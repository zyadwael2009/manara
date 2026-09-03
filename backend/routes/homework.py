"""Phase 21 — one homework post per class per school day.

The homeroom teacher of a class can upsert its posts; admin can too.
Reads scope to anyone who can view the class roster or timetable — so
students in the class + linked parents + course teachers + admin.
"""
from __future__ import annotations

from datetime import date as _date, datetime, timedelta

from flask import Blueprint, jsonify, request

from models import HomeworkPost, ParentStudentLink, SchoolClass, User, db
from routes.auth import current_user, login_required
from utils.notifications import enqueue
from utils.permissions import (
    can_view_class_timetable,
    homerooms_class,
    is_admin,
)
from utils.validation import (
    ValidationError,
    as_str,
    require_fields,
    require_json,
)
from utils.time import utc_now

homework_bp = Blueprint("homework", __name__)


def _parse_iso_date(raw: str) -> _date:
    try:
        return _date.fromisoformat(raw)
    except (TypeError, ValueError):
        raise ValidationError(f"date must be YYYY-MM-DD (got {raw!r}).") from None


def _can_write(user: User, sc: SchoolClass) -> bool:
    return is_admin(user) or homerooms_class(user, sc)


@homework_bp.route("/classes/<string:class_id>/homework", methods=["GET"])
@login_required
def list_homework(class_id: str):
    sc = db.session.get(SchoolClass, class_id)
    if sc is None:
        return jsonify({"error": "Class not found."}), 404
    user = current_user()
    if not can_view_class_timetable(user, sc):
        return jsonify({"error": "You do not have permission."}), 403

    from_raw = request.args.get("from")
    to_raw = request.args.get("to")
    try:
        from_d = _parse_iso_date(from_raw) if from_raw else _date.today() - timedelta(days=14)
        to_d = _parse_iso_date(to_raw) if to_raw else _date.today() + timedelta(days=7)
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400

    rows = (
        HomeworkPost.query.filter_by(class_id=class_id)
        .filter(HomeworkPost.date >= from_d)
        .filter(HomeworkPost.date <= to_d)
        .order_by(HomeworkPost.date.desc())
        .all()
    )
    return jsonify([r.to_dict() for r in rows]), 200


@homework_bp.route("/classes/<string:class_id>/homework/<string:date>", methods=["PUT"])
@login_required
def upsert_homework(class_id: str, date: str):
    sc = db.session.get(SchoolClass, class_id)
    if sc is None:
        return jsonify({"error": "Class not found."}), 404
    user = current_user()
    if not _can_write(user, sc):
        return jsonify({"error": "You do not have permission."}), 403

    try:
        target = _parse_iso_date(date)
        payload = require_json(request.get_json(silent=True))
        require_fields(payload, ("title",))
        title = as_str(payload["title"], "title", max_len=200)
        body = as_str(payload.get("body", ""), "body", max_len=5000) or ""
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400
    if not title.strip():
        return jsonify({"error": "title is required."}), 400

    row = HomeworkPost.query.filter_by(class_id=class_id, date=target).first()
    is_new = row is None
    if row is None:
        row = HomeworkPost(
            class_id=class_id, date=target,
            author_id=user.id, title=title.strip(), body=body.strip(),
        )
        db.session.add(row)
    else:
        row.title = title.strip()
        row.body = body.strip()
        row.author_id = user.id
        row.updated_at = utc_now()
    db.session.flush()

    # Ping every student in the class + linked parents on first-post only
    # (edits don't re-notify — otherwise a typo fix would spam).
    if is_new:
        student_ids = [s.id for s in sc.students.all()]
        parent_links = (
            ParentStudentLink.query
            .filter(ParentStudentLink.student_id.in_(student_ids)).all()
            if student_ids else []
        )
        for sid in student_ids:
            enqueue(sid, kind="announcement",
                    title=f"Homework posted for {sc.name}",
                    body=row.title, ref_type="homework", ref_id=row.id)
        for link in parent_links:
            enqueue(link.parent_id, kind="announcement",
                    title=f"Homework posted for {sc.name}",
                    body=row.title, ref_type="homework", ref_id=row.id)

    db.session.commit()
    return jsonify(row.to_dict()), 200 if not is_new else 201


@homework_bp.route("/classes/<string:class_id>/homework/<string:date>", methods=["DELETE"])
@login_required
def delete_homework(class_id: str, date: str):
    sc = db.session.get(SchoolClass, class_id)
    if sc is None:
        return jsonify({"error": "Class not found."}), 404
    user = current_user()
    if not _can_write(user, sc):
        return jsonify({"error": "You do not have permission."}), 403
    try:
        target = _parse_iso_date(date)
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400
    row = HomeworkPost.query.filter_by(class_id=class_id, date=target).first()
    if row is None:
        return "", 204
    db.session.delete(row)
    db.session.commit()
    return "", 204
