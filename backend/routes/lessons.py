"""Lesson CRUD + single-lesson-read gated by the content-view rule."""
from __future__ import annotations

from flask import Blueprint, jsonify, request
from sqlalchemy import func

from models import LESSON_TYPES, Lesson, Module, db
from routes.auth import current_user, login_required
from utils.permissions import (
    can_edit_lesson,
    can_edit_module,
    can_view_lesson_content,
)
from utils.validation import (
    ValidationError,
    as_int,
    as_str,
    one_of,
    require_fields,
    require_json,
)

lessons_bp = Blueprint("lessons", __name__)


# =============================================================================
# Read — used by the student's lesson viewer + teacher's content editor
# =============================================================================
@lessons_bp.route("/lessons/<string:lesson_id>", methods=["GET"])
@login_required
def get_lesson(lesson_id: str):
    lesson = db.session.get(Lesson, lesson_id)
    if lesson is None:
        return jsonify({"error": "Lesson not found."}), 404
    user = current_user()
    if not can_view_lesson_content(user, lesson):
        return jsonify({"error": "You do not have permission to view this lesson."}), 403
    return jsonify(lesson.to_dict(hide_content=False)), 200


# =============================================================================
# Writes
# =============================================================================
@lessons_bp.route("/modules/<string:module_id>/lessons", methods=["POST"])
@login_required
def create_lesson(module_id: str):
    module = db.session.get(Module, module_id)
    if module is None:
        return jsonify({"error": "Module not found."}), 404
    if not can_edit_module(current_user(), module):
        return jsonify({"error": "You do not have permission to modify this module."}), 403

    try:
        payload = require_json(request.get_json(silent=True))
        require_fields(payload, ("title", "type"))
        title = as_str(payload["title"], "title", max_len=200)
        ltype = one_of(payload["type"], LESSON_TYPES, "type")
        content_url = payload.get("contentUrl")
        content_text = payload.get("contentText")
        if content_url is not None:
            content_url = as_str(content_url, "contentUrl", max_len=1000) or None
        if content_text is not None:
            content_text = as_str(content_text, "contentText", max_len=100_000) or None
        if ltype in ("video", "pdf") and not content_url:
            raise ValidationError(f"Lesson type '{ltype}' requires 'contentUrl'.")
        if ltype == "text" and not content_text:
            raise ValidationError("Text lessons require 'contentText'.")
        duration = payload.get("durationMinutes")
        duration_minutes = None if duration in (None, "") else as_int(duration, "durationMinutes")
        order_index = as_int(payload.get("orderIndex"), "orderIndex", default=-1)
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400

    if order_index < 0:
        last = db.session.query(func.max(Lesson.order_index)).filter_by(module_id=module.id).scalar()
        order_index = 0 if last is None else last + 1

    lesson = Lesson(
        module_id=module.id,
        title=title,
        type=ltype,
        content_url=content_url,
        content_text=content_text,
        duration_minutes=duration_minutes,
        order_index=order_index,
    )
    db.session.add(lesson)
    db.session.commit()
    return jsonify(lesson.to_dict(hide_content=False)), 201


@lessons_bp.route("/lessons/<string:lesson_id>", methods=["PUT", "PATCH"])
@login_required
def update_lesson(lesson_id: str):
    lesson = db.session.get(Lesson, lesson_id)
    if lesson is None:
        return jsonify({"error": "Lesson not found."}), 404
    if not can_edit_lesson(current_user(), lesson):
        return jsonify({"error": "You do not have permission to edit this lesson."}), 403

    try:
        payload = require_json(request.get_json(silent=True))
        if "title" in payload:
            lesson.title = as_str(payload["title"], "title", max_len=200)
        if "type" in payload:
            lesson.type = one_of(payload["type"], LESSON_TYPES, "type")
        if "contentUrl" in payload:
            v = payload["contentUrl"]
            lesson.content_url = None if v in (None, "") else as_str(v, "contentUrl", max_len=1000)
        if "contentText" in payload:
            v = payload["contentText"]
            lesson.content_text = None if v in (None, "") else as_str(v, "contentText", max_len=100_000)
        if "durationMinutes" in payload:
            v = payload["durationMinutes"]
            lesson.duration_minutes = None if v in (None, "") else as_int(v, "durationMinutes")
        if "orderIndex" in payload:
            lesson.order_index = as_int(payload["orderIndex"], "orderIndex")

        if lesson.type in ("video", "pdf") and not lesson.content_url:
            raise ValidationError(f"Lesson type '{lesson.type}' requires 'contentUrl'.")
        if lesson.type == "text" and not lesson.content_text:
            raise ValidationError("Text lessons require 'contentText'.")
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400

    db.session.commit()
    return jsonify(lesson.to_dict(hide_content=False)), 200


@lessons_bp.route("/lessons/<string:lesson_id>", methods=["DELETE"])
@login_required
def delete_lesson(lesson_id: str):
    lesson = db.session.get(Lesson, lesson_id)
    if lesson is None:
        return jsonify({"error": "Lesson not found."}), 404
    if not can_edit_lesson(current_user(), lesson):
        return jsonify({"error": "You do not have permission to delete this lesson."}), 403
    # Phase 9 audit fix F5: same shape as delete_module — deleting a lesson
    # shrinks the progress denominator, potentially pushing a student to 100%
    # and opening the cert gate.
    course = lesson.module.course if lesson.module else None
    db.session.delete(lesson)
    db.session.flush()
    if course is not None:
        from models import Enrollment
        from utils.certificates import maybe_issue_certificate
        from utils.grading import recompute_progress_percent
        for e in Enrollment.query.filter_by(course_id=course.id).filter(
            Enrollment.status.in_(("active", "completed"))
        ).all():
            recompute_progress_percent(e)
            maybe_issue_certificate(e)
    db.session.commit()
    return jsonify({"message": "Lesson deleted."}), 200
