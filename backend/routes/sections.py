"""Sections blueprint — admin-configurable school-section split.

Default seed (in `seed_dev.py`): Elementary, Middle, High.
Admin can rename / reorder / add / delete.
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from models import Grade, Section, db
from routes.auth import login_required, require_admin
from utils.validation import (
    ValidationError,
    as_int,
    as_str,
    require_fields,
    require_json,
)

sections_bp = Blueprint("sections", __name__)


@sections_bp.route("", methods=["GET"])
@sections_bp.route("/", methods=["GET"])
@login_required
def list_sections():
    rows = Section.query.order_by(Section.order_index.asc(), Section.name.asc()).all()
    return jsonify([s.to_dict() for s in rows]), 200


@sections_bp.route("", methods=["POST"])
@sections_bp.route("/", methods=["POST"])
@require_admin
def create_section():
    try:
        payload = require_json(request.get_json(silent=True))
        require_fields(payload, ("name",))
        name = as_str(payload["name"], "name", max_len=80)
        order_index = as_int(payload.get("orderIndex"), "orderIndex", default=0)
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400
    if Section.query.filter_by(name=name).first() is not None:
        return jsonify({"error": "A section with this name already exists."}), 409
    section = Section(name=name, order_index=order_index)
    db.session.add(section)
    db.session.commit()
    return jsonify(section.to_dict()), 201


@sections_bp.route("/<string:section_id>", methods=["PUT", "PATCH"])
@require_admin
def update_section(section_id: str):
    section = db.session.get(Section, section_id)
    if section is None:
        return jsonify({"error": "Section not found."}), 404
    try:
        payload = require_json(request.get_json(silent=True))
        if "name" in payload:
            new_name = as_str(payload["name"], "name", max_len=80)
            if new_name != section.name and Section.query.filter_by(name=new_name).first():
                return jsonify({"error": "A section with this name already exists."}), 409
            section.name = new_name
        if "orderIndex" in payload:
            section.order_index = as_int(payload["orderIndex"], "orderIndex")
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400
    db.session.commit()
    return jsonify(section.to_dict()), 200


@sections_bp.route("/<string:section_id>", methods=["DELETE"])
@require_admin
def delete_section(section_id: str):
    section = db.session.get(Section, section_id)
    if section is None:
        return jsonify({"error": "Section not found."}), 404
    # Refuse if grades still reference this section — no silent cascades.
    if Grade.query.filter_by(section_id=section_id).count() > 0:
        return (
            jsonify(
                {"error": "This section still has grades. Reassign or delete them first."}
            ),
            409,
        )
    db.session.delete(section)
    db.session.commit()
    return jsonify({"message": "Section deleted."}), 200
