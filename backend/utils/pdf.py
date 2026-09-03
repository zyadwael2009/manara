"""Phase 23 — PDF renderers for the report card and multi-year transcript.

Reuses the same `reportlab` stack the certificate PDF (`utils/certificates.py`)
already uses. Layout is intentionally plain — a school office prints
these; fancy graphics don't help.

Read-only. No writes. Callers hand the endpoint a fully-computed report
card / transcript dict and get back `bytes` ready for `send_file`.
"""
from __future__ import annotations

import io
from datetime import datetime
from typing import Any, Iterable
from utils.time import utc_now


# Small palette — kept in sync with the certificate render so a page
# printed today looks like it came from the same institution.
_INK = (0.10, 0.13, 0.21)     # slate-900
_MUTED = (0.44, 0.51, 0.60)   # slate-500
_ACCENT = (0.31, 0.27, 0.90)  # indigo-600
_LINE = (0.85, 0.87, 0.90)    # slate-200


def _fmt_pct(v: Any) -> str:
    if v is None:
        return "—"
    try:
        return f"{float(v):.1f}%"
    except (TypeError, ValueError):
        return "—"


def _fmt_num(v: Any, digits: int = 2) -> str:
    if v is None:
        return "—"
    try:
        return f"{float(v):.{digits}f}"
    except (TypeError, ValueError):
        return "—"


# ---------------------------------------------------------------------------
# Report card
# ---------------------------------------------------------------------------
def render_report_card_pdf(
    *,
    student_name: str,
    student_email: str,
    class_name: str | None,
    grade_name: str | None,
    term_name: str | None,
    school_name: str,
    report: dict,
) -> bytes:
    """Render one term's report card to a portrait A4 PDF."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas as pdfcanvas

    buf = io.BytesIO()
    c = pdfcanvas.Canvas(buf, pagesize=A4)
    w, h = A4

    _draw_page_header(
        c, w, h,
        title=school_name,
        subtitle="Report card",
        stamp=utc_now().strftime("Issued %d %b %Y"),
    )

    # Student block
    y = h - 40 * mm
    c.setFillColorRGB(*_INK)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(20 * mm, y, student_name)
    y -= 6 * mm
    c.setFont("Helvetica", 10)
    c.setFillColorRGB(*_MUTED)
    line = f"{student_email}"
    if grade_name:
        line += f"  ·  {grade_name}"
    if class_name:
        line += f"  ·  Class {class_name}"
    if term_name:
        line += f"  ·  Term {term_name}"
    c.drawString(20 * mm, y, line)

    # Cumulative band
    cum = report.get("cumulative") or {}
    y -= 12 * mm
    c.setStrokeColorRGB(*_LINE)
    c.setLineWidth(0.6)
    c.rect(20 * mm, y - 20 * mm, w - 40 * mm, 20 * mm, stroke=1, fill=0)
    c.setFillColorRGB(*_INK)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(24 * mm, y - 6 * mm, "Cumulative")
    c.setFont("Helvetica", 22)
    c.setFillColorRGB(*_ACCENT)
    c.drawString(24 * mm, y - 16 * mm, _fmt_pct(cum.get("percent")))
    c.setFont("Helvetica", 12)
    c.setFillColorRGB(*_INK)
    c.drawString(70 * mm, y - 16 * mm, f"Letter {cum.get('letter') or '—'}")
    c.drawString(110 * mm, y - 16 * mm, f"GPA {_fmt_num(cum.get('gpaValue'))}")

    # Subject rows
    y -= 32 * mm
    c.setFillColorRGB(*_MUTED)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(20 * mm, y, "SUBJECT")
    c.drawRightString(140 * mm, y, "PERCENT")
    c.drawRightString(165 * mm, y, "LETTER")
    c.drawRightString(190 * mm, y, "GPA")
    y -= 3 * mm
    c.setStrokeColorRGB(*_LINE)
    c.line(20 * mm, y, w - 20 * mm, y)

    y -= 6 * mm
    c.setFont("Helvetica", 11)
    c.setFillColorRGB(*_INK)
    for s in report.get("subjects") or []:
        if y < 30 * mm:
            c.showPage()
            _draw_page_header(c, w, h, title=school_name,
                              subtitle="Report card (continued)")
            y = h - 40 * mm
        c.drawString(20 * mm, y, str(s.get("courseTitle") or ""))
        c.drawRightString(140 * mm, y, _fmt_pct(s.get("percent")))
        c.drawRightString(165 * mm, y, s.get("letter") or "—")
        c.drawRightString(190 * mm, y, _fmt_num(s.get("gpaValue")))
        y -= 7 * mm

    _draw_footer(c, w)
    c.showPage()
    c.save()
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Transcript
# ---------------------------------------------------------------------------
def render_transcript_pdf(
    *,
    student_name: str,
    student_email: str,
    grade_name: str | None,
    school_name: str,
    terms: Iterable[dict],
) -> bytes:
    """Render a multi-term transcript. `terms` is an iterable of
    `{termName, subjects: [ {courseTitle, percent, letter, gpaValue} ],
       cumulative: {percent, letter, gpaValue}}`.
    """
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas as pdfcanvas

    buf = io.BytesIO()
    c = pdfcanvas.Canvas(buf, pagesize=A4)
    w, h = A4

    _draw_page_header(
        c, w, h,
        title=school_name,
        subtitle="Academic transcript",
        stamp=utc_now().strftime("Issued %d %b %Y"),
    )
    y = h - 40 * mm
    c.setFillColorRGB(*_INK)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(20 * mm, y, student_name)
    y -= 6 * mm
    c.setFont("Helvetica", 10)
    c.setFillColorRGB(*_MUTED)
    header_line = student_email + (f"  ·  {grade_name}" if grade_name else "")
    c.drawString(20 * mm, y, header_line)

    y -= 10 * mm
    for term in terms:
        if y < 40 * mm:
            c.showPage()
            _draw_page_header(c, w, h, title=school_name,
                              subtitle="Academic transcript (continued)")
            y = h - 40 * mm

        # Term band
        c.setFillColorRGB(*_INK)
        c.setFont("Helvetica-Bold", 12)
        c.drawString(20 * mm, y, term.get("termName") or "Term")
        cum = term.get("cumulative") or {}
        c.setFont("Helvetica", 10)
        c.setFillColorRGB(*_MUTED)
        c.drawRightString(
            w - 20 * mm, y,
            f"{_fmt_pct(cum.get('percent'))}   ·   {cum.get('letter') or '—'}"
            f"   ·   GPA {_fmt_num(cum.get('gpaValue'))}",
        )
        y -= 3 * mm
        c.setStrokeColorRGB(*_LINE)
        c.line(20 * mm, y, w - 20 * mm, y)
        y -= 5 * mm

        c.setFont("Helvetica", 10.5)
        c.setFillColorRGB(*_INK)
        for s in term.get("subjects") or []:
            if y < 30 * mm:
                c.showPage()
                _draw_page_header(c, w, h, title=school_name,
                                  subtitle="Academic transcript (continued)")
                y = h - 40 * mm
            c.drawString(24 * mm, y, str(s.get("courseTitle") or ""))
            c.drawRightString(140 * mm, y, _fmt_pct(s.get("percent")))
            c.drawRightString(165 * mm, y, s.get("letter") or "—")
            c.drawRightString(190 * mm, y, _fmt_num(s.get("gpaValue")))
            y -= 6 * mm

        y -= 8 * mm

    _draw_footer(c, w)
    c.showPage()
    c.save()
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Phase 28 — Fee statement / receipt
#
# Renders one page per student showing every fee item, per-fee payments,
# and a totals block at the bottom. Reuses the same header + footer +
# palette as the report card so a school office folder of PDFs reads
# with one visual voice.
# ---------------------------------------------------------------------------
def render_fees_pdf(*, student, fees) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas as _canvas

    buf = io.BytesIO()
    w, h = A4
    c = _canvas.Canvas(buf, pagesize=A4)
    _draw_page_header(
        c, w, h,
        title="Manara",
        subtitle="Fee statement",
        stamp=utc_now().strftime("%Y-%m-%d"),
    )

    # Student identity block.
    y = h - 40 * mm
    c.setFillColorRGB(*_INK)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(20 * mm, y, student.name or "—")
    y -= 5 * mm
    c.setFillColorRGB(*_MUTED)
    c.setFont("Helvetica", 9.5)
    c.drawString(20 * mm, y, student.email or "")
    y -= 10 * mm

    # Column header.
    c.setFillColorRGB(*_MUTED)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(20 * mm, y, "FEE ITEM")
    c.drawRightString(120 * mm, y, "DUE")
    c.drawRightString(150 * mm, y, "AMOUNT")
    c.drawRightString(175 * mm, y, "PAID")
    c.drawRightString(w - 20 * mm, y, "BALANCE")
    y -= 3 * mm
    c.setStrokeColorRGB(*_LINE)
    c.setLineWidth(0.5)
    c.line(20 * mm, y, w - 20 * mm, y)
    y -= 5 * mm

    total_amount = 0.0
    total_paid = 0.0
    for fee in fees:
        if y < 40 * mm:
            _draw_footer(c, w)
            c.showPage()
            _draw_page_header(c, w, h, title="Manara",
                              subtitle="Fee statement (continued)")
            y = h - 40 * mm

        amount = float(fee.amount or 0)
        paid = float(fee.paid_amount())
        balance = amount - paid
        total_amount += amount
        total_paid += paid

        c.setFillColorRGB(*_INK)
        c.setFont("Helvetica", 10.5)
        c.drawString(20 * mm, y, (fee.label or "")[:60])
        c.setFont("Helvetica", 9.5)
        c.setFillColorRGB(*_MUTED)
        c.drawRightString(120 * mm, y,
                          fee.due_date.isoformat() if fee.due_date else "—")
        c.setFillColorRGB(*_INK)
        c.setFont("Helvetica", 10)
        c.drawRightString(150 * mm, y, f"{amount:,.2f}")
        c.drawRightString(175 * mm, y, f"{paid:,.2f}")
        # Balance is highlighted in the accent color when > 0 so it's
        # obvious at a glance which lines are still owed.
        if balance > 0:
            c.setFillColorRGB(*_ACCENT)
            c.setFont("Helvetica-Bold", 10)
        c.drawRightString(w - 20 * mm, y, f"{balance:,.2f}")
        y -= 6 * mm

        # Payment rows (indented, smaller type).
        for p in fee.payments.all():
            if y < 30 * mm:
                _draw_footer(c, w)
                c.showPage()
                _draw_page_header(c, w, h, title="Manara",
                                  subtitle="Fee statement (continued)")
                y = h - 40 * mm
            c.setFillColorRGB(*_MUTED)
            c.setFont("Helvetica", 9)
            paid_at = p.paid_at.strftime("%Y-%m-%d") if p.paid_at else "—"
            method = f" · {p.method}" if p.method else ""
            c.drawString(26 * mm, y, f"payment {paid_at}{method}")
            c.drawRightString(175 * mm, y, f"{float(p.amount or 0):,.2f}")
            y -= 5 * mm
        y -= 2 * mm

    # Totals block.
    y -= 4 * mm
    c.setStrokeColorRGB(*_LINE)
    c.setLineWidth(0.8)
    c.line(20 * mm, y, w - 20 * mm, y)
    y -= 7 * mm
    c.setFillColorRGB(*_INK)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(20 * mm, y, "Totals")
    c.drawRightString(150 * mm, y, f"{total_amount:,.2f}")
    c.drawRightString(175 * mm, y, f"{total_paid:,.2f}")
    balance_total = total_amount - total_paid
    if balance_total > 0:
        c.setFillColorRGB(*_ACCENT)
    c.drawRightString(w - 20 * mm, y, f"{balance_total:,.2f}")

    _draw_footer(c, w)
    c.showPage()
    c.save()
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Phase 31 · T3 — Cohort comparison PDF
#
# One page per term: header block + per-class metrics table + a totals
# block for the whole-term rollup. Same visual chrome as the fees PDF
# so an admin printing both reports gets one voice.
#
# `snap_a` and `snap_b` are the exact JSON dicts returned by
# `_term_snapshot()` in `routes/dashboards.py`.
# ---------------------------------------------------------------------------
def render_cohort_comparison_pdf(snap_a: dict, snap_b: dict) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas as _canvas

    buf = io.BytesIO()
    w, h = A4
    c = _canvas.Canvas(buf, pagesize=A4)

    def _render_page(snap: dict, subtitle: str) -> None:
        _draw_page_header(
            c, w, h,
            title="Manara",
            subtitle=subtitle,
            stamp=utc_now().strftime("%Y-%m-%d"),
        )
        y = h - 40 * mm
        c.setFillColorRGB(*_INK)
        c.setFont("Helvetica-Bold", 13)
        c.drawString(20 * mm, y, snap.get("termName") or "—")
        y -= 5 * mm
        c.setFillColorRGB(*_MUTED)
        c.setFont("Helvetica", 9.5)
        span = (
            f"{snap.get('startDate') or '—'} → {snap.get('endDate') or '—'}"
        )
        c.drawString(20 * mm, y, span)
        y -= 10 * mm

        # Column header.
        c.setFillColorRGB(*_MUTED)
        c.setFont("Helvetica-Bold", 9)
        c.drawString(20 * mm, y, "CLASS")
        c.drawRightString(105 * mm, y, "STUDENTS")
        c.drawRightString(130 * mm, y, "ATTN")
        c.drawRightString(155 * mm, y, "AVG %")
        c.drawRightString(180 * mm, y, "PASS %")
        c.drawRightString(w - 20 * mm, y, "CERTS")
        y -= 3 * mm
        c.setStrokeColorRGB(*_LINE)
        c.setLineWidth(0.5)
        c.line(20 * mm, y, w - 20 * mm, y)
        y -= 5 * mm

        c.setFillColorRGB(*_INK)
        c.setFont("Helvetica", 10.5)
        for row in snap.get("perClass") or []:
            if y < 30 * mm:
                _draw_footer(c, w)
                c.showPage()
                _draw_page_header(c, w, h, title="Manara",
                                  subtitle=f"{subtitle} (continued)")
                y = h - 40 * mm
            c.drawString(20 * mm, y, str(row.get("className") or "")[:40])
            c.drawRightString(105 * mm, y, str(row.get("students", 0)))
            c.drawRightString(130 * mm, y,
                              _fmt_pct((row.get("attendanceRate", 0) or 0) * 100))
            c.drawRightString(155 * mm, y,
                              _fmt_pct(row.get("avgPercent", 0)))
            c.drawRightString(180 * mm, y,
                              _fmt_pct((row.get("passRate", 0) or 0) * 100))
            c.drawRightString(w - 20 * mm, y, str(row.get("certCount", 0)))
            y -= 6 * mm

        # Whole-term rollup block.
        overall = snap.get("overall") or {}
        y -= 6 * mm
        c.setStrokeColorRGB(*_LINE)
        c.setLineWidth(0.8)
        c.line(20 * mm, y, w - 20 * mm, y)
        y -= 7 * mm
        c.setFillColorRGB(*_ACCENT)
        c.setFont("Helvetica-Bold", 11)
        c.drawString(20 * mm, y, "Term overall")
        c.drawRightString(130 * mm, y,
                          _fmt_pct((overall.get("attendanceRate", 0) or 0) * 100))
        c.drawRightString(155 * mm, y,
                          _fmt_pct(overall.get("avgPercent", 0)))
        c.drawRightString(180 * mm, y,
                          _fmt_pct((overall.get("passRate", 0) or 0) * 100))
        c.drawRightString(w - 20 * mm, y, str(overall.get("certCount", 0)))
        _draw_footer(c, w)
        c.showPage()

    _render_page(snap_a, "Cohort comparison · Term A")
    _render_page(snap_b, "Cohort comparison · Term B")
    c.save()
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Phase 32 · T2 — Digital diploma
#
# One-page A4 landscape with a formal ornamental border, the student
# name in a very large hand-scriptish font (we fall back to
# Helvetica-Bold because reportlab's default set doesn't ship a
# script face — the important thing is that it *reads* like a
# diploma, not a report card). Class-of-YYYY band and honors line at
# the bottom, plus a small verify block with the diploma number.
# ---------------------------------------------------------------------------
def render_diploma_pdf(*, diploma, student) -> bytes:
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas as _canvas

    buf = io.BytesIO()
    w, h = landscape(A4)
    c = _canvas.Canvas(buf, pagesize=landscape(A4))

    # Ornamental double border — outer thin line, inner thicker accent.
    c.setStrokeColorRGB(*_INK)
    c.setLineWidth(0.4)
    c.rect(10 * mm, 10 * mm, w - 20 * mm, h - 20 * mm, stroke=1, fill=0)
    c.setStrokeColorRGB(*_ACCENT)
    c.setLineWidth(1.4)
    c.rect(14 * mm, 14 * mm, w - 28 * mm, h - 28 * mm, stroke=1, fill=0)

    # Header — school name + document label.
    c.setFillColorRGB(*_INK)
    c.setFont("Helvetica-Bold", 22)
    c.drawCentredString(w / 2, h - 30 * mm, "Manara")
    c.setFillColorRGB(*_MUTED)
    c.setFont("Helvetica", 11)
    c.drawCentredString(w / 2, h - 37 * mm, "DIPLOMA · DIGITAL VERIFIED CREDENTIAL")

    # Body — "This is to certify that..."
    y = h - 70 * mm
    c.setFillColorRGB(*_INK)
    c.setFont("Helvetica", 14)
    c.drawCentredString(w / 2, y, "This is to certify that")
    y -= 20 * mm
    # Student name — hero.
    c.setFillColorRGB(*_ACCENT)
    c.setFont("Helvetica-Bold", 34)
    c.drawCentredString(w / 2, y, (student.name or "—"))
    y -= 15 * mm
    c.setFillColorRGB(*_INK)
    c.setFont("Helvetica", 13)
    c.drawCentredString(
        w / 2, y,
        "has successfully completed the requirements of secondary education",
    )
    y -= 8 * mm
    c.drawCentredString(
        w / 2, y,
        "and is hereby awarded this diploma with all rights and privileges pertaining thereto.",
    )

    # Class-of-YYYY band.
    y -= 20 * mm
    c.setStrokeColorRGB(*_LINE)
    c.setLineWidth(0.6)
    c.line(w / 2 - 60 * mm, y, w / 2 + 60 * mm, y)
    y -= 8 * mm
    c.setFillColorRGB(*_INK)
    c.setFont("Helvetica-Bold", 16)
    c.drawCentredString(w / 2, y, f"CLASS OF {diploma.class_of_year}")

    if diploma.honors:
        y -= 8 * mm
        c.setFillColorRGB(*_ACCENT)
        c.setFont("Helvetica-Oblique", 13)
        c.drawCentredString(
            w / 2, y, diploma.honors.replace("_", " ").upper(),
        )

    # Bottom — verify block (left) + signatures line (right).
    c.setFillColorRGB(*_MUTED)
    c.setFont("Helvetica", 8)
    c.drawString(20 * mm, 20 * mm,
                 f"Verify at /verify-diploma/{diploma.diploma_number}")
    c.drawString(20 * mm, 16 * mm,
                 f"Issued {diploma.issued_at.strftime('%d %b %Y') if diploma.issued_at else '—'}")
    if diploma.total_certificates:
        c.drawString(
            20 * mm, 12 * mm,
            f"{diploma.total_certificates} course certificate"
            f"{'s' if diploma.total_certificates != 1 else ''} earned",
        )
    # Signature line.
    c.setStrokeColorRGB(*_INK)
    c.setLineWidth(0.4)
    c.line(w - 90 * mm, 22 * mm, w - 25 * mm, 22 * mm)
    c.setFont("Helvetica", 9)
    c.drawString(w - 90 * mm, 18 * mm, "Head of School")

    # Revoked overlay (rare) — big diagonal stamp.
    if diploma.revoked:
        c.saveState()
        c.translate(w / 2, h / 2)
        c.rotate(30)
        c.setFillColorRGB(0.85, 0.10, 0.15)
        c.setFont("Helvetica-Bold", 100)
        c.drawCentredString(0, 0, "REVOKED")
        c.restoreState()

    c.showPage()
    c.save()
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Chrome (header/footer)
# ---------------------------------------------------------------------------
def _draw_page_header(c, w, h, *, title: str, subtitle: str = "",
                     stamp: str | None = None) -> None:
    from reportlab.lib.units import mm
    c.setFillColorRGB(*_INK)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(20 * mm, h - 20 * mm, title)
    if subtitle:
        c.setFillColorRGB(*_MUTED)
        c.setFont("Helvetica", 10)
        c.drawString(20 * mm, h - 26 * mm, subtitle)
    if stamp:
        c.setFillColorRGB(*_MUTED)
        c.setFont("Helvetica", 9)
        c.drawRightString(w - 20 * mm, h - 20 * mm, stamp)
    # Rule under the header block.
    c.setStrokeColorRGB(*_LINE)
    c.setLineWidth(0.6)
    c.line(20 * mm, h - 30 * mm, w - 20 * mm, h - 30 * mm)


def _draw_footer(c, w) -> None:
    from reportlab.lib.units import mm
    c.setFillColorRGB(*_MUTED)
    c.setFont("Helvetica", 8)
    c.drawString(20 * mm, 12 * mm, "Manara · Auto-generated document")
