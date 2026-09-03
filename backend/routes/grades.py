"""Grades blueprint — admin CRUD for school grades (Grade 9, Grade 10, …).

Not to be confused with `grade_reports.py`, which handles grade-ENTRY writes
and report-card reads. This file is about the school-grade concept from
Phase 2.
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from models import Course, Grade, Section, SchoolClass, db
from routes.auth import login_required, require_admin
from utils.validation import (
    ValidationError,
    as_int,
    as_str,
    require_fields,
    require_json,
)

grades_bp = Blueprint("grades", __name__)


@grades_bp.route("", methods=["GET"])
@grades_bp.route("/", methods=["GET"])
@login_required
def list_grades():
    section_id = (request.args.get("sectionId") or "").strip() or None
    q = Grade.query
    if section_id:
        q = q.filter_by(section_id=section_id)
    rows = q.order_by(Grade.order_index.asc(), Grade.name.asc()).all()
    return jsonify([g.to_dict() for g in rows]), 200


@grades_bp.route("/<string:grade_id>", methods=["GET"])
@login_required
def get_grade(grade_id: str):
    g = db.session.get(Grade, grade_id)
    if g is None:
        return jsonify({"error": "Grade not found."}), 404
    return jsonify(g.to_dict()), 200


@grades_bp.route("", methods=["POST"])
@grades_bp.route("/", methods=["POST"])
@require_admin
def create_grade():
    try:
        payload = require_json(request.get_json(silent=True))
        require_fields(payload, ("name",))
        name = as_str(payload["name"], "name", max_len=80)
        section_id = payload.get("sectionId")
        order_index = as_int(payload.get("orderIndex"), "orderIndex", default=0)
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400
    if Grade.query.filter_by(name=name).first() is not None:
        return jsonify({"error": "A grade with this name already exists."}), 409
    if section_id is not None:
        if db.session.get(Section, section_id) is None:
            return jsonify({"error": "sectionId does not exist."}), 400
    grade = Grade(name=name, section_id=section_id, order_index=order_index)
    db.session.add(grade)
    db.session.commit()
    return jsonify(grade.to_dict()), 201


@grades_bp.route("/<string:grade_id>", methods=["PUT", "PATCH"])
@require_admin
def update_grade(grade_id: str):
    grade = db.session.get(Grade, grade_id)
    if grade is None:
        return jsonify({"error": "Grade not found."}), 404
    try:
        payload = require_json(request.get_json(silent=True))
        if "name" in payload:
            new_name = as_str(payload["name"], "name", max_len=80)
            if new_name != grade.name and Grade.query.filter_by(name=new_name).first():
                return jsonify({"error": "A grade with this name already exists."}), 409
            grade.name = new_name
        if "sectionId" in payload:
            sid = payload["sectionId"]
            if sid is not None and db.session.get(Section, sid) is None:
                return jsonify({"error": "sectionId does not exist."}), 400
            grade.section_id = sid
        if "orderIndex" in payload:
            grade.order_index = as_int(payload["orderIndex"], "orderIndex")
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400
    db.session.commit()
    return jsonify(grade.to_dict()), 200


@grades_bp.route("/<string:grade_id>", methods=["DELETE"])
@require_admin
def delete_grade(grade_id: str):
    grade = db.session.get(Grade, grade_id)
    if grade is None:
        return jsonify({"error": "Grade not found."}), 404
    if SchoolClass.query.filter_by(grade_id=grade_id).count() > 0:
        return (
            jsonify({"error": "This grade still has classes. Delete or reassign them first."}),
            409,
        )
    if Course.query.filter_by(grade_id=grade_id).count() > 0:
        return (
            jsonify({"error": "This grade still has courses. Delete or reassign them first."}),
            409,
        )
    db.session.delete(grade)
    db.session.commit()
    return jsonify({"message": "Grade deleted."}), 200


# =============================================================================
# Curriculum read — grouped by mandatory + elective groups
# =============================================================================
@grades_bp.route("/<string:grade_id>/curriculum", methods=["GET"])
@login_required
def get_grade_curriculum(grade_id: str):
    """Returns { mandatory: [...], electiveGroups: { language: [...], ... } }."""
    grade = db.session.get(Grade, grade_id)
    if grade is None:
        return jsonify({"error": "Grade not found."}), 404
    all_courses = Course.query.filter_by(grade_id=grade_id).order_by(Course.title.asc()).all()
    mandatory = []
    electives: dict[str, list[dict]] = {}
    for c in all_courses:
        d = c.to_dict()
        if c.elective_group is None or c.elective_group == "":
            mandatory.append(d)
        else:
            electives.setdefault(c.elective_group, []).append(d)
    return (
        jsonify(
            {
                "gradeId": grade.id,
                "gradeName": grade.name,
                "sectionId": grade.section_id,
                "sectionName": grade.section.name if grade.section else None,
                "mandatory": mandatory,
                "electiveGroups": electives,
            }
        ),
        200,
    )
