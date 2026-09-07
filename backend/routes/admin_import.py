"""Phase 20 — admin CSV bulk-import of users.

One endpoint: `POST /api/admin/users/import` (multipart, admin-only).

Row format (header required):
    email, name, role, gradeName, className
Only `email`, `name`, `role` are required per row. `gradeName` + `className`
apply to students to auto-place them via the existing helper. Blank
`className` is OK (creates the user unplaced); non-blank must resolve to
an existing class within the given grade — the endpoint never creates
grades or classes on its own.

Idempotent: rows are keyed on email — existing users get their name/role
updated in-place, then their class placement is (re-)applied if given.
Newly-created users each get their OWN random temporary password, returned
once in the response next to their row. They previously all shared the
literal `changeme123`, which meant one leaked row handed you the whole
school; the password is only ever stored as a hash, so this response is the
single chance to read it.

All writes go through the same helpers the admin's UI already uses
(`_place_student_in_class`-shaped call → `_auto_enroll_mandatory_for_grade`).
No trust-core surface bypassed.
"""
from __future__ import annotations

import csv
import io
import secrets
from datetime import datetime

from flask import Blueprint, jsonify, request

from models import (
    Grade,
    SchoolClass,
    User,
    db,
)
from routes.auth import current_user, require_admin
from routes.students import _auto_enroll_mandatory_for_grade
from utils.time import utc_now

admin_import_bp = Blueprint("admin_import", __name__)


# Phase 25 hard-audit fix C-1: role="admin" was importable via CSV,
# silently bypassing the Phase 11 audit fix in `routes/users.py` that
# closed the same hole via the JSON create endpoint. Admin accounts
# must only come from either the seed script or a direct DB write.
_ALLOWED_ROLES = ("student", "instructor", "parent")


def _temporary_password() -> str:
    """A fresh URL-safe password per imported user (~95 bits of entropy)."""
    return secrets.token_urlsafe(12)


@admin_import_bp.route("/admin/users/import", methods=["POST"])
@require_admin
def bulk_import_users():
    """Multipart form-data. Field name: `file` (a text/CSV file).

    Returns:
      {
        "created":  [ {row, email, id, temporaryPassword}, ... ],
        "updated":  [ {row, email, id}, ... ],
        "skipped":  [ {row, email, reason}, ... ],
        "errors":   [ {row, error}, ... ],
        "notice":   "..."
      }

    `temporaryPassword` appears only on created rows, and only in this
    response — it is stored as a hash and cannot be read back later.
    """
    file = request.files.get("file")
    if file is None:
        return jsonify({"error": "Upload a CSV file under form field 'file'."}), 400
    try:
        raw = file.stream.read().decode("utf-8-sig")
    except UnicodeDecodeError:
        return jsonify({"error": "CSV must be UTF-8 encoded."}), 400
    if not raw.strip():
        return jsonify({"error": "CSV file is empty."}), 400

    reader = csv.DictReader(io.StringIO(raw))
    if reader.fieldnames is None:
        return jsonify({"error": "CSV is missing a header row."}), 400

    normalized = {f.strip().lower() for f in reader.fieldnames}
    for req in ("email", "name", "role"):
        if req not in normalized:
            return jsonify({
                "error": f"CSV header must include '{req}'."
            }), 400

    # Grade / class lookup — resolved on demand so we don't blow memory on
    # rows that never reference them.
    grade_cache: dict[str, Grade] = {}
    class_cache: dict[tuple[str, str], SchoolClass] = {}

    def _grade_by_name(name: str) -> Grade | None:
        key = name.strip()
        if key in grade_cache:
            return grade_cache[key]
        row = Grade.query.filter_by(name=key).first()
        if row is not None:
            grade_cache[key] = row
        return row

    def _class_in_grade(grade: Grade, class_name: str) -> SchoolClass | None:
        key = (grade.id, class_name.strip())
        if key in class_cache:
            return class_cache[key]
        row = SchoolClass.query.filter_by(
            grade_id=grade.id, name=class_name.strip(),
        ).first()
        if row is not None:
            class_cache[key] = row
        return row

    # `require_admin` already validated the caller — this is who we credit
    # as the enrolling admin on any auto-enrollment writes below.
    admin = current_user()

    created: list[dict] = []
    updated: list[dict] = []
    skipped: list[dict] = []
    errors: list[dict] = []

    row_num = 1  # 1 = header
    for raw_row in reader:
        row_num += 1
        # Lowercase-key the row so callers' case variations survive.
        row = {(k or "").strip().lower(): (v or "").strip() for k, v in raw_row.items()}
        email = row.get("email", "").lower()
        name = row.get("name", "")
        role = row.get("role", "").lower()
        grade_name = row.get("gradename", "")
        class_name = row.get("classname", "")

        if not email or not name or not role:
            errors.append({"row": row_num,
                           "error": "email, name, and role are all required."})
            continue
        if role not in _ALLOWED_ROLES:
            errors.append({"row": row_num,
                           "error": f"role must be one of {_ALLOWED_ROLES}."})
            continue
        if "@" not in email:
            errors.append({"row": row_num, "error": "email looks malformed."})
            continue

        # Resolve grade + class up front so we don't create the user and
        # then fail placement — the row's whole intent is atomic.
        target_class: SchoolClass | None = None
        if role == "student" and class_name:
            if not grade_name:
                errors.append({"row": row_num,
                               "error": "gradeName required when className is given."})
                continue
            grade = _grade_by_name(grade_name)
            if grade is None:
                errors.append({"row": row_num,
                               "error": f"grade '{grade_name}' not found."})
                continue
            target_class = _class_in_grade(grade, class_name)
            if target_class is None:
                errors.append({"row": row_num,
                               "error": f"class '{class_name}' not found in grade '{grade_name}'."})
                continue

        existing = User.query.filter_by(email=email).first()
        if existing is None:
            user = User(name=name, email=email, role=role, is_active=True)
            temp_password = _temporary_password()
            user.set_password(temp_password)
            # Someone other than the account holder chose this password, so
            # the holder must replace it before the account is really theirs.
            user.must_change_password = True
            db.session.add(user)
            db.session.flush()  # need the id for placement
            outcome = created
        else:
            # Refuse to change role of an existing user across role families —
            # too easy a foot-gun (student → admin via CSV typo).
            if existing.role != role:
                skipped.append({"row": row_num, "email": email,
                                "reason": f"user already exists with role '{existing.role}' — refusing to change to '{role}'."})
                continue
            existing.name = name
            existing.updated_at = utc_now()
            user = existing
            outcome = updated

        # Placement + auto-enroll — same trust-core path the UI uses.
        if target_class is not None:
            if user.class_id != target_class.id:
                # Phase 25 hard-audit fix: if this is a CROSS-GRADE move
                # (student was in a different grade's class), soft-drop
                # their old mandatory enrollments FIRST. Otherwise the
                # student ends up enrolled in both grades' mandatory
                # courses — silent curriculum corruption. Mirrors the
                # `routes/students.py::place_student_in_class` UI path.
                from routes.students import _soft_drop_all_active_enrollments
                old_class = (
                    db.session.get(SchoolClass, user.class_id)
                    if user.class_id else None
                )
                cross_grade = (
                    old_class is not None
                    and old_class.grade_id != target_class.grade_id
                )
                if cross_grade:
                    _soft_drop_all_active_enrollments(user)
                user.class_id = target_class.id
                _auto_enroll_mandatory_for_grade(user, target_class.grade_id, admin)

        entry = {"row": row_num, "email": email, "id": user.id}
        if outcome is created:
            entry["temporaryPassword"] = temp_password
        outcome.append(entry)

    db.session.commit()

    return jsonify({
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "errors": errors,
        "notice": (
            "Each new user has their own temporary password, listed beside "
            "their row. This is the only time they are shown — hand them out "
            "now. Every one of these users is required to choose a new "
            "password at first sign-in."
        ),
    }), 200
