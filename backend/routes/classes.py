"""Classes blueprint — admin CRUD for school-class sections.

Also exposes the class-course-teacher assignments (moved out of Phase 1's
courses.instructor_id shortcut).
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from models import (
    ClassCourseTeacher,
    Course,
    Enrollment,
    Grade,
    SchoolClass,
    User,
    db,
)
from routes.auth import current_user, login_required, require_admin
from utils.permissions import (
    can_assign_class_course_teacher,
    can_view_class_roster,
    homerooms_class,
    is_admin,
    is_instructor,
)
from utils.validation import (
    ValidationError,
    as_str,
    require_fields,
    require_json,
)
from utils.time import utc_now

classes_bp = Blueprint("classes", __name__)


def _validated_exclude_ids(raw) -> set[str]:
    """`excludeStudentIds` must be a list of strings — anything else is a
    payload error. Passing a bare string would `set("abc") -> {"a","b","c"}`
    and silently exclude the wrong students on a destructive graduate/promote
    call. Phase 9 audit fix F7.
    """
    if raw is None:
        return set()
    if not isinstance(raw, list):
        raise ValidationError("excludeStudentIds must be a list of student ids.")
    for x in raw:
        if not isinstance(x, str):
            raise ValidationError("excludeStudentIds entries must be strings.")
    return set(raw)


@classes_bp.route("", methods=["GET"])
@classes_bp.route("/", methods=["GET"])
@login_required
def list_classes():
    grade_id = (request.args.get("gradeId") or "").strip() or None
    q = SchoolClass.query
    if grade_id:
        q = q.filter_by(grade_id=grade_id)
    rows = q.order_by(SchoolClass.name.asc()).all()
    return jsonify([c.to_dict() for c in rows]), 200


@classes_bp.route("/<string:class_id>", methods=["GET"])
@login_required
def get_class(class_id: str):
    sc = db.session.get(SchoolClass, class_id)
    if sc is None:
        return jsonify({"error": "Class not found."}), 404
    # Phase 9 audit fix F1: only expose the roster (student names + emails)
    # to admin, homeroom, teachers of the class, and linked parents. Everyone
    # else gets the class metadata without the student list — the name is
    # public catalogue, the roster is PII.
    user = current_user()
    include_roster = can_view_class_roster(user, sc)
    return jsonify(sc.to_dict(include_roster=include_roster)), 200


@classes_bp.route("", methods=["POST"])
@classes_bp.route("/", methods=["POST"])
@require_admin
def create_class():
    try:
        payload = require_json(request.get_json(silent=True))
        require_fields(payload, ("gradeId", "name"))
        grade_id = as_str(payload["gradeId"], "gradeId")
        name = as_str(payload["name"], "name", max_len=80)
        homeroom_teacher_id = payload.get("homeroomTeacherId")
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400

    if db.session.get(Grade, grade_id) is None:
        return jsonify({"error": "gradeId does not exist."}), 400
    if SchoolClass.query.filter_by(grade_id=grade_id, name=name).first() is not None:
        return jsonify({"error": "A class with this name already exists in this grade."}), 409
    if homeroom_teacher_id:
        err = _validate_homeroom_teacher(homeroom_teacher_id, exclude_class_id=None)
        if err:
            return err

    sc = SchoolClass(grade_id=grade_id, name=name, homeroom_teacher_id=homeroom_teacher_id)
    db.session.add(sc)
    db.session.commit()
    return jsonify(sc.to_dict()), 201


def _validate_homeroom_teacher(teacher_id: str, *, exclude_class_id: str | None):
    """Returns a Flask (jsonify, code) tuple on error, or None on success."""
    user = db.session.get(User, teacher_id)
    if user is None or user.role != "instructor":
        return jsonify({"error": "homeroomTeacherId must refer to an instructor."}), 400
    # Enforce the one-homeroom-per-teacher invariant. Even though the DB has
    # a unique index, checking here gives a friendlier error message.
    q = SchoolClass.query.filter_by(homeroom_teacher_id=teacher_id)
    if exclude_class_id:
        q = q.filter(SchoolClass.id != exclude_class_id)
    other = q.first()
    if other is not None:
        return (
            jsonify(
                {
                    "error": f"This teacher already homerooms '{other.name}'. "
                    "A teacher can only be homeroom for one class."
                }
            ),
            409,
        )
    return None


@classes_bp.route("/<string:class_id>", methods=["PUT", "PATCH"])
@require_admin
def update_class(class_id: str):
    sc = db.session.get(SchoolClass, class_id)
    if sc is None:
        return jsonify({"error": "Class not found."}), 404
    try:
        payload = require_json(request.get_json(silent=True))
        if "name" in payload:
            new_name = as_str(payload["name"], "name", max_len=80)
            if new_name != sc.name and SchoolClass.query.filter_by(
                grade_id=sc.grade_id, name=new_name
            ).first():
                return jsonify({"error": "A class with this name already exists in this grade."}), 409
            sc.name = new_name
        if "homeroomTeacherId" in payload:
            htid = payload["homeroomTeacherId"]
            if htid is None or htid == "":
                sc.homeroom_teacher_id = None
            else:
                err = _validate_homeroom_teacher(htid, exclude_class_id=sc.id)
                if err:
                    return err
                sc.homeroom_teacher_id = htid
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400
    db.session.commit()
    return jsonify(sc.to_dict()), 200


@classes_bp.route("/<string:class_id>", methods=["DELETE"])
@require_admin
def delete_class(class_id: str):
    sc = db.session.get(SchoolClass, class_id)
    if sc is None:
        return jsonify({"error": "Class not found."}), 404
    if sc.students.count() > 0:
        return (
            jsonify({"error": "This class still has students. Unassign them first."}),
            409,
        )
    db.session.delete(sc)
    db.session.commit()
    return jsonify({"message": "Class deleted."}), 200


# =============================================================================
# Class → Course teacher assignments
# =============================================================================
@classes_bp.route("/<string:class_id>/courses", methods=["GET"])
@login_required
def list_class_courses(class_id: str):
    """Which courses are 'active' in this class, and who teaches each.

    In the K-12 curriculum model, "active in this class" means: the course
    belongs to this class's grade. We enrich with the teacher assigned to
    THIS class (nullable).
    """
    sc = db.session.get(SchoolClass, class_id)
    if sc is None:
        return jsonify({"error": "Class not found."}), 404

    courses = Course.query.filter_by(grade_id=sc.grade_id).order_by(Course.title.asc()).all()
    # Map course_id -> ClassCourseTeacher row for this class
    teacher_by_course: dict[str, ClassCourseTeacher] = {
        cct.course_id: cct
        for cct in ClassCourseTeacher.query.filter_by(class_id=sc.id).all()
    }
    out = []
    for c in courses:
        cct = teacher_by_course.get(c.id)
        d = c.to_dict()
        d["classTeacher"] = cct.to_dict() if cct else None
        out.append(d)
    return jsonify(out), 200


@classes_bp.route("/<string:class_id>/courses/<string:course_id>/teacher", methods=["PUT"])
@login_required
def assign_class_course_teacher(class_id: str, course_id: str):
    """Assign (or reassign) the teacher for `course` in `class`.

    Auth: admin OR the department leader for the course's (dept × section).
    """
    sc = db.session.get(SchoolClass, class_id)
    if sc is None:
        return jsonify({"error": "Class not found."}), 404
    course = db.session.get(Course, course_id)
    if course is None:
        return jsonify({"error": "Course not found."}), 404
    if course.grade_id != sc.grade_id:
        return (
            jsonify({"error": "This course is not part of this class's grade curriculum."}),
            400,
        )

    user = current_user()
    if not can_assign_class_course_teacher(user, course):
        return jsonify({"error": "You do not have permission to assign this course."}), 403

    try:
        payload = require_json(request.get_json(silent=True))
        require_fields(payload, ("teacherId",))
        teacher_id = as_str(payload["teacherId"], "teacherId")
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400

    teacher = db.session.get(User, teacher_id)
    if teacher is None or teacher.role != "instructor":
        return jsonify({"error": "teacherId must refer to an instructor."}), 400

    existing = ClassCourseTeacher.query.filter_by(course_id=course.id, class_id=sc.id).first()
    if existing:
        existing.teacher_id = teacher.id
        existing.assigned_by_id = user.id
    else:
        existing = ClassCourseTeacher(
            course_id=course.id,
            class_id=sc.id,
            teacher_id=teacher.id,
            assigned_by_id=user.id,
        )
        db.session.add(existing)
    db.session.commit()
    return jsonify(existing.to_dict()), 200


# ============================================================================
# End-of-year promotion + graduation
# ============================================================================
@classes_bp.route("/<string:class_id>/promote", methods=["POST"])
@require_admin
def promote_class(class_id: str):
    """Bulk-move students from `class_id` to `toClassId`.

    Body: { toClassId, excludeStudentIds?: [] }
    """
    from datetime import datetime as _dt

    from models import Enrollment
    from routes.students import (
        _auto_enroll_mandatory_for_grade,
        _soft_drop_all_active_enrollments,
    )

    src = db.session.get(SchoolClass, class_id)
    if src is None:
        return jsonify({"error": "Source class not found."}), 404

    try:
        payload = require_json(request.get_json(silent=True))
        require_fields(payload, ("toClassId",))
        to_class_id = as_str(payload["toClassId"], "toClassId")
        # Phase 9 audit fix F7: guard against a stringy `excludeStudentIds`.
        # `set("abc")` becomes `{"a","b","c"}` and silently wrong-excludes —
        # destructive on a promote/graduate call.
        excludes = _validated_exclude_ids(payload.get("excludeStudentIds"))
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400

    dst = db.session.get(SchoolClass, to_class_id)
    if dst is None:
        return jsonify({"error": "toClassId does not exist."}), 400
    if dst.grade_id == src.grade_id:
        return (
            jsonify({"error": "Destination class is in the same grade — that's not promotion."}),
            400,
        )

    # Sanity-check: destination should be the immediately-next grade by
    # order_index. Refuse otherwise (admin can leap manually with place_student).
    src_grade = db.session.get(Grade, src.grade_id)
    dst_grade = db.session.get(Grade, dst.grade_id)
    if (
        src_grade is not None
        and dst_grade is not None
        and dst_grade.order_index != src_grade.order_index + 1
    ):
        return (
            jsonify(
                {
                    "error": (
                        f"'{dst_grade.name}' is not the grade immediately after "
                        f"'{src_grade.name}'. Promote step-by-step, or move students "
                        f"individually via placement."
                    )
                }
            ),
            400,
        )

    admin = current_user()
    students = src.students.all()

    promoted = 0
    held = 0
    carried = 0

    for s in students:
        if s.id in excludes:
            held += 1
            continue

        # Snapshot student's active elective enrollments before we soft-drop.
        old_elective_courses = []
        for e in Enrollment.query.filter_by(student_id=s.id, status="active").all():
            c = db.session.get(Course, e.course_id)
            if c and c.elective_group:
                old_elective_courses.append(c)

        # Cross-grade move: soft-drop old, place, auto-enroll new mandatory.
        _soft_drop_all_active_enrollments(s)
        s.class_id = dst.id
        _auto_enroll_mandatory_for_grade(s, dst.grade_id, admin)

        # Carry-forward electives.
        for old_c in old_elective_courses:
            successor = Course.query.filter_by(
                grade_id=dst.grade_id,
                succeeds_course_id=old_c.id,
                elective_group=old_c.elective_group,
            ).first()
            if successor is None:
                continue
            db.session.add(
                Enrollment(
                    student_id=s.id,
                    course_id=successor.id,
                    status="active",
                    enrolled_via="elective_choice",
                    enrolled_by_id=admin.id,
                )
            )
            carried += 1

        promoted += 1

    db.session.commit()
    return (
        jsonify(
            {
                "promoted": promoted,
                "heldBack": held,
                "carriedForwardElectives": carried,
                "fromClass": src.name,
                "toClass": dst.name,
            }
        ),
        200,
    )


@classes_bp.route("/<string:class_id>/graduate", methods=["POST"])
@require_admin
def graduate_class(class_id: str):
    """Grade-12 flavor: soft-drop all enrollments + mark students graduated.

    Body: { excludeStudentIds?: [] }
    """
    from datetime import datetime as _dt

    from routes.students import _soft_drop_all_active_enrollments

    src = db.session.get(SchoolClass, class_id)
    if src is None:
        return jsonify({"error": "Class not found."}), 404

    payload = request.get_json(silent=True) or {}
    try:
        excludes = _validated_exclude_ids(payload.get("excludeStudentIds"))
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400

    students = src.students.all()
    graduated = 0
    held = 0
    graduated_ids: list[str] = []
    grade_id_snapshot = src.grade_id
    for s in students:
        if s.id in excludes:
            held += 1
            continue
        _soft_drop_all_active_enrollments(s)
        s.is_active = False
        s.graduated_at = utc_now()
        s.token_version = (s.token_version or 0) + 1  # invalidate live session
        s.class_id = None
        graduated += 1
        graduated_ids.append(s.id)
    db.session.commit()

    # Phase 32 · T2 — auto-issue diplomas.
    # Phase 33 fix #2 — narrower except: `issue_diploma` now savepoints
    # its own insert, so the only exceptions that reach here are logic
    # bugs. Log-and-continue instead of silent pass so a real bad row
    # surfaces in the server log.
    diplomas_issued = 0
    if graduated_ids:
        from utils.diplomas import issue_diploma
        for sid in graduated_ids:
            try:
                if issue_diploma(sid, grade_id=grade_id_snapshot) is not None:
                    diplomas_issued += 1
            except Exception as _diploma_err:  # pragma: no cover
                from flask import current_app as _app
                _app.logger.warning(
                    "issue_diploma failed for %s: %r", sid, _diploma_err,
                )
        db.session.commit()

    return jsonify({
        "graduated": graduated,
        "heldBack": held,
        "diplomasIssued": diplomas_issued,
    }), 200


@classes_bp.route("/<string:class_id>/courses/<string:course_id>/teacher", methods=["DELETE"])
@login_required
def unassign_class_course_teacher(class_id: str, course_id: str):
    sc = db.session.get(SchoolClass, class_id)
    if sc is None:
        return jsonify({"error": "Class not found."}), 404
    course = db.session.get(Course, course_id)
    if course is None:
        return jsonify({"error": "Course not found."}), 404
    user = current_user()
    if not can_assign_class_course_teacher(user, course):
        return jsonify({"error": "You do not have permission."}), 403
    row = ClassCourseTeacher.query.filter_by(course_id=course.id, class_id=sc.id).first()
    if row:
        db.session.delete(row)
        db.session.commit()
    return jsonify({"message": "Unassigned."}), 200
