"""Phase 21 — direct messages between one parent and one teacher.

Threads are keyed on (parent_id, teacher_id, subject). A parent starts a
thread addressed to a teacher of one of their children; a teacher starts
one addressed to a parent of one of their students. Everyone else 403s.

Reads scope to threads where the caller is either the parent or teacher.
Sends also enqueue a bell notification for the recipient.
"""
from __future__ import annotations

from datetime import datetime

from flask import Blueprint, jsonify, request

from models import (
    ClassCourseTeacher,
    Message,
    MessageThread,
    ParentStudentLink,
    SchoolClass,
    User,
    db,
)
from routes.auth import current_user, login_required
from utils.notifications import enqueue
from utils.permissions import is_admin, is_instructor, is_parent
from utils.validation import (
    ValidationError,
    as_str,
    require_fields,
    require_json,
)
from utils.time import utc_now

messages_bp = Blueprint("messages", __name__)


def _shared_children(parent: User, teacher: User) -> list[str]:
    """Student ids that (a) `parent` is linked to AND
    (b) `teacher` teaches or homerooms.
    """
    child_ids = {
        l.student_id
        for l in ParentStudentLink.query.filter_by(parent_id=parent.id).all()
    }
    if not child_ids:
        return []
    children = User.query.filter(User.id.in_(child_ids)).all()
    # Classes the teacher homerooms.
    homeroom_class_ids = {
        c.id for c in SchoolClass.query.filter_by(homeroom_teacher_id=teacher.id).all()
    }
    # Classes the teacher teaches any course in.
    teach_class_ids = {
        cct.class_id
        for cct in ClassCourseTeacher.query.filter_by(teacher_id=teacher.id).all()
    }
    reachable_class_ids = homeroom_class_ids | teach_class_ids
    return [c.id for c in children if c.class_id in reachable_class_ids]


def _can_pair_communicate(a: User, b: User) -> bool:
    """True ONLY when the pair is a genuine (parent, teacher) match with
    a shared student. The MessageThread schema promises
    `parent_id.role == 'parent'` and `teacher_id.role == 'instructor'`;
    any other pairing violates the invariant.

    Phase 25 hard-audit fix H-1: the previous version returned True for
    ANY pair where either side was an admin, which let an admin open
    threads with students / other admins and baked their id into
    `parent_id`, breaking the schema promise. Admin is no longer a free
    pass here — admin-to-anyone messages are out of scope for this
    surface. (An admin who genuinely needs to reach a parent or teacher
    can still author under the parent/teacher role via the admin office
    if we later add that flow.)
    """
    if a is None or b is None:
        return False
    parent, teacher = None, None
    if is_parent(a) and is_instructor(b):
        parent, teacher = a, b
    elif is_parent(b) and is_instructor(a):
        parent, teacher = b, a
    if parent is None or teacher is None:
        return False
    return bool(_shared_children(parent, teacher))


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------
@messages_bp.route("/messages/threads/mine", methods=["GET"])
@messages_bp.route("/messages/threads/mine/", methods=["GET"])
@login_required
def my_threads():
    """List conversations for the caller.

    Phase 29 · T3 — pagination. `?page=N&pageSize=M` (max 50). When
    no page is supplied the response is a **plain array** (back-compat
    with clients from before the pagination sweep); when either `page`
    or `pageSize` is supplied it becomes the paged envelope
    `{items, page, pageSize, hasMore}`.
    """
    user = current_user()
    q = MessageThread.query.filter(
        db.or_(MessageThread.parent_id == user.id,
               MessageThread.teacher_id == user.id)
    ).order_by(MessageThread.last_message_at.desc())

    if not request.args.get("page") and not request.args.get("pageSize"):
        # Legacy bare-array shape.
        rows = q.all()
        return jsonify([t.to_dict(viewer_id=user.id) for t in rows]), 200

    from utils.pagination import paginate
    page = paginate(q, render_item=lambda t: t.to_dict(viewer_id=user.id))
    return jsonify(page), 200


@messages_bp.route("/messages/threads/<string:tid>", methods=["GET"])
@login_required
def get_thread(tid: str):
    user = current_user()
    t = db.session.get(MessageThread, tid)
    if t is None:
        return jsonify({"error": "Thread not found."}), 404
    if user.id not in (t.parent_id, t.teacher_id) and not is_admin(user):
        return jsonify({"error": "You do not have permission."}), 403

    msgs = t.messages.order_by(Message.created_at.asc()).all()
    # Mark the OTHER party's messages as read by this viewer.
    now = utc_now()
    for m in msgs:
        if m.author_id != user.id and m.read_by_other_at is None:
            m.read_by_other_at = now
    db.session.commit()

    return jsonify({
        "thread": t.to_dict(viewer_id=user.id),
        "messages": [m.to_dict() for m in msgs],
    }), 200


# ---------------------------------------------------------------------------
# Writes
# ---------------------------------------------------------------------------
@messages_bp.route("/messages/threads", methods=["POST"])
@login_required
def create_thread():
    """Body: `{recipientId, subject, body}`. Recipient must be the
    opposite role of the caller (parent ↔ teacher), and must reach a
    shared student."""
    try:
        payload = require_json(request.get_json(silent=True))
        require_fields(payload, ("recipientId", "subject", "body"))
        recipient_id = as_str(payload["recipientId"], "recipientId")
        subject = as_str(payload["subject"], "subject", max_len=200)
        body = as_str(payload["body"], "body", max_len=5000)
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400
    if not body.strip() or not subject.strip():
        return jsonify({"error": "subject and body are required."}), 400

    user = current_user()
    recipient = db.session.get(User, recipient_id)
    if recipient is None:
        return jsonify({"error": "Recipient not found."}), 404
    if not _can_pair_communicate(user, recipient):
        return jsonify({"error": "You cannot message this user."}), 403

    parent = user if is_parent(user) else recipient
    teacher = recipient if parent is user else user
    # Reuse an existing thread on the same subject if one exists.
    thread = MessageThread.query.filter_by(
        parent_id=parent.id, teacher_id=teacher.id, subject=subject.strip(),
    ).first()
    if thread is None:
        thread = MessageThread(
            parent_id=parent.id,
            teacher_id=teacher.id,
            subject=subject.strip(),
        )
        db.session.add(thread)
        db.session.flush()

    msg = Message(thread_id=thread.id, author_id=user.id, body=body.strip())
    db.session.add(msg)
    thread.last_message_at = utc_now()

    # Ping the recipient's bell.
    enqueue(
        recipient.id,
        kind="message",
        title=f"New message from {user.name}",
        body=msg.body[:280],
        ref_type="thread",
        ref_id=thread.id,
    )
    db.session.commit()
    return jsonify({
        "thread": thread.to_dict(viewer_id=user.id),
        "message": msg.to_dict(),
    }), 201


@messages_bp.route("/messages/threads/<string:tid>/messages", methods=["POST"])
@login_required
def reply_thread(tid: str):
    user = current_user()
    t = db.session.get(MessageThread, tid)
    if t is None:
        return jsonify({"error": "Thread not found."}), 404
    if user.id not in (t.parent_id, t.teacher_id) and not is_admin(user):
        return jsonify({"error": "You do not have permission."}), 403
    try:
        payload = require_json(request.get_json(silent=True))
        require_fields(payload, ("body",))
        body = as_str(payload["body"], "body", max_len=5000)
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400
    if not body.strip():
        return jsonify({"error": "body is required."}), 400

    msg = Message(thread_id=t.id, author_id=user.id, body=body.strip())
    db.session.add(msg)
    t.last_message_at = utc_now()
    other_id = t.parent_id if user.id == t.teacher_id else t.teacher_id
    enqueue(
        other_id,
        kind="message",
        title=f"New reply from {user.name}",
        body=msg.body[:280],
        ref_type="thread",
        ref_id=t.id,
    )
    db.session.commit()
    return jsonify(msg.to_dict()), 201
