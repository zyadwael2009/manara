"""Enrollments blueprint — reads + manual escape-hatch add/drop.

Auto-enrollment (mandatory subjects) happens in `students.py` on class
placement. Elective picks happen in `students.py` too. This module holds:
  * `GET /api/enrollments/mine`         — student's own enrollments
  * `GET /api/enrollments/<id>`         — detail
  * `GET /api/courses/<id>/enrollments` — roster of a course
  * `POST /api/courses/<id>/enrollments` — admin manual add (escape hatch)
  * `DELETE /api/enrollments/<id>`      — admin manual soft-drop
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from models import Certificate, Course, Enrollment, SchoolClass, User, db
from routes.auth import current_user, login_required, require_admin
from utils.permissions import (
    can_edit_course_content,
    can_view_student_records,
    classes_user_teaches_for_course,
    is_admin,
    teaches_course_in_any_class,
)
from utils.validation import (
    ValidationError,
    as_str,
    require_fields,
    require_json,
)

enrollments_bp = Blueprint("enrollments", __name__)


def _certs_by_enrollment(rows) -> dict:
    """Phase 33 fix #5 — batch-load certificates for a page of
    enrollments in ONE query, then hand the map into `to_dict` to skip
    its per-row Certificate.query. Turns N+1 (1 + N) into (1 + 1)."""
    ids = [e.id for e in rows]
    if not ids:
        return {}
    return {
        c.enrollment_id: c
        for c in Certificate.query.filter(
            Certificate.enrollment_id.in_(ids)
        ).all()
    }


@enrollments_bp.route("/enrollments/mine", methods=["GET"])
@enrollments_bp.route("/enrollments/mine/", methods=["GET"])
@login_required
def my_enrollments():
    """List all enrollments for the current user (any role).

    Students: their placed courses.
    Everyone else: empty (or their own enrollments if they somehow have any).
    """
    user = current_user()
    # Phase 25 hard-audit fix: this endpoint is student-scoped by
    # design. Non-students that happen to own Enrollment rows (data
    # anomalies, historical role changes) shouldn't leak them via a
    # loosely-typed "any role" pass-through. If a non-student needs a
    # list, they use `/api/users/<id>/enrollments` with proper role
    # checks instead.
    from utils.permissions import is_student
    if not is_student(user):
        return jsonify([]), 200
    q = (
        Enrollment.query.filter_by(student_id=user.id)
        .order_by(Enrollment.enrolled_at.desc())
    )
    # Phase 33 fix #25 — optional envelope pagination (back-compat
    # bare-array shape when no `page`/`pageSize` arg is supplied).
    if request.args.get("page") or request.args.get("pageSize"):
        from utils.pagination import paginate
        page = paginate(
            q,
            render_item=lambda e: e.to_dict(
                include_course=True,
                cert_by_enrollment=_certs_by_enrollment([e]),
            ),
        )
        return jsonify(page), 200
    rows = q.all()
    cert_map = _certs_by_enrollment(rows)
    return jsonify([
        e.to_dict(include_course=True, cert_by_enrollment=cert_map)
        for e in rows
    ]), 200


@enrollments_bp.route("/users/<string:student_id>/enrollments", methods=["GET"])
@login_required
def list_student_enrollments(student_id: str):
    """All enrollments for one student — used by admin's student-detail
    screen and (Phase 6) the parent portal.

    Auth: `can_view_student_records` — admin, student's course teachers,
    homeroom teacher, or the student themself (parent later).
    """
    student = db.session.get(User, student_id)
    if student is None or student.role != "student":
        return jsonify({"error": "Student not found."}), 404
    user = current_user()
    if not can_view_student_records(user, student):
        return jsonify({"error": "You do not have permission."}), 403
    rows = (
        Enrollment.query.filter_by(student_id=student.id)
        .order_by(Enrollment.enrolled_at.desc())
        .all()
    )
    cert_map = _certs_by_enrollment(rows)
    return jsonify([
        e.to_dict(include_course=True, cert_by_enrollment=cert_map)
        for e in rows
    ]), 200


@enrollments_bp.route("/enrollments/<string:enrollment_id>", methods=["GET"])
@login_required
def get_enrollment(enrollment_id: str):
    e = db.session.get(Enrollment, enrollment_id)
    if e is None:
        return jsonify({"error": "Enrollment not found."}), 404
    user = current_user()
    if not can_view_student_records(user, e.student):
        return jsonify({"error": "You do not have permission."}), 403
    return jsonify(e.to_dict(include_course=True)), 200


@enrollments_bp.route("/courses/<string:course_id>/enrollments", methods=["GET"])
@login_required
def list_course_enrollments(course_id: str):
    """Roster of a course. Admin OR any teacher of the course."""
    course = db.session.get(Course, course_id)
    if course is None:
        return jsonify({"error": "Course not found."}), 404
    user = current_user()
    if not (is_admin(user) or teaches_course_in_any_class(user, course)):
        return jsonify({"error": "You do not have permission."}), 403

    q = (
        Enrollment.query.filter_by(course_id=course.id)
        .filter(Enrollment.status.in_(("active", "completed")))
    )
    # Phase 9 audit fix F4: non-admin callers only see enrollments of
    # students in classes they teach this course in.
    # Phase 33 fix #24 — push the class filter into SQL (was a Python
    # post-filter that pulled the whole roster over the wire even
    # when the teacher only owned a subset of classes).
    if not is_admin(user):
        allowed_class_ids = classes_user_teaches_for_course(user, course)
        if not allowed_class_ids:
            return jsonify([]), 200
        q = q.join(User, User.id == Enrollment.student_id).filter(
            User.class_id.in_(allowed_class_ids)
        )
    rows = q.all()
    cert_map = _certs_by_enrollment(rows)
    # Enrich each row with a compact student blob including their class.
    out = []
    for e in rows:
        s = e.student
        d = e.to_dict(cert_by_enrollment=cert_map)
        d["student"] = s.to_dict() if s else None
        out.append(d)
    return jsonify(out), 200


@enrollments_bp.route("/courses/<string:course_id>/enrollments", methods=["POST"])
@require_admin
def manual_enroll(course_id: str):
    """Escape-hatch — admin manually enrolls a student in a course.
    Records enrolled_via='manual'.
    """
    course = db.session.get(Course, course_id)
    if course is None:
        return jsonify({"error": "Course not found."}), 404
    try:
        payload = require_json(request.get_json(silent=True))
        require_fields(payload, ("studentId",))
        student_id = as_str(payload["studentId"], "studentId")
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400

    student = db.session.get(User, student_id)
    if student is None or student.role != "student":
        return jsonify({"error": "studentId must refer to a student."}), 400

    existing = Enrollment.query.filter_by(student_id=student.id, course_id=course.id).first()
    if existing is not None:
        if existing.status != "active":
            existing.status = "active"
            existing.enrolled_via = "manual"
            existing.enrolled_by_id = current_user().id
            db.session.commit()
            # Phase 33 fix #14 — recompute progress + grade cache on
            # re-activation so the report card doesn't show the
            # stale cachedPercent captured at drop time. Runs through
            # the same trust-core writers the rest of the app uses.
            from utils.grading import (
                recompute_enrollment_cache,
                recompute_progress_percent,
            )
            recompute_progress_percent(existing)
            recompute_enrollment_cache(existing)
            db.session.commit()
        return jsonify(existing.to_dict()), 200

    admin = current_user()
    e = Enrollment(
        student_id=student.id,
        course_id=course.id,
        status="active",
        enrolled_via="manual",
        enrolled_by_id=admin.id,
    )
    db.session.add(e)
    db.session.commit()
    return jsonify(e.to_dict()), 201


@enrollments_bp.route("/enrollments/<string:enrollment_id>", methods=["DELETE"])
@require_admin
def drop_enrollment(enrollment_id: str):
    """Soft-drop an enrollment (status='dropped').

    Refuses if this is a mandatory course for the student's current class
    (dropping it would break the curriculum invariant — admin must
    unassign the student from the class first).
    """
    e = db.session.get(Enrollment, enrollment_id)
    if e is None:
        return jsonify({"error": "Enrollment not found."}), 404
    student = e.student
    course = e.course
    # If the student is currently in a class whose grade owns this course,
    # AND the course is mandatory, refuse.
    if student.class_id is not None:
        sc = db.session.get(SchoolClass, student.class_id)
        if sc and sc.grade_id == course.grade_id and not course.elective_group:
            return (
                jsonify(
                    {
                        "error": "This is a mandatory course for the student's current class. "
                        "Unassign the student from the class first."
                    }
                ),
                409,
            )
    e.status = "dropped"
    db.session.commit()
    return jsonify(e.to_dict()), 200
