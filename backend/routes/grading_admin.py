"""Grading admin — school years, terms, categories, grading scale.

All routes admin-only. (Phase 11 audit fix L6: the previous docstring
claimed term lock/unlock allowed dept-leader, but the decorators have
always been `@require_admin` — the docstring was drift, not the code.)
"""
from __future__ import annotations

from datetime import date, datetime

from flask import Blueprint, jsonify, request

from models import (
    GradeCategory,
    GradingScaleBand,
    SchoolYear,
    Term,
    db,
)
from routes.auth import current_user, login_required, require_admin
from utils.validation import (
    ValidationError,
    as_int,
    as_str,
    require_fields,
    require_json,
)
from utils.time import utc_now

grading_admin_bp = Blueprint("grading_admin", __name__)


def _parse_date(raw) -> date | None:
    if raw is None or raw == "":
        return None
    if isinstance(raw, date):
        return raw
    try:
        return datetime.fromisoformat(str(raw)).date()
    except ValueError as e:
        raise ValidationError(f"Invalid date '{raw}'.") from e


# =============================================================================
# School years
# =============================================================================
@grading_admin_bp.route("/school-years", methods=["GET"])
@login_required
def list_school_years():
    rows = SchoolYear.query.order_by(SchoolYear.start_date.desc().nullslast()).all()
    return jsonify([y.to_dict() for y in rows]), 200


@grading_admin_bp.route("/school-years", methods=["POST"])
@require_admin
def create_school_year():
    try:
        payload = require_json(request.get_json(silent=True))
        require_fields(payload, ("name",))
        name = as_str(payload["name"], "name", max_len=80)
        start = _parse_date(payload.get("startDate"))
        end = _parse_date(payload.get("endDate"))
        is_current = bool(payload.get("isCurrent", False))
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400
    if SchoolYear.query.filter_by(name=name).first() is not None:
        return jsonify({"error": "A school year with this name already exists."}), 409
    if is_current:
        for other in SchoolYear.query.filter_by(is_current=True).all():
            other.is_current = False
    y = SchoolYear(name=name, start_date=start, end_date=end, is_current=is_current)
    db.session.add(y)
    db.session.commit()
    return jsonify(y.to_dict()), 201


@grading_admin_bp.route("/school-years/<string:year_id>", methods=["PUT", "PATCH"])
@require_admin
def update_school_year(year_id: str):
    y = db.session.get(SchoolYear, year_id)
    if y is None:
        return jsonify({"error": "School year not found."}), 404
    try:
        payload = require_json(request.get_json(silent=True))
        if "name" in payload:
            new_name = as_str(payload["name"], "name", max_len=80)
            if new_name != y.name and SchoolYear.query.filter_by(name=new_name).first():
                return jsonify({"error": "A school year with this name already exists."}), 409
            y.name = new_name
        if "startDate" in payload:
            y.start_date = _parse_date(payload["startDate"])
        if "endDate" in payload:
            y.end_date = _parse_date(payload["endDate"])
        if "isCurrent" in payload:
            is_cur = bool(payload["isCurrent"])
            if is_cur:
                for other in SchoolYear.query.filter(SchoolYear.id != y.id, SchoolYear.is_current.is_(True)).all():
                    other.is_current = False
            y.is_current = is_cur
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400
    db.session.commit()
    return jsonify(y.to_dict()), 200


@grading_admin_bp.route("/school-years/<string:year_id>", methods=["DELETE"])
@require_admin
def delete_school_year(year_id: str):
    y = db.session.get(SchoolYear, year_id)
    if y is None:
        return jsonify({"error": "School year not found."}), 404
    if Term.query.filter_by(school_year_id=y.id).count() > 0:
        return jsonify({"error": "Delete or reassign this year's terms first."}), 409
    db.session.delete(y)
    db.session.commit()
    return jsonify({"message": "School year deleted."}), 200


# =============================================================================
# Terms
# =============================================================================
@grading_admin_bp.route("/school-years/<string:year_id>/terms", methods=["GET"])
@login_required
def list_terms(year_id: str):
    y = db.session.get(SchoolYear, year_id)
    if y is None:
        return jsonify({"error": "School year not found."}), 404
    rows = Term.query.filter_by(school_year_id=y.id).order_by(Term.order_index.asc()).all()
    return jsonify([t.to_dict() for t in rows]), 200


@grading_admin_bp.route("/school-years/<string:year_id>/terms", methods=["POST"])
@require_admin
def create_term(year_id: str):
    y = db.session.get(SchoolYear, year_id)
    if y is None:
        return jsonify({"error": "School year not found."}), 404
    try:
        payload = require_json(request.get_json(silent=True))
        require_fields(payload, ("name",))
        name = as_str(payload["name"], "name", max_len=80)
        start = _parse_date(payload.get("startDate"))
        end = _parse_date(payload.get("endDate"))
        order_index = as_int(payload.get("orderIndex"), "orderIndex", default=0)
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400
    if Term.query.filter_by(school_year_id=y.id, name=name).first() is not None:
        return jsonify({"error": "A term with this name already exists in this year."}), 409
    t = Term(
        school_year_id=y.id, name=name, start_date=start, end_date=end,
        order_index=order_index,
    )
    db.session.add(t)
    db.session.commit()
    return jsonify(t.to_dict()), 201


@grading_admin_bp.route("/terms/<string:term_id>", methods=["PUT", "PATCH"])
@require_admin
def update_term(term_id: str):
    t = db.session.get(Term, term_id)
    if t is None:
        return jsonify({"error": "Term not found."}), 404
    try:
        payload = require_json(request.get_json(silent=True))
        if "name" in payload:
            t.name = as_str(payload["name"], "name", max_len=80)
        if "startDate" in payload:
            t.start_date = _parse_date(payload["startDate"])
        if "endDate" in payload:
            t.end_date = _parse_date(payload["endDate"])
        if "orderIndex" in payload:
            t.order_index = as_int(payload["orderIndex"], "orderIndex")
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400
    db.session.commit()
    return jsonify(t.to_dict()), 200


@grading_admin_bp.route("/terms/<string:term_id>", methods=["DELETE"])
@require_admin
def delete_term(term_id: str):
    t = db.session.get(Term, term_id)
    if t is None:
        return jsonify({"error": "Term not found."}), 404
    db.session.delete(t)
    db.session.commit()
    return jsonify({"message": "Term deleted."}), 200


@grading_admin_bp.route("/terms/<string:term_id>/lock", methods=["POST"])
@require_admin
def lock_term(term_id: str):
    t = db.session.get(Term, term_id)
    if t is None:
        return jsonify({"error": "Term not found."}), 404
    t.is_locked = True
    t.locked_at = utc_now()
    db.session.commit()
    return jsonify(t.to_dict()), 200


@grading_admin_bp.route("/terms/<string:term_id>/unlock", methods=["POST"])
@require_admin
def unlock_term(term_id: str):
    t = db.session.get(Term, term_id)
    if t is None:
        return jsonify({"error": "Term not found."}), 404
    t.is_locked = False
    t.locked_at = None
    db.session.commit()
    return jsonify(t.to_dict()), 200


# =============================================================================
# Grade categories
# =============================================================================
@grading_admin_bp.route("/grade-categories", methods=["GET"])
@login_required
def list_categories():
    rows = GradeCategory.query.order_by(GradeCategory.order_index.asc()).all()
    return jsonify([c.to_dict() for c in rows]), 200


@grading_admin_bp.route("/grade-categories", methods=["POST"])
@require_admin
def create_category():
    try:
        payload = require_json(request.get_json(silent=True))
        require_fields(payload, ("name",))
        name = as_str(payload["name"], "name", max_len=80)
        slug = as_str(payload.get("slug") or name, "slug", max_len=80).lower().replace(" ", "_")
        order_index = as_int(payload.get("orderIndex"), "orderIndex", default=0)
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400
    if GradeCategory.query.filter_by(slug=slug).first() is not None:
        return jsonify({"error": "A grade category with this slug already exists."}), 409
    c = GradeCategory(name=name, slug=slug, order_index=order_index)
    db.session.add(c)
    db.session.commit()
    return jsonify(c.to_dict()), 201


@grading_admin_bp.route("/grade-categories/<string:cat_id>", methods=["PUT", "PATCH"])
@require_admin
def update_category(cat_id: str):
    c = db.session.get(GradeCategory, cat_id)
    if c is None:
        return jsonify({"error": "Not found."}), 404
    try:
        payload = require_json(request.get_json(silent=True))
        if "name" in payload:
            c.name = as_str(payload["name"], "name", max_len=80)
        if "orderIndex" in payload:
            c.order_index = as_int(payload["orderIndex"], "orderIndex")
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400
    db.session.commit()
    return jsonify(c.to_dict()), 200


@grading_admin_bp.route("/grade-categories/<string:cat_id>", methods=["DELETE"])
@require_admin
def delete_category(cat_id: str):
    c = db.session.get(GradeCategory, cat_id)
    if c is None:
        return jsonify({"error": "Not found."}), 404
    if c.is_system:
        return jsonify({"error": "System categories cannot be deleted; rename instead."}), 400
    db.session.delete(c)
    db.session.commit()
    return jsonify({"message": "Deleted."}), 200


# =============================================================================
# Grading scale bands
# =============================================================================
@grading_admin_bp.route("/grading-scale", methods=["GET"])
@login_required
def list_bands():
    rows = GradingScaleBand.query.order_by(GradingScaleBand.min_percent.desc()).all()
    return jsonify([b.to_dict() for b in rows]), 200


@grading_admin_bp.route("/grading-scale", methods=["POST"])
@require_admin
def create_band():
    try:
        payload = require_json(request.get_json(silent=True))
        require_fields(payload, ("minPercent", "maxPercent", "letter", "gpaValue"))
        mn = as_int(payload["minPercent"], "minPercent")
        mx = as_int(payload["maxPercent"], "maxPercent")
        letter = as_str(payload["letter"], "letter", max_len=8)
        gpa = float(payload["gpaValue"])
        order_index = as_int(payload.get("orderIndex"), "orderIndex", default=0)
    except (ValidationError, ValueError, TypeError) as e:
        return jsonify({"error": str(e)}), 400
    if mn > mx:
        return jsonify({"error": "minPercent must be <= maxPercent."}), 400
    if GradingScaleBand.query.filter_by(letter=letter).first() is not None:
        return jsonify({"error": f"Letter '{letter}' already exists."}), 409
    b = GradingScaleBand(
        min_percent=mn, max_percent=mx, letter=letter,
        gpa_value=gpa, order_index=order_index,
    )
    db.session.add(b)
    db.session.commit()
    return jsonify(b.to_dict()), 201


@grading_admin_bp.route("/grading-scale/<string:band_id>", methods=["PUT", "PATCH"])
@require_admin
def update_band(band_id: str):
    b = db.session.get(GradingScaleBand, band_id)
    if b is None:
        return jsonify({"error": "Not found."}), 404
    try:
        payload = require_json(request.get_json(silent=True))
        if "minPercent" in payload:
            b.min_percent = as_int(payload["minPercent"], "minPercent")
        if "maxPercent" in payload:
            b.max_percent = as_int(payload["maxPercent"], "maxPercent")
        if "letter" in payload:
            b.letter = as_str(payload["letter"], "letter", max_len=8)
        if "gpaValue" in payload:
            b.gpa_value = float(payload["gpaValue"])
        if "orderIndex" in payload:
            b.order_index = as_int(payload["orderIndex"], "orderIndex")
    except (ValidationError, ValueError, TypeError) as e:
        return jsonify({"error": str(e)}), 400
    if b.min_percent > b.max_percent:
        return jsonify({"error": "minPercent must be <= maxPercent."}), 400
    db.session.commit()
    return jsonify(b.to_dict()), 200


@grading_admin_bp.route("/grading-scale/<string:band_id>", methods=["DELETE"])
@require_admin
def delete_band(band_id: str):
    b = db.session.get(GradingScaleBand, band_id)
    if b is None:
        return jsonify({"error": "Not found."}), 404
    db.session.delete(b)
    db.session.commit()
    return jsonify({"message": "Deleted."}), 200
