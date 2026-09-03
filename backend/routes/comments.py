"""Phase 21 — one-deep Q&A comments per lesson.

Anyone who can view the lesson's course content can also read its
comments. Posting requires the same visibility. Delete: author or admin.

Replies are one level deep (a "question" and its "answers"). A reply
can't itself have a reply — the UI stays flat and threaded.
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from models import Lesson, LessonComment, db
from routes.auth import current_user, login_required
from utils.notifications import enqueue
from utils.permissions import can_view_content, is_admin
from utils.validation import (
    ValidationError,
    as_str,
    require_fields,
    require_json,
)

comments_bp = Blueprint("comments", __name__)


def _course_of_lesson(lesson: Lesson):
    return lesson.module.course if lesson.module else None


@comments_bp.route("/lessons/<string:lid>/comments", methods=["GET"])
@login_required
def list_lesson_comments(lid: str):
    lesson = db.session.get(Lesson, lid)
    if lesson is None:
        return jsonify({"error": "Lesson not found."}), 404
    user = current_user()
    course = _course_of_lesson(lesson)
    if course is None or not can_view_content(user, course):
        return jsonify({"error": "You do not have permission."}), 403
    rows = (
        LessonComment.query.filter_by(lesson_id=lid)
        .order_by(LessonComment.created_at.asc())
        .all()
    )
    return jsonify([c.to_dict() for c in rows]), 200


@comments_bp.route("/lessons/<string:lid>/comments", methods=["POST"])
@login_required
def create_comment(lid: str):
    lesson = db.session.get(Lesson, lid)
    if lesson is None:
        return jsonify({"error": "Lesson not found."}), 404
    user = current_user()
    course = _course_of_lesson(lesson)
    if course is None or not can_view_content(user, course):
        return jsonify({"error": "You do not have permission."}), 403
    try:
        payload = require_json(request.get_json(silent=True))
        require_fields(payload, ("body",))
        body = as_str(payload["body"], "body", max_len=5000)
        parent_id = payload.get("parentCommentId")
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400
    if not body.strip():
        return jsonify({"error": "body is required."}), 400

    parent: LessonComment | None = None
    if parent_id:
        parent = db.session.get(LessonComment, parent_id)
        if parent is None or parent.lesson_id != lid:
            return jsonify({"error": "parentCommentId not found on this lesson."}), 400
        if parent.parent_comment_id is not None:
            return jsonify({"error": "Comments are only one level deep."}), 400

    row = LessonComment(
        lesson_id=lid,
        author_id=user.id,
        parent_comment_id=parent.id if parent else None,
        body=body.strip(),
    )
    db.session.add(row)
    db.session.flush()

    # Ping the original questioner when someone answers.
    if parent is not None and parent.author_id != user.id:
        enqueue(
            parent.author_id,
            kind="comment_reply",
            title=f"{user.name} answered your question",
            body=row.body[:280],
            ref_type="lesson",
            ref_id=lid,
        )

    db.session.commit()
    return jsonify(row.to_dict()), 201


@comments_bp.route("/comments/<string:cid>", methods=["DELETE"])
@login_required
def delete_comment(cid: str):
    row = db.session.get(LessonComment, cid)
    if row is None:
        return jsonify({"error": "Comment not found."}), 404
    user = current_user()
    if not (is_admin(user) or row.author_id == user.id):
        return jsonify({"error": "You do not have permission."}), 403
    db.session.delete(row)
    db.session.commit()
    return "", 204
