"""Module CRUD.

Phase 2: permission checks route through `can_edit_course_content`
(dept-leader-aware) instead of Phase 1's ownership shortcut.
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request
from sqlalchemy import func

from models import Course, Module, db
from routes.auth import current_user, login_required
from utils.permissions import can_edit_course_content, can_edit_module, can_view_module_content
from utils.validation import (
    ValidationError,
    as_int,
    as_str,
    require_fields,
    require_json,
)

modules_bp = Blueprint("modules", __name__)


@modules_bp.route("/courses/<string:course_id>/modules", methods=["POST"])
@login_required
def create_module(course_id: str):
    course = db.session.get(Course, course_id)
    if course is None:
        return jsonify({"error": "Course not found."}), 404
    if not can_edit_course_content(current_user(), course):
        return jsonify({"error": "You do not have permission to modify this course."}), 403

    try:
        payload = require_json(request.get_json(silent=True))
        require_fields(payload, ("title",))
        title = as_str(payload["title"], "title", max_len=200)
        order_index = as_int(payload.get("orderIndex"), "orderIndex", default=-1)
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400

    if order_index < 0:
        last = db.session.query(func.max(Module.order_index)).filter_by(course_id=course.id).scalar()
        order_index = 0 if last is None else last + 1

    module = Module(course_id=course.id, title=title, order_index=order_index)
    db.session.add(module)
    db.session.commit()
    return jsonify(module.to_dict()), 201


@modules_bp.route("/modules/<string:module_id>", methods=["GET"])
@login_required
def get_module(module_id: str):
    module = db.session.get(Module, module_id)
    if module is None:
        return jsonify({"error": "Module not found."}), 404
    user = current_user()
    hide = not can_view_module_content(user, module)
    if hide and not can_edit_module(user, module):
        return jsonify({"error": "You do not have permission to view this module."}), 403
    return jsonify(module.to_dict(include_lessons=True, hide_content=hide)), 200


@modules_bp.route("/modules/<string:module_id>", methods=["PUT", "PATCH"])
@login_required
def update_module(module_id: str):
    module = db.session.get(Module, module_id)
    if module is None:
        return jsonify({"error": "Module not found."}), 404
    if not can_edit_module(current_user(), module):
        return jsonify({"error": "You do not have permission to edit this module."}), 403

    try:
        payload = require_json(request.get_json(silent=True))
        if "title" in payload:
            module.title = as_str(payload["title"], "title", max_len=200)
        if "orderIndex" in payload:
            module.order_index = as_int(payload["orderIndex"], "orderIndex")
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400

    db.session.commit()
    return jsonify(module.to_dict()), 200


@modules_bp.route("/modules/<string:module_id>", methods=["DELETE"])
@login_required
def delete_module(module_id: str):
    module = db.session.get(Module, module_id)
    if module is None:
        return jsonify({"error": "Module not found."}), 404
    if not can_edit_module(current_user(), module):
        return jsonify({"error": "You do not have permission to delete this module."}), 403
    # Phase 9 audit fix F5: capture the course before delete cascades;
    # after delete, progress denominators change so we recompute + re-issue
    # certs for any student whose gate now opens.
    course = module.course
    db.session.delete(module)
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
    return jsonify({"message": "Module deleted."}), 200
