"""Phase 27 — group-mode assignments.

When `Assignment.is_group = True`, students form/join an
`AssignmentGroup` before submitting. Every group member ends up with an
`AssignmentSubmission` row that shares the same content + grade — the
grade fan-out lives in `routes/assignments.py::grade_submission` (it
detects group mode, finds the members, and rolls up each member's
enrollment independently).

Endpoints:
  * POST   /api/assignments/<aid>/groups       — student creates
  * GET    /api/assignments/<aid>/groups       — roster + open slots
  * POST   /api/assignment-groups/<gid>/join   — student joins
  * POST   /api/assignment-groups/<gid>/leave  — student leaves
  * DELETE /api/assignment-groups/<gid>        — creator (or admin) drops
                                                  an empty/orphan group

Trust-core: never writes grades or enrollment cache here. Grading is
still admin/teacher-only via the existing `grade_submission` route; this
file only wires the roster the grader fans out over.
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from models import (
    Assignment,
    AssignmentGroup,
    AssignmentGroupMember,
    User,
    db,
)
from routes.auth import current_user, login_required
from utils.permissions import (
    has_active_enrollment,
    is_admin,
    is_student,
)
from utils.validation import (
    ValidationError,
    as_str,
    require_fields,
    require_json,
)

assignment_groups_bp = Blueprint("assignment_groups", __name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _course_of(a: Assignment):
    return a.module.course if (a and a.module) else None


def _existing_membership(user: User, assignment_id: str) -> AssignmentGroupMember | None:
    """Return this student's current membership for THIS assignment (if any).

    We don't store `assignment_id` on the member row directly (it lives
    on the parent group), so this is a two-table lookup — cheap because
    a student only ever has at most one membership per assignment.
    """
    return (
        AssignmentGroupMember.query
        .join(AssignmentGroup, AssignmentGroup.id == AssignmentGroupMember.group_id)
        .filter(
            AssignmentGroupMember.student_id == user.id,
            AssignmentGroup.assignment_id == assignment_id,
        )
        .first()
    )


def _group_size(group_id: str) -> int:
    return AssignmentGroupMember.query.filter_by(group_id=group_id).count()


def _can_read_groups(user: User, assignment: Assignment) -> bool:
    """Reads: any enrolled student, the course's teacher, or admin.

    A student sees the roster so they can choose which group to join;
    a teacher sees it to know who's still solo.
    """
    if user is None:
        return False
    if is_admin(user):
        return True
    course = _course_of(assignment)
    if course is None:
        return False
    # Course-scope teacher check reuses the same helper the assignment
    # editor already uses in routes/assignments.py.
    from utils.permissions import teaches_course_in_any_class
    if teaches_course_in_any_class(user, course):
        return True
    return has_active_enrollment(user, course)


# ---------------------------------------------------------------------------
# GET  /api/assignments/<aid>/groups
# ---------------------------------------------------------------------------
@assignment_groups_bp.route(
    "/assignments/<string:aid>/groups", methods=["GET"],
)
@login_required
def list_groups(aid: str):
    a = db.session.get(Assignment, aid)
    if a is None:
        return jsonify({"error": "Assignment not found."}), 404
    user = current_user()
    if not _can_read_groups(user, a):
        return jsonify({"error": "You do not have permission."}), 403
    if not a.is_group:
        # Return an empty list so the client can render "not a group
        # assignment" without a special error branch.
        return jsonify({"groups": [], "isGroup": False,
                        "maxGroupSize": a.max_group_size}), 200
    groups = (
        AssignmentGroup.query
        .filter_by(assignment_id=aid)
        .order_by(AssignmentGroup.created_at.asc())
        .all()
    )
    return jsonify({
        "groups": [g.to_dict() for g in groups],
        "isGroup": True,
        "maxGroupSize": a.max_group_size,
    }), 200


# ---------------------------------------------------------------------------
# POST /api/assignments/<aid>/groups     (student creates a new group)
# ---------------------------------------------------------------------------
@assignment_groups_bp.route(
    "/assignments/<string:aid>/groups", methods=["POST"],
)
@login_required
def create_group(aid: str):
    a = db.session.get(Assignment, aid)
    if a is None:
        return jsonify({"error": "Assignment not found."}), 404
    if not a.is_group:
        return jsonify({"error": "This assignment is not group-mode."}), 400
    if not a.is_published:
        return jsonify({"error": "Assignment is not published."}), 404

    user = current_user()
    if not is_student(user):
        return jsonify({"error": "Only students can create a group."}), 403
    course = _course_of(a)
    if course is None or not has_active_enrollment(user, course):
        return jsonify({"error": "You are not enrolled in this course."}), 403

    # One group per student per assignment — same-assignment membership
    # is unique enforced here (schema doesn't know the assignment_id).
    if _existing_membership(user, aid) is not None:
        return jsonify(
            {"error": "You are already in a group for this assignment."},
        ), 409

    try:
        payload = require_json(request.get_json(silent=True))
        require_fields(payload, ("name",))
        name = as_str(payload["name"], "name", max_len=80).strip()
        if not name:
            raise ValidationError("name must not be blank.")
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400

    # Phase 33 fix #11 — case-insensitive uniqueness per assignment.
    # Two "Team Alpha"s would leave the join UI ambiguous. App-side
    # rather than a DB constraint so we don't need a schema change.
    from sqlalchemy import func as _f
    dupe = (
        AssignmentGroup.query
        .filter_by(assignment_id=aid)
        .filter(_f.lower(AssignmentGroup.name) == name.lower())
        .first()
    )
    if dupe is not None:
        return jsonify(
            {"error": f"A group named '{name}' already exists for this assignment."},
        ), 409

    group = AssignmentGroup(
        assignment_id=aid,
        name=name,
        created_by_id=user.id,
    )
    db.session.add(group)
    db.session.flush()
    db.session.add(AssignmentGroupMember(
        group_id=group.id, student_id=user.id,
    ))
    db.session.commit()
    return jsonify(group.to_dict()), 201


# ---------------------------------------------------------------------------
# POST /api/assignment-groups/<gid>/join
# ---------------------------------------------------------------------------
@assignment_groups_bp.route(
    "/assignment-groups/<string:gid>/join", methods=["POST"],
)
@login_required
def join_group(gid: str):
    # Phase 33 fix #7 — take a row-level lock on the group before the
    # size check + insert so two students hitting "Join" in the same
    # instant can't both bypass `max_group_size`. On Postgres/MySQL
    # `with_for_update` blocks the peer transaction; on SQLite the
    # whole DB is single-writer so the ordering falls out naturally.
    g = (
        AssignmentGroup.query
        .filter_by(id=gid)
        .with_for_update()
        .first()
    )
    if g is None:
        return jsonify({"error": "Group not found."}), 404
    a = db.session.get(Assignment, g.assignment_id)
    if a is None or not a.is_group:
        return jsonify({"error": "Group's assignment is invalid."}), 400
    if not a.is_published:
        return jsonify({"error": "Assignment is not published."}), 404

    user = current_user()
    if not is_student(user):
        return jsonify({"error": "Only students can join a group."}), 403
    course = _course_of(a)
    if course is None or not has_active_enrollment(user, course):
        return jsonify({"error": "You are not enrolled in this course."}), 403

    if _existing_membership(user, g.assignment_id) is not None:
        return jsonify(
            {"error": "You are already in a group for this assignment."},
        ), 409
    if a.max_group_size is not None and _group_size(g.id) >= a.max_group_size:
        return jsonify({"error": "This group is full."}), 409

    db.session.add(AssignmentGroupMember(group_id=g.id, student_id=user.id))
    db.session.commit()
    return jsonify(g.to_dict()), 200


# ---------------------------------------------------------------------------
# POST /api/assignment-groups/<gid>/leave
# ---------------------------------------------------------------------------
@assignment_groups_bp.route(
    "/assignment-groups/<string:gid>/leave", methods=["POST"],
)
@login_required
def leave_group(gid: str):
    g = db.session.get(AssignmentGroup, gid)
    if g is None:
        return jsonify({"error": "Group not found."}), 404
    user = current_user()
    mem = AssignmentGroupMember.query.filter_by(
        group_id=gid, student_id=user.id,
    ).first()
    if mem is None:
        return jsonify({"error": "You are not in this group."}), 404
    db.session.delete(mem)
    # If that was the last member, drop the empty group so it doesn't
    # clutter the roster for the next student picking a slot.
    remaining = _group_size(gid) - 1  # session hasn't flushed yet
    if remaining <= 0:
        db.session.delete(g)
    db.session.commit()
    return jsonify({"ok": True}), 200


# ---------------------------------------------------------------------------
# DELETE /api/assignment-groups/<gid>  (creator or admin — empty groups only)
# ---------------------------------------------------------------------------
@assignment_groups_bp.route(
    "/assignment-groups/<string:gid>", methods=["DELETE"],
)
@login_required
def delete_group(gid: str):
    g = db.session.get(AssignmentGroup, gid)
    if g is None:
        return jsonify({"error": "Group not found."}), 404
    user = current_user()
    if not (is_admin(user) or g.created_by_id == user.id):
        return jsonify({"error": "You do not have permission."}), 403
    if _group_size(gid) > 0 and not is_admin(user):
        return jsonify(
            {"error": "Group still has members. Ask them to leave first."},
        ), 409
    db.session.delete(g)  # cascades to memberships
    db.session.commit()
    return jsonify({"ok": True}), 200
