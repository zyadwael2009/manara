"""Certificate gate + issuance + PDF renderer.

Trust-core (Rule #6): three gate criteria checked server-side inside the
same transaction that could flip them.

  1. enrollment.progress_percent == 100
  2. Every published quiz in the course has a passing attempt by this student
  3. Cumulative % >= course.min_certificate_percent (default 60)

Callers wire `maybe_issue_certificate(enrollment)` into their write path;
it's idempotent — if a cert already exists for this enrollment, it just
returns it. On successful issuance, a `certificates` row is created with
a `LMS-YYYY-<8-hex>` number derived from a UUID4.
"""
from __future__ import annotations

import io
import uuid as _uuid
from datetime import datetime
from typing import Optional

from models import (
    Certificate,
    Course,
    Enrollment,
    Quiz,
    QuizAttempt,
    User,
    db,
)
from utils.time import utc_now

DEFAULT_MIN_CERT_PERCENT = 60


# ---------------------------------------------------------------------------
# Gate check
# ---------------------------------------------------------------------------
def is_eligible(enrollment: Enrollment) -> tuple[bool, list[str]]:
    """Return (True, []) when all three gates pass; else (False, reasons)."""
    reasons: list[str] = []

    if enrollment.progress_percent != 100:
        reasons.append(f"Progress is {enrollment.progress_percent}%, not 100%.")

    course = enrollment.course
    if course is None:
        reasons.append("Course not found.")
        return (False, reasons)

    # Quizzes: every published quiz in the course must have a passing attempt.
    # Phase 33 fix #6 — was O(modules × quizzes) queries: one Quiz
    # query per module + one QuizAttempt query per quiz. On a course
    # with 12 modules × 4 quizzes that was 60+ SELECTs per
    # `maybe_issue_certificate` call — which itself runs from every
    # progress mark, grade write, quiz submit, and rubric edit. Now
    # two queries total: all published quizzes joined through modules,
    # and all passing attempts by this student for those quizzes.
    module_ids = [m.id for m in course.modules]
    if module_ids:
        published_quizzes = (
            Quiz.query
            .filter(Quiz.module_id.in_(module_ids))
            .filter_by(is_published=True)
            .all()
        )
        if published_quizzes:
            quiz_ids = [q.id for q in published_quizzes]
            passing_quiz_ids = {
                row.quiz_id for row in
                QuizAttempt.query
                .filter(QuizAttempt.quiz_id.in_(quiz_ids))
                .filter_by(student_id=enrollment.student_id, passed=True)
                .filter(QuizAttempt.submitted_at.isnot(None))
                .all()
            }
            for q in published_quizzes:
                if q.id not in passing_quiz_ids:
                    reasons.append(f"Quiz '{q.title}' hasn't been passed.")

    # Cumulative percentage.
    min_pct = course.min_certificate_percent
    if min_pct is None:
        min_pct = DEFAULT_MIN_CERT_PERCENT
    cached = enrollment.cached_percent
    if cached is None:
        reasons.append("No graded categories yet — course percentage unavailable.")
    elif float(cached) < min_pct:
        reasons.append(f"Course grade {float(cached):.1f}% is below {min_pct}%.")

    return (len(reasons) == 0, reasons)


# ---------------------------------------------------------------------------
# Number generator
# ---------------------------------------------------------------------------
def _generate_cert_number() -> str:
    # Phase 11 audit fix L1: 16 hex chars = 64 bits of entropy. The old
    # 8-char format (~32 bits) hit ~50% birthday-collision probability at
    # ~65k certs per year, and made the public /verify endpoint enumerable
    # at internet scale. 16 chars pushes that boundary out to ~4 billion.
    # Old certs (8-char suffix) still verify — verify does exact-string
    # lookup, not a fixed-length parse.
    year = utc_now().year
    hex_part = _uuid.uuid4().hex[:16].upper()
    return f"LMS-{year}-{hex_part}"


# ---------------------------------------------------------------------------
# Idempotent issuance
# ---------------------------------------------------------------------------
def maybe_issue_certificate(
    enrollment: Enrollment, by_user: Optional[User] = None
) -> Optional[Certificate]:
    """Create a certificate if eligible AND no existing cert. Otherwise
    return the existing cert (if any) or None. Does NOT commit — caller's
    transaction wraps this.
    """
    existing = Certificate.query.filter_by(enrollment_id=enrollment.id).first()
    if existing is not None:
        return existing
    ok, _reasons = is_eligible(enrollment)
    if not ok:
        return None
    # Phase 9 audit fix F6: two concurrent triggering writes for the same
    # enrollment (e.g. a lesson-complete and a quiz-submit racing) can both
    # see "no cert" and both try to insert; the unique constraint on
    # `enrollment_id` catches one with an IntegrityError. Without this
    # savepoint the whole outer transaction (progress row + grade cache +
    # quiz score) rolls back and the caller 500s. With it, the loser
    # rolls back only its own INSERT and returns the winner's row.
    from sqlalchemy.exc import IntegrityError
    cert = Certificate(
        certificate_number=_generate_cert_number(),
        enrollment_id=enrollment.id,
        issued_at=utc_now(),
    )
    try:
        with db.session.begin_nested():
            db.session.add(cert)
            db.session.flush()
    except IntegrityError:
        # Losing side of the race. Refetch the winner and return it.
        cert = Certificate.query.filter_by(enrollment_id=enrollment.id).first()
        return cert
    # Phase 21 — bell notification. Only fires on the winning insert
    # (the losing side returned above). The enqueue helper is
    # additionally same-day idempotent so a re-triggered eligibility
    # check can't re-notify.
    from utils.notifications import enqueue
    course = enrollment.course
    enqueue(
        enrollment.student_id,
        kind="certificate_issued",
        title="Certificate earned!",
        body=(course.title if course else "You earned a certificate.")
             + " — download from your course page.",
        ref_type="certificate",
        ref_id=cert.id,
    )
    return cert


# ---------------------------------------------------------------------------
# PDF renderer
# ---------------------------------------------------------------------------
def render_certificate_pdf(cert: Certificate, verify_base_url: str = "") -> bytes:
    """Render a landscape A4 certificate PDF. Byte output only — the
    caller streams it via `send_file` or similar.

    verify_base_url: e.g. "https://school.example.com" so the PDF footer
    can print a full URL. Empty string omits the URL.
    """
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.pdfgen import canvas as pdfcanvas

    enrollment = cert.enrollment
    student = enrollment.student if enrollment else None
    course = enrollment.course if enrollment else None

    student_name = student.name if student else "Unknown Student"
    course_title = course.title if course else "Unknown Course"
    issued_str = cert.issued_at.strftime("%B %d, %Y") if cert.issued_at else "—"

    buf = io.BytesIO()
    page = landscape(A4)
    width, height = page
    c = pdfcanvas.Canvas(buf, pagesize=page)

    # --- Border frame ---
    c.setStrokeColor(colors.HexColor("#4F46E5"))
    c.setLineWidth(2)
    c.rect(10 * mm, 10 * mm, width - 20 * mm, height - 20 * mm)
    c.setStrokeColor(colors.HexColor("#F59E0B"))
    c.setLineWidth(1)
    c.rect(14 * mm, 14 * mm, width - 28 * mm, height - 28 * mm)

    # --- School header ---
    c.setFillColor(colors.HexColor("#3730A3"))
    c.setFont("Helvetica-Bold", 14)
    c.drawCentredString(width / 2, height - 25 * mm, "LMS · SCHOOL OF LEARNING")

    # --- Certificate title ---
    c.setFillColor(colors.HexColor("#0F172A"))
    c.setFont("Helvetica-Bold", 40)
    c.drawCentredString(width / 2, height - 55 * mm, "Certificate of Completion")

    # --- Awarded to ---
    c.setFillColor(colors.HexColor("#475569"))
    c.setFont("Helvetica", 14)
    c.drawCentredString(width / 2, height - 75 * mm, "This certificate is proudly presented to")

    c.setFillColor(colors.HexColor("#4F46E5"))
    c.setFont("Helvetica-Bold", 32)
    c.drawCentredString(width / 2, height - 95 * mm, student_name)

    # Line under name.
    c.setStrokeColor(colors.HexColor("#E5E7EB"))
    c.setLineWidth(0.5)
    line_w = min(150 * mm, len(student_name) * 8 + 20)
    c.line((width - line_w) / 2, height - 100 * mm, (width + line_w) / 2, height - 100 * mm)

    # --- For completing ---
    c.setFillColor(colors.HexColor("#475569"))
    c.setFont("Helvetica", 14)
    c.drawCentredString(width / 2, height - 115 * mm, "for successfully completing the course")

    c.setFillColor(colors.HexColor("#0F172A"))
    c.setFont("Helvetica-Bold", 22)
    c.drawCentredString(width / 2, height - 130 * mm, course_title)

    # --- Date ---
    c.setFillColor(colors.HexColor("#475569"))
    c.setFont("Helvetica-Oblique", 12)
    c.drawCentredString(width / 2, height - 150 * mm, f"Issued on {issued_str}")

    # --- Footer: cert number + verify URL ---
    c.setFillColor(colors.HexColor("#94A3B8"))
    c.setFont("Helvetica", 9)
    c.drawString(20 * mm, 20 * mm, f"Certificate No. {cert.certificate_number}")
    if verify_base_url:
        verify_url = f"{verify_base_url.rstrip('/')}/verify/{cert.certificate_number}"
        c.drawRightString(width - 20 * mm, 20 * mm, f"Verify at: {verify_url}")
    else:
        c.drawRightString(
            width - 20 * mm, 20 * mm,
            f"Verify: /api/verify/{cert.certificate_number}",
        )

    c.showPage()
    c.save()
    return buf.getvalue()
