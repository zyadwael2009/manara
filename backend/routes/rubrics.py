"""Per-course rubric — GET (any signed-in) + PUT (can_edit_course_content).

Server INVARIANT: sum of maxScore across a rubric MUST equal 100. Reject
otherwise with the exact diff.
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from models import Course, CourseRubric, Enrollment, GradeCategory, db
from routes.auth import current_user, login_required
from utils.certificates import maybe_issue_certificate
from utils.grading import recompute_enrollment_cache, validate_rubric_sum
from utils.permissions import can_edit_course_content
from utils.validation import (
    ValidationError,
    as_int,
    require_json,
)

rubrics_bp = Blueprint("rubrics", __name__)


@rubrics_bp.route("/courses/<string:course_id>/rubric", methods=["GET"])
@login_required
def get_rubric(course_id: str):
    course = db.session.get(Course, course_id)
    if course is None:
        return jsonify({"error": "Course not found."}), 404
    rows = (
        CourseRubric.query.filter_by(course_id=course.id)
        .order_by(CourseRubric.order_index.asc())
        .all()
    )
    return jsonify([r.to_dict() for r in rows]), 200


@rubrics_bp.route("/courses/<string:course_id>/rubric", methods=["PUT"])
@login_required
def set_rubric(course_id: str):
    """Replace the entire rubric for a course.

    Body: { items: [{ gradeCategoryId, maxScore, orderIndex? }, ...] }

    Enforces sum(maxScore) == 100. Recomputes every enrollment's cache
    after a successful update.
    """
    course = db.session.get(Course, course_id)
    if course is None:
        return jsonify({"error": "Course not found."}), 404
    user = current_user()
    if not can_edit_course_content(user, course):
        return jsonify({"error": "You do not have permission to edit this course's rubric."}), 403

    try:
        payload = require_json(request.get_json(silent=True))
        items = payload.get("items")
        if not isinstance(items, list):
            raise ValidationError("Body must contain an `items` array.")
        for it in items:
            if not isinstance(it, dict):
                raise ValidationError("Each item must be an object.")
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400

    err = validate_rubric_sum(course.id, items)
    if err:
        return jsonify({"error": err}), 400

    # Validate each category exists.
    for it in items:
        cid = it.get("gradeCategoryId")
        max_score = int(it.get("maxScore") or 0)
        if not cid or db.session.get(GradeCategory, cid) is None:
            return jsonify({"error": f"gradeCategoryId '{cid}' does not exist."}), 400
        if max_score <= 0:
            return jsonify({"error": "Each maxScore must be > 0."}), 400

    had_entries_before = False
    for r in CourseRubric.query.filter_by(course_id=course.id).all():
        had_entries_before = True
        break

    # Wipe existing rubric then re-insert.
    CourseRubric.query.filter_by(course_id=course.id).delete()
    for i, it in enumerate(items):
        r = CourseRubric(
            course_id=course.id,
            grade_category_id=it["gradeCategoryId"],
            max_score=int(it["maxScore"]),
            order_index=int(it.get("orderIndex") or i),
        )
        db.session.add(r)

    # Recompute every enrollment's cache since maxima have changed.
    # A rubric change can also open (or fail to open) the cert gate.
    for e in Enrollment.query.filter_by(course_id=course.id).all():
        recompute_enrollment_cache(e)
        maybe_issue_certificate(e)

    db.session.commit()

    rows = (
        CourseRubric.query.filter_by(course_id=course.id)
        .order_by(CourseRubric.order_index.asc())
        .all()
    )
    out = {"items": [r.to_dict() for r in rows]}
    if had_entries_before:
        out["warning"] = (
            "Grade entries existed before this rubric change. Every affected "
            "enrollment's cached percentage / letter / GPA has been recomputed."
        )
    return jsonify(out), 200
