"""Phase 32 · T3 — curriculum standards + tags + mastery reads.

Writes are admin-only:
  * POST /api/standards — create.
  * PUT /api/standards/<id> — edit.
  * DELETE /api/standards/<id> — remove (cascades tags).
  * POST /api/standards/<id>/tags — tag a lesson/quiz/assignment.
  * DELETE /api/standard-tags/<tag_id> — untag.

Reads:
  * GET /api/standards — list (any authed user).
  * GET /api/standards/<id>/coverage — which content is tagged.
  * GET /api/<taggable_type>/<taggable_id>/standards — inverse lookup
    for the content editor.
  * GET /api/students/<sid>/standards-mastery — per-standard mastery
    rollup; readable by admin, the student, or a linked parent.

Trust-core: no writes to grades, enrollments, or certificates. Mastery
is a derived read across existing quiz + assignment rows.
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from models import (
    STANDARD_TAGGABLE_TYPES,
    Assignment,
    Lesson,
    Quiz,
    Standard,
    StandardTag,
    User,
    db,
)
from routes.auth import current_user, login_required, require_admin
from utils.permissions import is_admin, is_linked_parent_of
from utils.validation import (
    ValidationError,
    as_str,
    one_of,
    require_fields,
    require_json,
)

standards_bp = Blueprint("standards", __name__)


# ---------------------------------------------------------------------------
# Standards CRUD
# ---------------------------------------------------------------------------
@standards_bp.route("/standards", methods=["GET"])
@login_required
def list_standards():
    subject = request.args.get("subject")
    q = Standard.query
    if subject:
        q = q.filter_by(subject=subject)
    rows = q.order_by(Standard.code.asc()).all()
    return jsonify([r.to_dict() for r in rows]), 200


@standards_bp.route("/standards", methods=["POST"])
@require_admin
def create_standard():
    try:
        payload = require_json(request.get_json(silent=True))
        require_fields(payload, ("code", "name"))
        code = as_str(payload["code"], "code", max_len=80)
        name = as_str(payload["name"], "name", max_len=200)
        description = as_str(
            payload.get("description") or "", "description", max_len=5000,
        )
        subject = payload.get("subject")
        if subject is not None:
            subject = as_str(subject, "subject", max_len=80) or None
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400
    # Phase 33 fix #17 — the pre-check was a race; two admins running
    # a bulk import could both pass and one would 500 on the DB's
    # unique constraint on `code`. Savepoint the insert and translate
    # the IntegrityError into a friendly 409.
    from sqlalchemy.exc import IntegrityError
    if Standard.query.filter_by(code=code).first():
        return jsonify({"error": "A standard with that code already exists."}), 409
    st = Standard(
        code=code, name=name, description=description, subject=subject,
    )
    try:
        with db.session.begin_nested():
            db.session.add(st)
    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": "A standard with that code already exists."}), 409
    db.session.commit()
    return jsonify(st.to_dict()), 201


@standards_bp.route("/standards/<string:sid>", methods=["PUT", "PATCH"])
@require_admin
def update_standard(sid: str):
    st = db.session.get(Standard, sid)
    if st is None:
        return jsonify({"error": "Standard not found."}), 404
    try:
        payload = require_json(request.get_json(silent=True))
        if "code" in payload:
            code = as_str(payload["code"], "code", max_len=80)
            if code != st.code and Standard.query.filter_by(code=code).first():
                return jsonify({"error": "That code is already taken."}), 409
            st.code = code
        if "name" in payload:
            st.name = as_str(payload["name"], "name", max_len=200)
        if "description" in payload:
            st.description = as_str(
                payload["description"], "description", max_len=5000,
            )
        if "subject" in payload:
            raw = payload["subject"]
            st.subject = None if raw in (None, "") else as_str(
                raw, "subject", max_len=80) or None
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400
    db.session.commit()
    return jsonify(st.to_dict()), 200


@standards_bp.route("/standards/<string:sid>", methods=["DELETE"])
@require_admin
def delete_standard(sid: str):
    st = db.session.get(Standard, sid)
    if st is None:
        return jsonify({"error": "Standard not found."}), 404
    # Cascade tags manually — no cascade= on the relationship because
    # the join is polymorphic.
    StandardTag.query.filter_by(standard_id=sid).delete()
    db.session.delete(st)
    db.session.commit()
    return jsonify({"ok": True}), 200


# ---------------------------------------------------------------------------
# Tag / untag content
# ---------------------------------------------------------------------------
def _target_exists(taggable_type: str, taggable_id: str) -> bool:
    if taggable_type == "lesson":
        return db.session.get(Lesson, taggable_id) is not None
    if taggable_type == "quiz":
        return db.session.get(Quiz, taggable_id) is not None
    if taggable_type == "assignment":
        return db.session.get(Assignment, taggable_id) is not None
    return False


@standards_bp.route("/standards/<string:sid>/tags", methods=["POST"])
@require_admin
def create_tag(sid: str):
    st = db.session.get(Standard, sid)
    if st is None:
        return jsonify({"error": "Standard not found."}), 404
    try:
        payload = require_json(request.get_json(silent=True))
        require_fields(payload, ("taggableType", "taggableId"))
        taggable_type = one_of(
            payload["taggableType"], STANDARD_TAGGABLE_TYPES, "taggableType",
        )
        taggable_id = as_str(
            payload["taggableId"], "taggableId", max_len=36,
        )
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400
    if not _target_exists(taggable_type, taggable_id):
        return jsonify(
            {"error": f"No {taggable_type} with id {taggable_id}."},
        ), 404
    existing = StandardTag.query.filter_by(
        standard_id=sid,
        taggable_type=taggable_type,
        taggable_id=taggable_id,
    ).first()
    if existing is not None:
        return jsonify(existing.to_dict()), 200
    tag = StandardTag(
        standard_id=sid,
        taggable_type=taggable_type,
        taggable_id=taggable_id,
    )
    db.session.add(tag)
    db.session.commit()
    return jsonify(tag.to_dict()), 201


@standards_bp.route("/standard-tags/<string:tid>", methods=["DELETE"])
@require_admin
def delete_tag(tid: str):
    tag = db.session.get(StandardTag, tid)
    if tag is None:
        return jsonify({"error": "Tag not found."}), 404
    db.session.delete(tag)
    db.session.commit()
    return jsonify({"ok": True}), 200


# ---------------------------------------------------------------------------
# Read: coverage + inverse-lookup + mastery
# ---------------------------------------------------------------------------
@standards_bp.route("/standards/<string:sid>/coverage", methods=["GET"])
@login_required
def standard_coverage(sid: str):
    st = db.session.get(Standard, sid)
    if st is None:
        return jsonify({"error": "Standard not found."}), 404
    # Phase 33 fix #9 — was leaking unreleased quiz titles across the
    # whole school. Filter tags to content the caller can see:
    #   * admin → everything
    #   * teacher → content in courses they teach
    #   * student → content in courses they're enrolled in
    from models import Enrollment, Module
    from utils.permissions import can_view_content
    caller = current_user()
    tags = StandardTag.query.filter_by(standard_id=sid).all()

    def _course_of(t: StandardTag):
        if t.taggable_type == "lesson":
            l = db.session.get(Lesson, t.taggable_id)
            m = l.module if l else None
            return m.course if m else None
        if t.taggable_type == "quiz":
            q = db.session.get(Quiz, t.taggable_id)
            m = q.module if q else None
            return m.course if m else None
        if t.taggable_type == "assignment":
            a = db.session.get(Assignment, t.taggable_id)
            m = a.module if a else None
            return m.course if m else None
        return None

    def _title(t: StandardTag) -> str:
        if t.taggable_type == "lesson":
            l = db.session.get(Lesson, t.taggable_id)
            return l.title if l else "(missing lesson)"
        if t.taggable_type == "quiz":
            q = db.session.get(Quiz, t.taggable_id)
            return q.title if q else "(missing quiz)"
        if t.taggable_type == "assignment":
            a = db.session.get(Assignment, t.taggable_id)
            return a.title if a else "(missing assignment)"
        return "(unknown)"

    if is_admin(caller):
        visible = tags
    else:
        visible = [
            t for t in tags
            if (
                _course_of(t) is not None
                and can_view_content(caller, _course_of(t))
            )
        ]
    return jsonify({
        "standard": st.to_dict(),
        "tags": [
            {**t.to_dict(), "targetTitle": _title(t)} for t in visible
        ],
    }), 200


@standards_bp.route(
    "/standards/for-content/<string:taggable_type>/<string:taggable_id>",
    methods=["GET"],
)
@login_required
def standards_for_content(taggable_type: str, taggable_id: str):
    """Inverse lookup — every standard tagged onto this piece of
    content. Used by the lesson/quiz/assignment editor to render the
    "tagged standards" pill row.

    Phase 33 fix #8 — route was originally
    `/api/<taggable_type>/<taggable_id>/standards`, which as a
    2-segment prefix matched ANY `/api/x/y/standards` under
    `/api` and only required `@login_required`. Any authenticated
    user could enumerate standard tags on content from a different
    grade / class. Narrowed the URL and added a course-scope check.
    """
    if taggable_type not in STANDARD_TAGGABLE_TYPES:
        return jsonify({"error": "Unknown taggable type."}), 400

    # Resolve the containing course + gate on the caller's view scope.
    from utils.permissions import can_view_content
    course = None
    if taggable_type == "lesson":
        l = db.session.get(Lesson, taggable_id)
        m = l.module if l else None
        course = m.course if m else None
    elif taggable_type == "quiz":
        q = db.session.get(Quiz, taggable_id)
        m = q.module if q else None
        course = m.course if m else None
    elif taggable_type == "assignment":
        a = db.session.get(Assignment, taggable_id)
        m = a.module if a else None
        course = m.course if m else None
    if course is None:
        return jsonify({"error": "Content not found."}), 404
    caller = current_user()
    if not (is_admin(caller) or can_view_content(caller, course)):
        return jsonify({"error": "You do not have permission."}), 403

    tags = StandardTag.query.filter_by(
        taggable_type=taggable_type, taggable_id=taggable_id,
    ).all()
    if not tags:
        return jsonify([]), 200
    standards = Standard.query.filter(
        Standard.id.in_([t.standard_id for t in tags])
    ).all()
    by_id = {s.id: s for s in standards}
    return jsonify([
        {**by_id[t.standard_id].to_dict(), "tagId": t.id}
        for t in tags if t.standard_id in by_id
    ]), 200


@standards_bp.route(
    "/students/<string:sid>/standards-mastery",
    methods=["GET"],
)
@login_required
def student_mastery(sid: str):
    student = db.session.get(User, sid)
    if student is None:
        return jsonify({"error": "Student not found."}), 404
    caller = current_user()
    if not (
        is_admin(caller)
        or caller.id == sid
        or is_linked_parent_of(caller, student)
    ):
        return jsonify({"error": "You do not have permission."}), 403
    from utils.standards import compute_student_mastery
    return jsonify({
        "studentId": sid,
        "standards": compute_student_mastery(sid),
    }), 200
