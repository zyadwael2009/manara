"""Phase 27 — video-inline checkpoints.

One `VideoCheckpoint` = one pause-point on a video lesson. The client
(`_VideoBody` in `lesson_viewer_screen.dart`) pauses at
`position_seconds`, shows the MC prompt, and only resumes when the
student's choice matches `correct_option_id`.

There is deliberately **no** attempts table:
  * A wrong pick just retries in-place; nothing is recorded server-side.
  * The lesson's progress marker still fires from the existing progress
    endpoint once every checkpoint has been answered — that gate lives
    client-side because we don't need to defend a grade with it.

Endpoints (all under `/api`):
  * `GET  /lessons/<lid>/checkpoints` — student sees them WITHOUT the
    correct answer; owner sees the full row.
  * `POST /lessons/<lid>/checkpoints` — owner adds one.
  * `PUT  /checkpoints/<cid>`        — owner edits.
  * `DELETE /checkpoints/<cid>`      — owner removes.

Trust-core: touches no grade or enrollment state.
"""
from __future__ import annotations

import json

from flask import Blueprint, jsonify, request

from models import Lesson, VideoCheckpoint, db
from routes.auth import current_user, login_required
from utils.permissions import (
    can_edit_lesson,
    has_active_enrollment,
    is_admin,
    teaches_course_in_any_class,
)
from utils.validation import (
    ValidationError,
    as_str,
    require_fields,
    require_json,
)

checkpoints_bp = Blueprint("checkpoints", __name__)


def _parse_options(raw) -> tuple[list[dict], set[str]]:
    """Validate the incoming options list and return (parsed, id_set)."""
    if not isinstance(raw, list) or not raw:
        raise ValidationError("options must be a non-empty list.")
    if len(raw) > 8:
        raise ValidationError("A checkpoint can have at most 8 options.")
    parsed: list[dict] = []
    ids: set[str] = set()
    for i, opt in enumerate(raw):
        if not isinstance(opt, dict):
            raise ValidationError(f"options[{i}] must be an object.")
        oid = as_str(opt.get("id") or "", f"options[{i}].id", max_len=40)
        text = as_str(opt.get("text") or "", f"options[{i}].text", max_len=200)
        if oid in ids:
            raise ValidationError(f"options[{i}].id '{oid}' is duplicated.")
        ids.add(oid)
        parsed.append({"id": oid, "text": text})
    return parsed, ids


def _lesson_course(lesson: Lesson):
    """Follow `lesson → module → course`; return None if orphaned."""
    m = lesson.module if lesson else None
    return m.course if m is not None else None


def _can_see_lesson(user, lesson: Lesson) -> bool:
    """Read-access rule: owners always; students only when enrolled."""
    if user is None:
        return False
    if is_admin(user):
        return True
    course = _lesson_course(lesson)
    if course is None:
        return False
    if teaches_course_in_any_class(user, course):
        return True
    return has_active_enrollment(user, course)


# ---------------------------------------------------------------------------
# GET /api/lessons/<lid>/checkpoints
# ---------------------------------------------------------------------------
@checkpoints_bp.route("/lessons/<string:lid>/checkpoints", methods=["GET"])
@login_required
def list_checkpoints(lid: str):
    lesson = db.session.get(Lesson, lid)
    if lesson is None:
        return jsonify({"error": "Lesson not found."}), 404
    user = current_user()
    if not _can_see_lesson(user, lesson):
        return jsonify({"error": "You do not have permission."}), 403

    # Owner (admin or the course's teacher) sees the correct answer so
    # they can preview + edit; students never do — they judge their
    # choice client-side against what the server returns.
    is_owner = is_admin(user) or (
        _lesson_course(lesson) is not None
        and teaches_course_in_any_class(user, _lesson_course(lesson))
    )
    rows = (
        VideoCheckpoint.query
        .filter_by(lesson_id=lid)
        .order_by(VideoCheckpoint.position_seconds.asc())
        .all()
    )
    return jsonify([r.to_dict(hide_answer=not is_owner) for r in rows]), 200


# ---------------------------------------------------------------------------
# POST /api/lessons/<lid>/checkpoints
# ---------------------------------------------------------------------------
@checkpoints_bp.route("/lessons/<string:lid>/checkpoints", methods=["POST"])
@login_required
def create_checkpoint(lid: str):
    lesson = db.session.get(Lesson, lid)
    if lesson is None:
        return jsonify({"error": "Lesson not found."}), 404
    user = current_user()
    if not can_edit_lesson(user, lesson):
        return jsonify({"error": "You do not have permission."}), 403
    if lesson.type != "video":
        return jsonify(
            {"error": "Checkpoints only apply to video lessons."}
        ), 400

    try:
        payload = require_json(request.get_json(silent=True))
        require_fields(payload, ("positionSeconds", "prompt", "options"))
        pos = payload.get("positionSeconds")
        if not isinstance(pos, int) or pos < 0 or pos > 60 * 60 * 24:
            raise ValidationError("positionSeconds must be an integer 0..86400.")
        prompt = as_str(payload.get("prompt") or "", "prompt", max_len=500)
        opts, ids = _parse_options(payload.get("options"))
        correct = payload.get("correctOptionId")
        if correct is not None:
            correct = as_str(correct, "correctOptionId", max_len=40)
            if correct not in ids:
                raise ValidationError(
                    "correctOptionId must reference one of options[].id.")
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400

    cp = VideoCheckpoint(
        lesson_id=lid,
        position_seconds=pos,
        prompt=prompt,
        correct_option_id=correct,
        options_json=json.dumps(opts),
    )
    db.session.add(cp)
    db.session.commit()
    return jsonify(cp.to_dict()), 201


# ---------------------------------------------------------------------------
# PUT /api/checkpoints/<cid>
# ---------------------------------------------------------------------------
@checkpoints_bp.route("/checkpoints/<string:cid>", methods=["PUT", "PATCH"])
@login_required
def update_checkpoint(cid: str):
    cp = db.session.get(VideoCheckpoint, cid)
    if cp is None:
        return jsonify({"error": "Checkpoint not found."}), 404
    lesson = db.session.get(Lesson, cp.lesson_id)
    user = current_user()
    if lesson is None or not can_edit_lesson(user, lesson):
        return jsonify({"error": "You do not have permission."}), 403

    try:
        payload = require_json(request.get_json(silent=True))
        if "positionSeconds" in payload:
            pos = payload["positionSeconds"]
            if not isinstance(pos, int) or pos < 0 or pos > 60 * 60 * 24:
                raise ValidationError(
                    "positionSeconds must be an integer 0..86400.")
            cp.position_seconds = pos
        if "prompt" in payload:
            cp.prompt = as_str(payload["prompt"] or "", "prompt", max_len=500)
        if "options" in payload:
            opts, ids = _parse_options(payload["options"])
            cp.options_json = json.dumps(opts)
            # If the previously-correct id no longer exists, drop it —
            # avoids a dangling reference that would gray out every
            # student's answer.
            if cp.correct_option_id and cp.correct_option_id not in ids:
                cp.correct_option_id = None
        if "correctOptionId" in payload:
            raw = payload["correctOptionId"]
            if raw in (None, ""):
                cp.correct_option_id = None
            else:
                raw = as_str(raw, "correctOptionId", max_len=40)
                # Re-derive current ids so we validate against the
                # freshly-updated options if they were changed above.
                try:
                    ids = {o["id"] for o in json.loads(cp.options_json or "[]")}
                except Exception:
                    ids = set()
                if raw not in ids:
                    raise ValidationError(
                        "correctOptionId must reference one of options[].id.")
                cp.correct_option_id = raw
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400

    db.session.commit()
    return jsonify(cp.to_dict()), 200


# ---------------------------------------------------------------------------
# DELETE /api/checkpoints/<cid>
# ---------------------------------------------------------------------------
@checkpoints_bp.route("/checkpoints/<string:cid>", methods=["DELETE"])
@login_required
def delete_checkpoint(cid: str):
    cp = db.session.get(VideoCheckpoint, cid)
    if cp is None:
        return jsonify({"error": "Checkpoint not found."}), 404
    lesson = db.session.get(Lesson, cp.lesson_id)
    user = current_user()
    if lesson is None or not can_edit_lesson(user, lesson):
        return jsonify({"error": "You do not have permission."}), 403
    db.session.delete(cp)
    db.session.commit()
    return jsonify({"ok": True}), 200
