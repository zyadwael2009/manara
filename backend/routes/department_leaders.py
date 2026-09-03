"""Department leaders blueprint — admin-managed.

Slot = (department, section). Admin assigns a teacher to a slot; that
teacher becomes the content-edit owner for every course in that
department within that section.
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from models import DepartmentLeader, Section, User, db
from routes.auth import login_required, require_admin
from utils.validation import (
    ValidationError,
    as_str,
    require_fields,
    require_json,
)

department_leaders_bp = Blueprint("department_leaders", __name__)


@department_leaders_bp.route("", methods=["GET"])
@department_leaders_bp.route("/", methods=["GET"])
@login_required
def list_leaders():
    """List every (dept × section) slot, including vacant ones.

    Requires the caller to know which departments and sections exist. Admin
    UIs render this as a matrix.
    """
    rows = DepartmentLeader.query.all()
    return jsonify([r.to_dict() for r in rows]), 200


@department_leaders_bp.route("", methods=["POST"])
@department_leaders_bp.route("/", methods=["POST"])
@require_admin
def set_leader():
    """Create OR update the (department, section) → teacher assignment.

    Body: { department, sectionId, teacherId }
    Idempotent — if the slot already has a row, we overwrite it.
    """
    try:
        payload = require_json(request.get_json(silent=True))
        require_fields(payload, ("department", "sectionId", "teacherId"))
        department = as_str(payload["department"], "department", max_len=80).lower()
        section_id = as_str(payload["sectionId"], "sectionId")
        teacher_id = as_str(payload["teacherId"], "teacherId")
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400

    if db.session.get(Section, section_id) is None:
        return jsonify({"error": "sectionId does not exist."}), 400
    teacher = db.session.get(User, teacher_id)
    if teacher is None or teacher.role != "instructor":
        return jsonify({"error": "teacherId must refer to an instructor."}), 400

    existing = DepartmentLeader.query.filter_by(
        department=department, section_id=section_id
    ).first()
    from routes.auth import current_user
    admin = current_user()
    if existing:
        existing.teacher_id = teacher.id
        existing.assigned_by_id = admin.id
    else:
        existing = DepartmentLeader(
            department=department,
            section_id=section_id,
            teacher_id=teacher.id,
            assigned_by_id=admin.id,
        )
        db.session.add(existing)
    db.session.commit()
    return jsonify(existing.to_dict()), 200


@department_leaders_bp.route("/<string:leader_id>", methods=["DELETE"])
@require_admin
def clear_leader(leader_id: str):
    row = db.session.get(DepartmentLeader, leader_id)
    if row is None:
        return jsonify({"error": "Not found."}), 404
    db.session.delete(row)
    db.session.commit()
    return jsonify({"message": "Slot cleared."}), 200
