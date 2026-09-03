"""Phase 32 · T2 — diploma reads + verify + revoke + PDF.

Reads:
  * student — their own diploma via `/api/diplomas/mine`.
  * admin — any student's diploma via `/api/students/<sid>/diploma`.
  * linked parent — their child's diploma via the same path.
  * public (no auth) — verify by number via `/api/verify-diploma/<num>`.

Writes:
  * admin only — revoke / restore via `/api/diplomas/<id>/revoke`.

Trust-core: touches no grade or enrollment state. Auto-issuance
lives in `routes/classes.py::graduate_class` via `utils.diplomas`.
"""
from __future__ import annotations

from flask import Blueprint, Response, current_app, jsonify, request

from models import Diploma, User, db
from routes.auth import current_user, login_required, require_admin
from utils.permissions import is_admin, is_linked_parent_of
from utils.rate_limit import check_rate
from utils.time import utc_now
from utils.validation import (
    ValidationError,
    as_str,
    require_json,
)

diplomas_bp = Blueprint("diplomas", __name__)


def _can_read_student_diploma(caller: User, student: User) -> bool:
    if caller is None or student is None:
        return False
    if is_admin(caller):
        return True
    if caller.id == student.id:
        return True
    if is_linked_parent_of(caller, student):
        return True
    return False


# ---------------------------------------------------------------------------
# GET /api/diplomas/mine  (student self)
# ---------------------------------------------------------------------------
@diplomas_bp.route("/diplomas/mine", methods=["GET"])
@login_required
def my_diploma():
    caller = current_user()
    dip = (
        Diploma.query.filter_by(student_id=caller.id)
        .order_by(Diploma.class_of_year.desc())
        .first()
    )
    if dip is None:
        return jsonify({"diploma": None}), 200
    return jsonify({"diploma": dip.to_dict(include_student=True)}), 200


# ---------------------------------------------------------------------------
# GET /api/students/<sid>/diploma
# ---------------------------------------------------------------------------
@diplomas_bp.route("/students/<string:sid>/diploma", methods=["GET"])
@login_required
def student_diploma(sid: str):
    student = db.session.get(User, sid)
    if student is None:
        return jsonify({"error": "Student not found."}), 404
    caller = current_user()
    if not _can_read_student_diploma(caller, student):
        return jsonify({"error": "You do not have permission."}), 403
    dip = (
        Diploma.query.filter_by(student_id=sid)
        .order_by(Diploma.class_of_year.desc())
        .first()
    )
    if dip is None:
        return jsonify({"diploma": None}), 200
    return jsonify({"diploma": dip.to_dict(include_student=True)}), 200


# ---------------------------------------------------------------------------
# GET /api/verify-diploma/<num>   (public, no auth)
# ---------------------------------------------------------------------------
@diplomas_bp.route("/verify-diploma/<string:num>", methods=["GET"])
def verify_diploma(num: str):
    # Phase 33 fix #1 — same rate-limit shape the cert verify path
    # uses (Phase 11 L2). Without it a 32-bit tail (now widened to
    # 64 bits in `_make_number`) was grindable at internet speed.
    ip = request.remote_addr or "-"
    ok, retry_after = check_rate("verify_diploma", ip, limit=30, window=60)
    if not ok:
        resp = jsonify({"error": "Too many requests. Try again shortly."})
        resp.status_code = 429
        resp.headers["Retry-After"] = str(retry_after)
        return resp
    dip = Diploma.query.filter_by(diploma_number=num).first()
    if dip is None:
        return jsonify({"found": False}), 404
    student = db.session.get(User, dip.student_id)
    return jsonify({
        "found": True,
        "diplomaNumber": dip.diploma_number,
        "studentName": student.name if student else None,
        "classOfYear": dip.class_of_year,
        "honors": dip.honors,
        "revoked": dip.revoked,
        "revokedReason": dip.revoked_reason if dip.revoked else None,
        "issuedAt": dip.issued_at.isoformat() if dip.issued_at else None,
    }), 200


# ---------------------------------------------------------------------------
# POST /api/diplomas/<id>/revoke  (admin)
#
# Body: { "reason": "...", "restore": bool? }
# When `restore` is true, un-revokes the diploma and clears the reason.
# ---------------------------------------------------------------------------
@diplomas_bp.route("/diplomas/<string:did>/revoke", methods=["POST"])
@require_admin
def revoke_diploma(did: str):
    dip = db.session.get(Diploma, did)
    if dip is None:
        return jsonify({"error": "Diploma not found."}), 404
    caller = current_user()
    try:
        payload = require_json(request.get_json(silent=True))
        restore = bool(payload.get("restore", False))
        reason = payload.get("reason")
        if reason is not None:
            reason = as_str(reason, "reason", max_len=500) or None
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400
    if restore:
        dip.revoked = False
        dip.revoked_at = None
        dip.revoked_reason = None
        dip.revoked_by_id = None
    else:
        dip.revoked = True
        dip.revoked_at = utc_now()
        dip.revoked_reason = reason
        dip.revoked_by_id = caller.id
    db.session.commit()
    return jsonify(dip.to_dict(include_student=True)), 200


# ---------------------------------------------------------------------------
# GET /api/students/<sid>/diploma.pdf
# ---------------------------------------------------------------------------
@diplomas_bp.route("/students/<string:sid>/diploma.pdf", methods=["GET"])
@login_required
def student_diploma_pdf(sid: str):
    student = db.session.get(User, sid)
    if student is None:
        return jsonify({"error": "Student not found."}), 404
    caller = current_user()
    if not _can_read_student_diploma(caller, student):
        return jsonify({"error": "You do not have permission."}), 403
    dip = (
        Diploma.query.filter_by(student_id=sid)
        .order_by(Diploma.class_of_year.desc())
        .first()
    )
    if dip is None:
        return jsonify({"error": "No diploma on file."}), 404
    from utils.pdf import render_diploma_pdf
    try:
        pdf = render_diploma_pdf(diploma=dip, student=student)
    except Exception as e:  # pragma: no cover - reportlab breakage
        current_app.logger.warning("diploma pdf failed: %r", e)
        return jsonify({"error": "Could not render diploma."}), 500
    return Response(
        pdf,
        mimetype="application/pdf",
        headers={
            "Content-Disposition":
                f'inline; filename="diploma-{dip.diploma_number}.pdf"',
        },
    )
