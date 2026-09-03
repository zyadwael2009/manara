"""Students blueprint — class placement + elective picks.

Two admin verbs on a student:
  * Placement — PUT /api/users/<id>/class  (writes users.class_id + auto-enrollments)
  * Elective  — PUT /api/users/<id>/electives/<group>

Homeroom teachers can pick electives for their own homeroom students; admin
can do anything. See `permissions.can_pick_elective_for`.
"""
from __future__ import annotations

from datetime import date as _date, datetime

from flask import Blueprint, jsonify, request

from models import (
    Course,
    Enrollment,
    Grade,
    ParentStudentLink,
    SchoolClass,
    User,
    WithdrawalLog,
    db,
)
from routes.auth import current_user, login_required, require_admin
from utils.permissions import can_pick_elective_for
from utils.validation import (
    ValidationError,
    as_str,
    require_fields,
    require_json,
)
from utils.time import utc_now

students_bp = Blueprint("students", __name__)


# =============================================================================
# Placement
# =============================================================================
def _auto_enroll_mandatory_for_grade(
    student: User, grade_id: str | None, by_user: User
) -> list[Enrollment]:
    """Create (or reactivate) enrollments for every mandatory course in
    the target grade. Returns the enrollment rows written or reactivated.
    Idempotent — existing active rows are left alone.
    """
    if grade_id is None:
        return []
    courses = Course.query.filter_by(grade_id=grade_id, elective_group=None).all()
    written: list[Enrollment] = []
    for c in courses:
        existing = Enrollment.query.filter_by(student_id=student.id, course_id=c.id).first()
        if existing is None:
            e = Enrollment(
                student_id=student.id,
                course_id=c.id,
                status="active",
                enrolled_via="auto_mandatory",
                enrolled_by_id=by_user.id,
            )
            db.session.add(e)
            written.append(e)
        elif existing.status == "dropped":
            existing.status = "active"
            existing.enrolled_via = "auto_mandatory"
            existing.enrolled_by_id = by_user.id
            existing.enrolled_at = utc_now()
            existing.completed_at = None
            written.append(existing)
    return written


def _soft_drop_all_active_enrollments(student: User) -> int:
    """Mark every active enrollment for this student as 'dropped'. Returns
    the count. Used when the student moves to a different grade (whole
    curriculum swap)."""
    n = 0
    for e in Enrollment.query.filter_by(student_id=student.id, status="active").all():
        e.status = "dropped"
        n += 1
    return n


@students_bp.route("/<string:student_id>/class", methods=["PUT"])
@require_admin
def place_student_in_class(student_id: str):
    """Set/change users.class_id. Same-grade re-placement = no enrollment
    changes; different-grade re-placement = soft-drop old + auto-create
    new mandatory rows.

    Body: { classId }        — place into this class
    Or:   { classId, dryRun: true }   — return the diff without applying
    """
    student = db.session.get(User, student_id)
    if student is None or student.role != "student":
        return jsonify({"error": "Student not found."}), 404

    try:
        payload = require_json(request.get_json(silent=True))
        require_fields(payload, ("classId",))
        class_id = as_str(payload["classId"], "classId")
        dry_run = bool(payload.get("dryRun", False))
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400

    new_class = db.session.get(SchoolClass, class_id)
    if new_class is None:
        return jsonify({"error": "classId does not exist."}), 400

    old_class_id = student.class_id
    old_class = db.session.get(SchoolClass, old_class_id) if old_class_id else None
    same_grade = (
        old_class is not None and old_class.grade_id == new_class.grade_id
    )
    diff = {
        "sameClass": old_class_id == new_class.id,
        "sameGrade": same_grade,
        "oldClassId": old_class_id,
        "newClassId": new_class.id,
        "willDropEnrollments": 0,
        "willAutoEnroll": 0,
    }

    if old_class_id == new_class.id:
        return jsonify(diff), 200  # No-op

    if same_grade:
        # Same-grade move — no enrollment changes.
        if not dry_run:
            student.class_id = new_class.id
            db.session.commit()
        return jsonify(diff), 200

    # Different grade (or student was unassigned). Compute the diff.
    active_count = Enrollment.query.filter_by(student_id=student.id, status="active").count()
    would_add = Course.query.filter_by(
        grade_id=new_class.grade_id, elective_group=None
    ).count()
    diff["willDropEnrollments"] = active_count if old_class is not None else 0
    diff["willAutoEnroll"] = would_add

    if dry_run:
        return jsonify(diff), 200

    admin = current_user()
    if old_class is not None:
        _soft_drop_all_active_enrollments(student)
    student.class_id = new_class.id
    _auto_enroll_mandatory_for_grade(student, new_class.grade_id, admin)
    db.session.commit()
    return jsonify(diff), 200


@students_bp.route("/<string:student_id>/class", methods=["DELETE"])
@require_admin
def unassign_student_from_class(student_id: str):
    student = db.session.get(User, student_id)
    if student is None or student.role != "student":
        return jsonify({"error": "Student not found."}), 404
    if student.class_id is None:
        return jsonify({"message": "Student was not in a class."}), 200
    _soft_drop_all_active_enrollments(student)
    student.class_id = None
    db.session.commit()
    return jsonify({"message": "Unassigned."}), 200


# =============================================================================
# Electives
# =============================================================================
def _pending_elective_groups(student: User) -> list[dict]:
    """Every elective group in the student's grade that they don't have an
    active pick for. Returns a list ready to serialize.
    """
    if student.class_id is None:
        return []
    sc = db.session.get(SchoolClass, student.class_id)
    if sc is None:
        return []
    grade_id = sc.grade_id
    all_electives = (
        Course.query.filter(Course.grade_id == grade_id, Course.elective_group.isnot(None)).all()
    )
    # Group courses by their elective_group tag.
    groups: dict[str, list[Course]] = {}
    for c in all_electives:
        groups.setdefault(c.elective_group, []).append(c)

    # Which groups does the student already have an active enrollment for?
    active_group_tags = set()
    active_enrolls = Enrollment.query.filter_by(student_id=student.id, status="active").all()
    for e in active_enrolls:
        c = db.session.get(Course, e.course_id)
        if c and c.elective_group:
            active_group_tags.add(c.elective_group)

    out = []
    for tag, options in sorted(groups.items()):
        if tag in active_group_tags:
            continue
        out.append(
            {
                "group": tag,
                "options": [
                    {"courseId": c.id, "title": c.title, "instructorName": c.instructor.name if c.instructor else None}
                    for c in options
                ],
            }
        )
    return out


@students_bp.route("/<string:student_id>/electives/pending", methods=["GET"])
@login_required
def get_pending_electives(student_id: str):
    """List elective groups for the student that have no active pick yet.

    Visible to: admin, homeroom teacher of student's class, student themself,
    linked parent (Phase 6 will complete this).
    """
    student = db.session.get(User, student_id)
    if student is None or student.role != "student":
        return jsonify({"error": "Student not found."}), 404
    user = current_user()
    from utils.permissions import can_view_student_records
    if not can_view_student_records(user, student):
        return jsonify({"error": "You do not have permission."}), 403
    return jsonify(_pending_elective_groups(student)), 200


@students_bp.route("/<string:student_id>/electives/<string:group>", methods=["PUT"])
@login_required
def set_elective(student_id: str, group: str):
    """Pick (or switch) the student's course for the given elective group.

    Body: { courseId }
    Auth: admin OR homeroom teacher of student's class.
    """
    student = db.session.get(User, student_id)
    if student is None or student.role != "student":
        return jsonify({"error": "Student not found."}), 404
    user = current_user()
    if not can_pick_elective_for(user, student):
        return jsonify({"error": "You do not have permission."}), 403
    if student.class_id is None:
        return jsonify({"error": "Student is not placed in a class."}), 400

    try:
        payload = require_json(request.get_json(silent=True))
        require_fields(payload, ("courseId",))
        course_id = as_str(payload["courseId"], "courseId")
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400

    course = db.session.get(Course, course_id)
    if course is None:
        return jsonify({"error": "courseId does not exist."}), 400
    # Grade must match the student's class's grade.
    sc = db.session.get(SchoolClass, student.class_id)
    if course.grade_id != sc.grade_id:
        return (
            jsonify({"error": "This course is not part of the student's grade."}),
            400,
        )
    if course.elective_group != group:
        return (
            jsonify({"error": f"This course does not belong to the '{group}' elective group."}),
            400,
        )

    # Idempotency + soft-drop of any prior active pick for the same group.
    prior_enrollments = (
        db.session.query(Enrollment)
        .join(Course, Course.id == Enrollment.course_id)
        .filter(
            Enrollment.student_id == student.id,
            Enrollment.status == "active",
            Course.elective_group == group,
            Course.grade_id == sc.grade_id,
        )
        .all()
    )
    for pe in prior_enrollments:
        if pe.course_id == course.id:
            # Idempotent — student is already enrolled in this exact course.
            return jsonify(pe.to_dict()), 200
        pe.status = "dropped"  # progress preserved

    e = Enrollment(
        student_id=student.id,
        course_id=course.id,
        status="active",
        enrolled_via="elective_choice",
        enrolled_by_id=user.id,
    )
    db.session.add(e)
    db.session.commit()
    return jsonify(e.to_dict()), 201


# =============================================================================
# Phase 6 — Parent link management (admin only)
#
# Parents are created via POST /api/users (admin) then linked here. Self-
# registration into role='parent' is refused in routes/auth.py; the only
# path to a parent account or a link is admin-driven.
# =============================================================================
def _student_or_404(student_id: str):
    student = db.session.get(User, student_id)
    if student is None or student.role != "student":
        return None, (jsonify({"error": "Student not found."}), 404)
    return student, None


@students_bp.route("/<string:student_id>/parents", methods=["GET"])
@require_admin
def list_student_parents(student_id: str):
    student, err = _student_or_404(student_id)
    if err is not None:
        return err
    rows = (
        db.session.query(ParentStudentLink, User)
        .join(User, User.id == ParentStudentLink.parent_id)
        .filter(ParentStudentLink.student_id == student.id)
        .order_by(User.name.asc())
        .all()
    )
    return jsonify([
        {
            "linkId": link.id,
            "parentId": parent.id,
            "name": parent.name,
            "email": parent.email,
            "relationship": link.relationship_type,
            "linkCreatedAt": link.created_at.isoformat() + "Z" if link.created_at else None,
        }
        for link, parent in rows
    ]), 200


@students_bp.route("/<string:student_id>/parents", methods=["POST"])
@require_admin
def link_parent_to_student(student_id: str):
    student, err = _student_or_404(student_id)
    if err is not None:
        return err
    try:
        payload = require_json(request.get_json(silent=True))
        require_fields(payload, ("parentId",))
        parent_id = as_str(payload["parentId"], "parentId")
        relationship = as_str(
            payload.get("relationship") or "guardian",
            "relationship",
            max_len=20,
        )
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400

    parent = db.session.get(User, parent_id)
    if parent is None or parent.role != "parent" or not parent.is_active:
        return jsonify({"error": "parentId must refer to an active parent."}), 400
    existing = ParentStudentLink.query.filter_by(
        parent_id=parent.id, student_id=student.id
    ).first()
    if existing is not None:
        return jsonify({"error": "This parent is already linked to this student."}), 409

    link = ParentStudentLink(
        parent_id=parent.id,
        student_id=student.id,
        relationship_type=relationship,
    )
    db.session.add(link)
    db.session.commit()
    return jsonify(link.to_dict()), 201


@students_bp.route(
    "/<string:student_id>/parents/<string:parent_id>", methods=["DELETE"]
)
@require_admin
def unlink_parent_from_student(student_id: str, parent_id: str):
    student, err = _student_or_404(student_id)
    if err is not None:
        return err
    link = ParentStudentLink.query.filter_by(
        parent_id=parent_id, student_id=student.id
    ).first()
    if link is None:
        return jsonify({"error": "Link not found."}), 404
    db.session.delete(link)
    db.session.commit()
    # Phase 11 audit fix L5: match the {"message": "..."} envelope every
    # other terminal delete uses in this codebase.
    return jsonify({"message": "Unlinked."}), 200


# =============================================================================
# Phase 23 — Withdraw / transfer student (soft-delete + audit log)
#
# Preserves every historical row (grades, certificates, attendance,
# enrollments — they're soft-dropped, not deleted). Auth: admin only.
# =============================================================================
@students_bp.route("/<string:student_id>/withdraw", methods=["POST"])
@require_admin
def withdraw_student(student_id: str):
    """Body: `{reason?, effectiveDate?}`. Soft-deletes:
      * user.is_active = False
      * user.withdrawn_at = now
      * user.class_id = None
      * all active enrollments soft-dropped
      * one WithdrawalLog row written

    All history preserved.
    """
    student = db.session.get(User, student_id)
    if student is None or student.role != "student":
        return jsonify({"error": "Student not found."}), 404
    if not student.is_active:
        return jsonify({"error": "Student is already inactive."}), 409

    admin = current_user()
    payload = request.get_json(silent=True) or {}
    reason = payload.get("reason")
    # Phase 25 hard-audit fix: guard as_str so non-string reasons
    # (e.g. `{"reason": 5}`) return 400, not a 500 via unhandled
    # ValidationError.
    if reason is not None:
        try:
            reason = as_str(reason, "reason", max_len=500)
        except ValidationError as e:
            return jsonify({"error": str(e)}), 400

    eff_raw = payload.get("effectiveDate")
    effective_date = _date.today()
    if eff_raw:
        try:
            effective_date = _date.fromisoformat(str(eff_raw))
        except (TypeError, ValueError):
            return jsonify({"error": "effectiveDate must be YYYY-MM-DD."}), 400

    prior_class_id = student.class_id

    # Soft-drop enrollments via the existing helper.
    dropped = _soft_drop_all_active_enrollments(student)

    student.is_active = False
    student.withdrawn_at = utc_now()
    student.class_id = None
    # Bump token_version so any live session for this user is invalidated.
    student.token_version = (student.token_version or 0) + 1
    # Phase 25 hard-audit fix: clear the ICS calendar token so a
    # previously-shared subscription URL stops feeding data. If a
    # future admin flow re-activates the account, a fresh token is
    # issued rather than silently reactivating the old URL.
    student.calendar_token = None

    log = WithdrawalLog(
        student_id=student.id,
        admin_id=admin.id,
        reason=reason,
        effective_date=effective_date,
        prior_class_id=prior_class_id,
    )
    db.session.add(log)
    db.session.commit()

    return jsonify({
        "student": student.to_dict(),
        "log": log.to_dict(),
        "droppedEnrollments": dropped,
    }), 200
