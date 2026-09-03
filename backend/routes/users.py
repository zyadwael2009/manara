"""Users blueprint — search + list, used by the admin's roster/placement UI.

Auth is admin/instructor only, and only students are searchable. This
prevents a teacher from fishing for other teachers' or parents' emails.
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request
from sqlalchemy import or_

from models import User, db
from routes.auth import current_user, require_admin, require_role
from utils.permissions import is_admin
from utils.validation import (
    ValidationError,
    as_str,
    one_of,
    require_fields,
    require_json,
)

users_bp = Blueprint("users", __name__)


@users_bp.route("", methods=["GET"])
@users_bp.route("/", methods=["GET"])
@require_role("instructor", "admin")
def list_users():
    """Search users. Query params:
      role       required — Phase 2 hard-codes to 'student' (see below)
      search     optional substring, case-insensitive, matches name OR email
      unassigned optional 'true' to filter students with class_id IS NULL
      limit      optional int (default 20, max 100)

    Guardrails:
      * Non-student roles are rejected in Phase 2 to prevent teacher-list
        enumeration by teachers.
      * Empty search returns [] to prevent accidental full-school dumps
        (unless `unassigned=true` is set — that view is meaningful empty).
    """
    role = (request.args.get("role") or "").strip().lower()
    if role != "student":
        return jsonify({"error": "Only role=student is searchable in Phase 2."}), 400

    search = (request.args.get("search") or "").strip()
    unassigned = (request.args.get("unassigned") or "").strip().lower() == "true"
    try:
        limit = min(int(request.args.get("limit") or 20), 100)
    except (TypeError, ValueError):
        limit = 20

    if not search and not unassigned:
        return jsonify([]), 200

    q = User.query.filter_by(role="student", is_active=True)
    if unassigned:
        q = q.filter(User.class_id.is_(None))
    if search:
        pattern = f"%{search}%"
        q = q.filter(or_(User.name.ilike(pattern), User.email.ilike(pattern)))

    q = q.order_by(User.name.asc())
    # Phase 30 · T5 — pagination. Back-compat: no `page` arg → the
    # original limit-capped bare-array shape. With `page`/`pageSize`,
    # returns the envelope `{items, page, pageSize, hasMore}`.
    if request.args.get("page") or request.args.get("pageSize"):
        from utils.pagination import paginate
        return jsonify(paginate(q, render_item=lambda u: u.to_dict())), 200
    rows = q.limit(limit).all()
    return jsonify([u.to_dict() for u in rows]), 200


# =============================================================================
# Phase 6 — admin creates a parent account (or any account, admin-authoritative)
#
# Self-registration into role='parent' is refused in routes/auth.py; this is
# the only path an admin has to make one. Not used for students today
# (student accounts are created via /api/auth/register or the placement UI),
# but it works for any role — admin is the trusted actor.
# =============================================================================
# Phase 11 audit fix L3: admin is deliberately NOT in this list. Any
# admin session used to be able to mint peer admins with no audit trail;
# the seed script or a DB write is now the only path.
_ADMIN_CREATE_ROLES = ("parent", "instructor", "student")


@users_bp.route("", methods=["POST"])
@users_bp.route("/", methods=["POST"])
@require_admin
def admin_create_user():
    try:
        payload = require_json(request.get_json(silent=True))
        require_fields(payload, ("name", "email", "password", "role"))
        name = as_str(payload["name"], "name", max_len=120)
        email = as_str(payload["email"], "email", max_len=190).lower()
        password = as_str(payload["password"], "password", max_len=255)
        role = one_of(payload["role"], _ADMIN_CREATE_ROLES, "role")
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400

    if "@" not in email or "." not in email.split("@")[-1]:
        return jsonify({"error": "Invalid email address."}), 400
    if len(password) < 8:
        return jsonify({"error": "Password must be at least 8 characters."}), 400
    if User.query.filter_by(email=email).first() is not None:
        return jsonify({"error": "An account with this email already exists."}), 409

    u = User(name=name, email=email, role=role)
    u.set_password(password)
    db.session.add(u)
    db.session.commit()
    return jsonify(u.to_dict()), 201


@users_bp.route("/parents", methods=["GET"])
@users_bp.route("/parents/", methods=["GET"])
@require_admin
def list_parents():
    """Admin-facing directory of parent accounts, used by the link picker on
    the student detail screen. Requires admin so a teacher can't fish for
    parent contact info.
    """
    search = (request.args.get("search") or "").strip()
    q = User.query.filter_by(role="parent", is_active=True)
    if search:
        pattern = f"%{search}%"
        q = q.filter(or_(User.name.ilike(pattern), User.email.ilike(pattern)))
    rows = q.order_by(User.name.asc()).limit(200).all()
    return jsonify([u.to_dict() for u in rows]), 200


@users_bp.route("/instructors", methods=["GET"])
@users_bp.route("/instructors/", methods=["GET"])
@require_role("instructor", "admin")
def list_instructors():
    """List every instructor. Used by the admin UI to pick a homeroom teacher,
    a class-course teacher, or a department leader.

    Only admins get the full list; a non-admin instructor gets an empty list.
    (No teacher directory for regular teachers in Phase 2.)
    """
    user = current_user()
    if not is_admin(user):
        return jsonify([]), 200
    search = (request.args.get("search") or "").strip()
    q = User.query.filter_by(role="instructor", is_active=True)
    if search:
        pattern = f"%{search}%"
        q = q.filter(or_(User.name.ilike(pattern), User.email.ilike(pattern)))
    rows = q.order_by(User.name.asc()).all()
    return jsonify([u.to_dict() for u in rows]), 200
