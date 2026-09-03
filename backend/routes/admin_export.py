"""Phase 25 — admin CSV data export.

Complementary to the Phase 20 CSV importer: dump the school's core
tables to plain CSV so an admin can analyze offline.

Endpoints (all admin-only):
  * GET /api/admin/export/users.csv
  * GET /api/admin/export/enrollments.csv?termId=…
  * GET /api/admin/export/grades.csv?termId=…
  * GET /api/admin/export/attendance.csv?from=…&to=…

Response is `text/csv`; the browser downloads by content-disposition.
All queries are bounded (no LIKE, indexed columns) so exports scale
with the size of the school, not with disk history.
"""
from __future__ import annotations

import csv
import io
from datetime import date as _date, datetime

from flask import Blueprint, Response, jsonify, request

from models import (
    AttendanceMark,
    Course,
    Enrollment,
    GradeCategory,
    GradeEntry,
    SchoolClass,
    Term,
    User,
    db,
)
from routes.auth import require_admin
from utils.time import utc_now

admin_export_bp = Blueprint("admin_export", __name__)


def _csv_response(rows: list[list[str]], filename: str) -> Response:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    for row in rows:
        w.writerow(row)
    resp = Response(buf.getvalue(), mimetype="text/csv")
    resp.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    return resp


def _stamp() -> str:
    return utc_now().strftime("%Y%m%d-%H%M")


def _parse_iso_date(raw: str | None) -> _date | None:
    if not raw:
        return None
    try:
        return _date.fromisoformat(raw)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# users.csv
# ---------------------------------------------------------------------------
@admin_export_bp.route("/admin/export/users.csv", methods=["GET"])
@require_admin
def export_users():
    rows: list[list[str]] = [[
        "id", "name", "email", "role", "isActive",
        "className", "gradeName", "createdAt", "graduatedAt", "withdrawnAt",
    ]]
    for u in User.query.order_by(User.role.asc(), User.name.asc()).all():
        sc = db.session.get(SchoolClass, u.class_id) if u.class_id else None
        rows.append([
            u.id, u.name, u.email, u.role,
            "1" if u.is_active else "0",
            (sc.name if sc else ""),
            (sc.grade.name if sc and sc.grade else ""),
            u.created_at.isoformat() if u.created_at else "",
            u.graduated_at.isoformat() if u.graduated_at else "",
            u.withdrawn_at.isoformat() if u.withdrawn_at else "",
        ])
    return _csv_response(rows, f"users-{_stamp()}.csv")


# ---------------------------------------------------------------------------
# enrollments.csv
# ---------------------------------------------------------------------------
@admin_export_bp.route("/admin/export/enrollments.csv", methods=["GET"])
@require_admin
def export_enrollments():
    rows: list[list[str]] = [[
        "enrollmentId", "studentId", "studentName", "studentEmail",
        "courseId", "courseTitle", "status", "enrolledVia",
        "progressPercent", "cachedPercent", "cachedLetter", "cachedGpa",
        "enrolledAt", "completedAt",
    ]]
    for e in (
        Enrollment.query
        .order_by(Enrollment.enrolled_at.desc().nullslast())
        .all()
    ):
        student = e.student
        course = e.course
        rows.append([
            e.id,
            e.student_id,
            student.name if student else "",
            student.email if student else "",
            e.course_id,
            course.title if course else "",
            e.status or "",
            e.enrolled_via or "",
            str(e.progress_percent or 0),
            str(float(e.cached_percent)) if e.cached_percent is not None else "",
            e.cached_letter or "",
            str(float(e.cached_gpa)) if e.cached_gpa is not None else "",
            e.enrolled_at.isoformat() if e.enrolled_at else "",
            e.completed_at.isoformat() if e.completed_at else "",
        ])
    return _csv_response(rows, f"enrollments-{_stamp()}.csv")


# ---------------------------------------------------------------------------
# grades.csv
# ---------------------------------------------------------------------------
@admin_export_bp.route("/admin/export/grades.csv", methods=["GET"])
@require_admin
def export_grades():
    term_id = request.args.get("termId")
    rows: list[list[str]] = [[
        "gradeEntryId", "enrollmentId", "studentId", "studentName",
        "courseId", "courseTitle", "termId", "termName",
        "categoryId", "categorySlug", "categoryName", "score", "updatedAt",
    ]]
    q = GradeEntry.query
    if term_id:
        q = q.filter(GradeEntry.term_id == term_id)
    for entry in q.order_by(GradeEntry.updated_at.desc().nullslast()).all():
        e = db.session.get(Enrollment, entry.enrollment_id)
        student = e.student if e else None
        course = e.course if e else None
        cat = db.session.get(GradeCategory, entry.grade_category_id)
        term = db.session.get(Term, entry.term_id) if entry.term_id else None
        rows.append([
            entry.id,
            entry.enrollment_id,
            student.id if student else "",
            student.name if student else "",
            course.id if course else "",
            course.title if course else "",
            entry.term_id or "",
            term.name if term else "",
            entry.grade_category_id,
            cat.slug if cat else "",
            cat.name if cat else "",
            str(float(entry.score)),
            entry.updated_at.isoformat() if entry.updated_at else "",
        ])
    return _csv_response(rows, f"grades-{_stamp()}.csv")


# ---------------------------------------------------------------------------
# attendance.csv
# ---------------------------------------------------------------------------
@admin_export_bp.route("/admin/export/attendance.csv", methods=["GET"])
@require_admin
def export_attendance():
    from_d = _parse_iso_date(request.args.get("from"))
    to_d = _parse_iso_date(request.args.get("to"))
    rows: list[list[str]] = [[
        "id", "date", "studentId", "studentName",
        "classId", "className", "status", "reason", "markedById", "createdAt",
    ]]
    q = AttendanceMark.query
    if from_d is not None:
        q = q.filter(AttendanceMark.date >= from_d)
    if to_d is not None:
        q = q.filter(AttendanceMark.date <= to_d)
    for m in q.order_by(AttendanceMark.date.desc()).all():
        student = m.student
        sc = db.session.get(SchoolClass, m.class_id) if m.class_id else None
        rows.append([
            m.id,
            m.date.isoformat() if m.date else "",
            m.student_id,
            student.name if student else "",
            m.class_id or "",
            sc.name if sc else "",
            m.status or "",
            m.reason or "",
            m.marked_by_id or "",
            m.created_at.isoformat() if m.created_at else "",
        ])
    return _csv_response(rows, f"attendance-{_stamp()}.csv")


# ---------------------------------------------------------------------------
# Directory endpoint — small JSON that tells the admin UI what's exportable
# ---------------------------------------------------------------------------
@admin_export_bp.route("/admin/export/kinds", methods=["GET"])
@require_admin
def list_kinds():
    return jsonify({
        "kinds": [
            {"id": "users", "label": "Users",
             "description": "Every account: id, role, class, active/withdrawn.",
             "path": "/api/admin/export/users.csv"},
            {"id": "enrollments", "label": "Enrollments",
             "description": "Every student-course row with status + cached grade.",
             "path": "/api/admin/export/enrollments.csv"},
            {"id": "grades", "label": "Grade entries",
             "description": "Per-category scores, optionally by term.",
             "path": "/api/admin/export/grades.csv"},
            {"id": "attendance", "label": "Attendance marks",
             "description": "Every attendance row, optionally by date window.",
             "path": "/api/admin/export/attendance.csv"},
        ],
    }), 200
