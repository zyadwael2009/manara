"""Phase 22 — insight & intervention read endpoints.

  * `GET /api/classes/<id>/at-risk` — roster with risk envelope per student.
  * `GET /api/students/mine/grade-history?termId=…` — student time-series.
  * `GET /api/attendance/patterns` — admin patterns dashboard.

All three are pure aggregate reads. No writes, no trust-core touched.
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from models import Enrollment, GradeHistoryPoint, SchoolClass, User, db
from routes.auth import current_user, login_required, require_admin
from utils.analytics import compute_at_risk, compute_attendance_patterns
from utils.permissions import homerooms_class, is_admin, is_student

insight_bp = Blueprint("insight", __name__)


@insight_bp.route("/classes/<string:class_id>/at-risk", methods=["GET"])
@login_required
def class_at_risk(class_id: str):
    """Roster of `class_id`, each with `{atRisk, reasons[]}`.

    Auth: admin OR homeroom teacher of the class. Course teachers do
    NOT get this (they might teach the class but shouldn't see class-
    wide intervention flags for students they only see one subject of).
    """
    sc = db.session.get(SchoolClass, class_id)
    if sc is None:
        return jsonify({"error": "Class not found."}), 404
    user = current_user()
    if not (is_admin(user) or homerooms_class(user, sc)):
        return jsonify({"error": "You do not have permission."}), 403

    rows: list[dict] = []
    for s in sc.students.order_by(User.name.asc()).all():
        env = compute_at_risk(s)
        rows.append({
            "studentId": s.id,
            "name": s.name,
            "email": s.email,
            "atRisk": env["atRisk"],
            "reasons": env["reasons"],
        })
    return jsonify(rows), 200


@insight_bp.route("/students/mine/grade-history", methods=["GET"])
@insight_bp.route("/students/mine/grade-history/", methods=["GET"])
@login_required
def my_grade_history():
    """Per-course time series of cached-percent for the caller (student).

    Response: `{ series: [ {courseId, courseTitle, points:
    [ {recordedAt, percent, letter?} ] }, ... ] }`. Points ordered oldest
    first. Callers plot the last ~8-12 for a sparkline.
    """
    user = current_user()
    if not is_student(user):
        return jsonify({"series": []}), 200

    enrolls = (
        Enrollment.query.filter_by(student_id=user.id)
        .filter(Enrollment.status.in_(("active", "completed")))
        .all()
    )
    series: list[dict] = []
    for e in enrolls:
        pts = (
            GradeHistoryPoint.query.filter_by(enrollment_id=e.id)
            .order_by(GradeHistoryPoint.recorded_at.asc())
            .all()
        )
        if not pts:
            continue
        course = e.course
        series.append({
            "courseId": e.course_id,
            "courseTitle": course.title if course else "",
            "points": [
                {
                    "recordedAt": p.recorded_at.isoformat() + "Z"
                    if p.recorded_at else None,
                    "percent": float(p.cached_percent),
                    "letter": p.cached_letter,
                }
                for p in pts
            ],
        })
    return jsonify({"series": series}), 200


@insight_bp.route("/attendance/patterns", methods=["GET"])
@require_admin
def attendance_patterns():
    try:
        top_n = int(request.args.get("topN", 10))
    except (TypeError, ValueError):
        top_n = 10
    top_n = max(1, min(50, top_n))
    return jsonify(compute_attendance_patterns(top_n=top_n)), 200
