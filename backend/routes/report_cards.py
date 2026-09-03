"""Phase 23 — PDF report card + multi-term transcript endpoints.

  * `GET /api/students/<id>/report-card.pdf?termId=…`
  * `GET /api/students/<id>/transcript.pdf`

Both are pure read-and-render. Auth uses the same `can_view_report_card`
predicate as the JSON report card, which already covers the student
themself, their parent, and admin.
"""
from __future__ import annotations

from flask import Blueprint, Response, jsonify

from models import SchoolClass, SchoolYear, Term, User, db
from routes.auth import current_user, login_required
from utils.grading import student_report_card
from utils.pdf import render_report_card_pdf, render_transcript_pdf
from utils.permissions import can_view_report_card

report_cards_bp = Blueprint("report_cards", __name__)


_SCHOOL_NAME = "Manara"


def _student_or_404(sid: str):
    s = db.session.get(User, sid)
    if s is None or s.role != "student":
        return None, (jsonify({"error": "Student not found."}), 404)
    return s, None


def _class_name(student: User) -> str | None:
    if student.class_id is None:
        return None
    sc = db.session.get(SchoolClass, student.class_id)
    return sc.name if sc else None


def _grade_name(student: User) -> str | None:
    if student.class_id is None:
        return None
    sc = db.session.get(SchoolClass, student.class_id)
    if sc is None or sc.grade is None:
        return None
    return sc.grade.name


@report_cards_bp.route("/students/<string:sid>/report-card.pdf", methods=["GET"])
@login_required
def report_card_pdf(sid: str):
    student, err = _student_or_404(sid)
    if err is not None:
        return err
    user = current_user()
    if not can_view_report_card(user, student):
        return jsonify({"error": "You do not have permission."}), 403

    # Term picker: current term if none passed.
    from flask import request
    term_id = request.args.get("termId")
    term = db.session.get(Term, term_id) if term_id else None
    if term is None:
        year = SchoolYear.query.filter_by(is_current=True).first()
        if year is not None:
            term = (
                Term.query.filter_by(school_year_id=year.id)
                .order_by(Term.order_index.asc())
                .first()
            )

    report = student_report_card(student.id, term_id=(term.id if term else None))
    pdf = render_report_card_pdf(
        student_name=student.name,
        student_email=student.email,
        class_name=_class_name(student),
        grade_name=_grade_name(student),
        term_name=(term.name if term else None),
        school_name=_SCHOOL_NAME,
        report=report,
    )
    resp = Response(pdf, mimetype="application/pdf")
    resp.headers["Content-Disposition"] = (
        f'inline; filename="report-card-{student.name.replace(" ", "-")}.pdf"'
    )
    return resp


@report_cards_bp.route("/students/<string:sid>/transcript.pdf", methods=["GET"])
@login_required
def transcript_pdf(sid: str):
    student, err = _student_or_404(sid)
    if err is not None:
        return err
    user = current_user()
    if not can_view_report_card(user, student):
        return jsonify({"error": "You do not have permission."}), 403

    # Walk every term of every school year, oldest first. student_report_card
    # already handles the filter per term; we call it once per term.
    terms: list[dict] = []
    years = (
        SchoolYear.query
        .order_by(SchoolYear.created_at.asc().nullslast())
        .all()
    )
    for y in years:
        for t in (
            Term.query.filter_by(school_year_id=y.id)
            .order_by(Term.order_index.asc())
            .all()
        ):
            report = student_report_card(student.id, term_id=t.id)
            # Skip empty terms — the student may not have been enrolled yet.
            if not (report.get("subjects") or []):
                continue
            terms.append({
                "termName": f"{y.name} · {t.name}",
                "subjects": report["subjects"],
                "cumulative": report.get("cumulative"),
            })

    pdf = render_transcript_pdf(
        student_name=student.name,
        student_email=student.email,
        grade_name=_grade_name(student),
        school_name=_SCHOOL_NAME,
        terms=terms,
    )
    resp = Response(pdf, mimetype="application/pdf")
    resp.headers["Content-Disposition"] = (
        f'inline; filename="transcript-{student.name.replace(" ", "-")}.pdf"'
    )
    return resp
