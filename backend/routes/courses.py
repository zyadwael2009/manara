"""Course CRUD + catalog.

Phase 2 changes vs Phase 1:
  * `POST /api/courses` now admin-only. gradeId REQUIRED; electiveGroup optional.
  * gradeId is NOT editable after creation (would break every existing enrollment).
  * `GET /api/courses/<id>` now enriches with myEnrollment when the caller is
    a student, and respects the extended content gate.
  * The catalog reads add `isEnrolled` per item for signed-in students.
  * `GET /api/courses/mine` for admin/instructor now uses the class_course_teachers
    join instead of the retired courses.instructor_id shortcut.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from flask import Blueprint, jsonify, request
from sqlalchemy import or_

from models import (
    Certificate,
    ClassCourseTeacher,
    Course,
    Enrollment,
    Grade,
    COURSE_STATUSES,
    User,
    db,
)
from routes.auth import current_user, login_required, require_admin, require_role
from utils.permissions import (
    can_edit_course_content,
    can_view_content,
    is_admin,
    is_instructor,
    is_student,
    teaches_course_in_any_class,
)
from utils.validation import (
    ValidationError,
    as_str,
    require_fields,
    require_json,
)

courses_bp = Blueprint("courses", __name__)


# =============================================================================
# Catalog reads
# =============================================================================
@courses_bp.route("", methods=["GET"])
@courses_bp.route("/", methods=["GET"])
def list_courses():
    """List published courses. For a signed-in student, adds `isEnrolled` per item."""
    q = Course.query.filter(Course.status == "published")

    search = (request.args.get("search") or "").strip()
    if search:
        pattern = f"%{search}%"
        q = q.filter(or_(Course.title.ilike(pattern), Course.description.ilike(pattern)))

    category = (request.args.get("category") or "").strip()
    if category:
        q = q.filter(Course.category == category)

    grade_id = (request.args.get("gradeId") or "").strip()
    if grade_id:
        q = q.filter(Course.grade_id == grade_id)

    rows = q.order_by(Course.created_at.desc()).all()

    # For signed-in students, decorate with isEnrolled.
    user = current_user()
    enrolled_ids: set[str] = set()
    if is_student(user):
        for e in Enrollment.query.filter_by(student_id=user.id).filter(
            Enrollment.status.in_(("active", "completed"))
        ):
            enrolled_ids.add(e.course_id)

    out = []
    for c in rows:
        d = c.to_dict()
        d["isEnrolled"] = c.id in enrolled_ids
        out.append(d)
    return jsonify(out), 200


@courses_bp.route("/mine", methods=["GET"])
@courses_bp.route("/mine/", methods=["GET"])
@require_role("instructor", "admin")
def list_my_courses():
    """Instructor's own courses (via class_course_teachers). Admins see all."""
    user = current_user()
    if is_admin(user):
        rows = Course.query.order_by(Course.title.asc()).all()
    else:
        # Distinct courses this teacher is assigned to teach in any class.
        course_ids = {
            cct.course_id
            for cct in ClassCourseTeacher.query.filter_by(teacher_id=user.id).all()
        }
        if not course_ids:
            rows = []
        else:
            rows = (
                Course.query.filter(Course.id.in_(course_ids))
                .order_by(Course.title.asc())
                .all()
            )
    return jsonify([c.to_dict() for c in rows]), 200


@courses_bp.route("/<string:course_id>", methods=["GET"])
def get_course(course_id: str):
    """Course detail. Content hidden unless caller passes `can_view_content`."""
    course = db.session.get(Course, course_id)
    if course is None:
        return jsonify({"error": "Course not found."}), 404

    user = current_user()
    # Draft courses are only visible to those who can edit them.
    if course.status != "published" and not can_edit_course_content(user, course):
        return jsonify({"error": "Course not found."}), 404

    my_enrollment = None
    if is_student(user):
        my_enrollment = Enrollment.query.filter_by(
            student_id=user.id, course_id=course.id
        ).first()

    hide = not can_view_content(user, course)
    data = course.to_dict(
        include_modules=True,
        hide_content=hide,
        my_enrollment=my_enrollment,
        # Phase 16: decorate every module quiz summary with the student's
        # own last/best mark + attempt count. Only for students who have
        # a live enrollment — teachers/admins don't take quizzes.
        student_id=(user.id if is_student(user) and my_enrollment else None),
    )

    # For admin / any teacher of the course, add enrolledCount + class assignments.
    if is_admin(user) or teaches_course_in_any_class(user, course):
        data["enrolledCount"] = (
            Enrollment.query.filter_by(course_id=course.id)
            .filter(Enrollment.status.in_(("active", "completed")))
            .count()
        )
        data["classAssignments"] = [
            cct.to_dict()
            for cct in ClassCourseTeacher.query.filter_by(course_id=course.id).all()
        ]
    return jsonify(data), 200


# =============================================================================
# Writes — admin creates the shell; content edit follows dept-leader rules
# =============================================================================
def _enriched_dict(course: Course, user: User | None) -> dict:
    """Same shape as `GET /api/courses/<id>` returns, sans modules.

    Phase 10 audit fix M7: create/update/publish/unpublish used to return a
    bare `course.to_dict()` — no `myEnrollment`, no `enrolledCount` — so a
    student who published a course they were enrolled in saw the Enroll CTA
    flip back on until a full refresh. Now every write returns the same
    envelope shape as the corresponding read.
    """
    my_enrollment = None
    if is_student(user):
        my_enrollment = Enrollment.query.filter_by(
            student_id=user.id, course_id=course.id,
        ).first()
    data = course.to_dict(my_enrollment=my_enrollment)
    if is_admin(user) or teaches_course_in_any_class(user, course):
        data["enrolledCount"] = (
            Enrollment.query.filter_by(course_id=course.id)
            .filter(Enrollment.status.in_(("active", "completed")))
            .count()
        )
    return data


def _parse_price(raw) -> Decimal:
    if raw is None or raw == "":
        return Decimal("0")
    try:
        price = Decimal(str(raw))
    except (InvalidOperation, ValueError) as e:
        raise ValidationError("'price' must be a number.") from e
    if price < 0:
        raise ValidationError("'price' cannot be negative.")
    return price.quantize(Decimal("0.01"))


@courses_bp.route("", methods=["POST"])
@courses_bp.route("/", methods=["POST"])
@require_admin
def create_course():
    """Admin creates a course. gradeId REQUIRED. electiveGroup optional.

    The admin may set `instructorId` to hint at a lead author, but the real
    per-class teacher assignment happens via classes.py.
    """
    try:
        payload = require_json(request.get_json(silent=True))
        require_fields(payload, ("title", "gradeId"))
        title = as_str(payload["title"], "title", max_len=200)
        grade_id = as_str(payload["gradeId"], "gradeId")
        description = as_str(payload.get("description", ""), "description", max_len=10_000)
        category = as_str(payload.get("category", "general"), "category", max_len=80).lower() or "general"
        elective_group = payload.get("electiveGroup")
        if elective_group is not None:
            elective_group = as_str(elective_group, "electiveGroup", max_len=80).lower() or None
        thumbnail_url = payload.get("thumbnailUrl")
        if thumbnail_url is not None:
            thumbnail_url = as_str(thumbnail_url, "thumbnailUrl", max_len=500) or None
        price = _parse_price(payload.get("price"))
        instructor_id = payload.get("instructorId")
        succeeds_course_id = payload.get("succeedsCourseId")
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400

    if db.session.get(Grade, grade_id) is None:
        return jsonify({"error": "gradeId does not exist."}), 400

    if instructor_id:
        target = db.session.get(User, instructor_id)
        if target is None or target.role not in ("instructor", "admin"):
            return jsonify({"error": "instructorId must refer to an instructor or admin."}), 400

    if succeeds_course_id:
        prereq = db.session.get(Course, succeeds_course_id)
        if prereq is None:
            return jsonify({"error": "succeedsCourseId does not exist."}), 400
    course = Course(
        title=title,
        description=description,
        grade_id=grade_id,
        elective_group=elective_group,
        instructor_id=instructor_id,
        succeeds_course_id=succeeds_course_id,
        price=price,
        category=category,
        thumbnail_url=thumbnail_url,
        status="draft",
    )
    db.session.add(course)
    db.session.commit()
    return jsonify(_enriched_dict(course, current_user())), 201


@courses_bp.route("/<string:course_id>", methods=["PUT", "PATCH"])
@login_required
def update_course(course_id: str):
    course = db.session.get(Course, course_id)
    if course is None:
        return jsonify({"error": "Course not found."}), 404
    user = current_user()
    if not can_edit_course_content(user, course):
        return jsonify({"error": "You do not have permission to edit this course."}), 403

    try:
        payload = require_json(request.get_json(silent=True))
        if "title" in payload:
            course.title = as_str(payload["title"], "title", max_len=200)
        if "description" in payload:
            course.description = as_str(payload["description"], "description", max_len=10_000)
        if "category" in payload:
            course.category = (as_str(payload["category"], "category", max_len=80).lower() or "general")
        if "electiveGroup" in payload:
            eg = payload["electiveGroup"]
            course.elective_group = (
                None if eg in (None, "") else as_str(eg, "electiveGroup", max_len=80).lower()
            )
        if "thumbnailUrl" in payload:
            tu = payload["thumbnailUrl"]
            course.thumbnail_url = None if tu in (None, "") else as_str(tu, "thumbnailUrl", max_len=500)
        if "price" in payload:
            course.price = _parse_price(payload["price"])
        if "gradeId" in payload and payload["gradeId"] != course.grade_id:
            return (
                jsonify(
                    {"error": "gradeId cannot be changed after creation (would break enrollments)."}
                ),
                400,
            )
        if "status" in payload:
            return jsonify({"error": "Use POST /courses/<id>/publish to change status."}), 400
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400

    db.session.commit()
    return jsonify(_enriched_dict(course, user)), 200


@courses_bp.route("/<string:course_id>", methods=["DELETE"])
@require_admin
def delete_course(course_id: str):
    """Admin-only delete (moved from Phase 1's owner-instructor rule).

    Cascades to modules → lessons → enrollments. Refused if any active
    enrollment exists (would silently strip students).
    """
    course = db.session.get(Course, course_id)
    if course is None:
        return jsonify({"error": "Course not found."}), 404
    active = (
        Enrollment.query.filter_by(course_id=course.id)
        .filter(Enrollment.status == "active")
        .count()
    )
    if active > 0:
        return (
            jsonify(
                {
                    "error": f"This course has {active} active enrollment(s). "
                    "Drop the enrollments first."
                }
            ),
            409,
        )
    # Phase 5: refuse if any non-revoked certificate points at this course
    # (via an enrollment). Preserves historical integrity of issued certs.
    live_certs = (
        db.session.query(Certificate)
        .join(Enrollment, Enrollment.id == Certificate.enrollment_id)
        .filter(Enrollment.course_id == course.id, Certificate.revoked.is_(False))
        .count()
    )
    if live_certs > 0:
        return (
            jsonify(
                {
                    "error": f"This course has {live_certs} issued certificate(s). "
                    "Revoke them first."
                }
            ),
            409,
        )
    db.session.delete(course)
    db.session.commit()
    return jsonify({"message": "Course deleted."}), 200


@courses_bp.route("/<string:course_id>/publish", methods=["POST"])
@login_required
def publish_course(course_id: str):
    course = db.session.get(Course, course_id)
    if course is None:
        return jsonify({"error": "Course not found."}), 404
    if not can_edit_course_content(current_user(), course):
        return jsonify({"error": "You do not have permission."}), 403

    total_lessons = sum(m.lessons.count() for m in course.modules)
    if course.modules.count() == 0 or total_lessons == 0:
        return (
            jsonify(
                {
                    "error": "A course needs at least one module with at least one lesson before it can be published."
                }
            ),
            400,
        )
    course.status = "published"
    db.session.commit()
    return jsonify(_enriched_dict(course, current_user())), 200


@courses_bp.route("/<string:course_id>/unpublish", methods=["POST"])
@login_required
def unpublish_course(course_id: str):
    course = db.session.get(Course, course_id)
    if course is None:
        return jsonify({"error": "Course not found."}), 404
    if not can_edit_course_content(current_user(), course):
        return jsonify({"error": "You do not have permission."}), 403
    course.status = "draft"
    db.session.commit()
    return jsonify(_enriched_dict(course, current_user())), 200
