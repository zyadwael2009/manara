"""Phase 32 · T2 — diploma issuance helper.

Called from `routes/classes.py::graduate_class` on the bulk-graduate
path. Idempotent per `(student_id, class_of_year)` — a re-run of the
graduation doesn't mint a second diploma, it returns the existing one.

Trust-core: reads existing enrollment + certificate rows to build the
snapshot columns on the diploma; writes ONLY to the `diplomas` table.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional


def _make_number(class_of_year: int) -> str:
    """Diploma number = MNR-DIP-YYYY-<16-hex>. 64 bits of entropy —
    matches the certificate scheme (`MNR-CRT-...`) since Phase 11 L2.
    An 8-hex tail was enumerable across the full graduate roster; this
    is the same fix the certificate number path shipped."""
    from uuid import uuid4
    return f"MNR-DIP-{class_of_year}-{uuid4().hex[:16].upper()}"


def issue_diploma(
    student_id: str,
    *,
    grade_id: Optional[str] = None,
    honors: Optional[str] = None,
    class_of_year: Optional[int] = None,
):
    """Issue (or return existing) diploma for one student.

    Returns the `Diploma` row (created or existing), or None if the
    student cannot be found. `class_of_year` defaults to the current
    UTC year — matches the graduation moment.
    """
    from models import Certificate, Diploma, Enrollment, User, db
    student = db.session.get(User, student_id)
    if student is None:
        return None
    if class_of_year is None:
        class_of_year = datetime.now(timezone.utc).year

    existing = Diploma.query.filter_by(
        student_id=student_id, class_of_year=class_of_year,
    ).first()
    if existing is not None:
        return existing

    # Snapshot: total non-revoked certificates + average grade cache
    # across the student's completed / active enrollments at the
    # moment of graduation. Denormalising these onto the diploma row
    # means the PDF stays deterministic even if certs are later
    # revoked or grades edited.
    certs = (
        Certificate.query
        .join(Enrollment, Enrollment.id == Certificate.enrollment_id)
        .filter(
            Enrollment.student_id == student_id,
            Certificate.revoked.is_(False),
        )
        .count()
    )
    enrollments = Enrollment.query.filter_by(student_id=student_id).all()
    pcts = [
        float(e.cached_percent)
        for e in enrollments if e.cached_percent is not None
    ]
    avg = (sum(pcts) / len(pcts)) if pcts else None
    # Phase 33 fix #2 — savepoint the insert so a diploma-number
    # collision (or any other IntegrityError) can be re-tried without
    # tainting the outer transaction. Same shape as
    # `maybe_issue_certificate` (Phase 9 F6). On collision we re-fetch
    # the (student, year) row and return it instead of losing the
    # graduate silently.
    from decimal import Decimal
    from sqlalchemy.exc import IntegrityError
    for _attempt in range(3):
        dip = Diploma(
            diploma_number=_make_number(class_of_year),
            student_id=student_id,
            grade_id=grade_id,
            class_of_year=class_of_year,
            honors=honors,
            total_certificates=certs,
            average_percent=Decimal(f"{avg:.2f}") if avg is not None else None,
        )
        try:
            with db.session.begin_nested():
                db.session.add(dip)
            return dip
        except IntegrityError:
            db.session.rollback()
            # (student, class_of_year) is the unique constraint on the
            # table — if we lost a concurrent-graduate race the peer
            # diploma is now committed and returning it is the correct
            # answer. Otherwise the collision was on `diploma_number`
            # (64-bit; astronomically rare) and the retry generates a
            # fresh number.
            existing = Diploma.query.filter_by(
                student_id=student_id, class_of_year=class_of_year,
            ).first()
            if existing is not None:
                return existing
            # Fall through to another attempt for a number-collision.
    return None
