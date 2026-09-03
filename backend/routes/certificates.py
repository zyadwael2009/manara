"""Certificate reads + public verify + admin revoke.

There is intentionally NO issue endpoint — issuance happens server-side,
inside the transactions of the write paths that could open the gate
(progress writes, grade writes, quiz submits/overrides, rubric change).
"""
from __future__ import annotations

from datetime import datetime

from flask import Blueprint, Response, jsonify, request

from models import Certificate, Enrollment, User, db
from routes.auth import current_user, login_required, require_admin
from utils.certificates import render_certificate_pdf
from utils.permissions import can_view_student_records, is_admin
from utils.rate_limit import check_rate
from utils.validation import ValidationError, as_str, require_json
from utils.time import utc_now

certificates_bp = Blueprint("certificates", __name__)


def _can_view_cert(user: User | None, cert: Certificate) -> bool:
    if user is None:
        return False
    if is_admin(user):
        return True
    enrollment = cert.enrollment
    if enrollment is None:
        return False
    student = enrollment.student
    if student is None:
        return False
    if student.id == user.id:
        return True
    return can_view_student_records(user, student)


# ---------------------------------------------------------------------------
# My certs
# ---------------------------------------------------------------------------
@certificates_bp.route("/certificates/mine", methods=["GET"])
@login_required
def list_my_certs():
    user = current_user()
    q = (
        Certificate.query.join(Enrollment, Enrollment.id == Certificate.enrollment_id)
        .filter(Enrollment.student_id == user.id)
        .order_by(Certificate.issued_at.desc())
    )
    # Phase 33 fix #25 — optional envelope pagination; bare-array
    # shape preserved for callers that don't pass `page`/`pageSize`.
    if request.args.get("page") or request.args.get("pageSize"):
        from utils.pagination import paginate
        return jsonify(paginate(
            q, render_item=lambda c: c.to_dict(include_names=True),
        )), 200
    rows = q.all()
    return jsonify([c.to_dict(include_names=True) for c in rows]), 200


# ---------------------------------------------------------------------------
# Detail
# ---------------------------------------------------------------------------
@certificates_bp.route("/certificates/<string:cert_id>", methods=["GET"])
@login_required
def get_cert(cert_id: str):
    cert = db.session.get(Certificate, cert_id)
    if cert is None:
        return jsonify({"error": "Certificate not found."}), 404
    if not _can_view_cert(current_user(), cert):
        return jsonify({"error": "You do not have permission."}), 403
    return jsonify(cert.to_dict(include_names=True)), 200


# ---------------------------------------------------------------------------
# PDF download
# ---------------------------------------------------------------------------
@certificates_bp.route("/certificates/<string:cert_id>/pdf", methods=["GET"])
@login_required
def get_cert_pdf(cert_id: str):
    cert = db.session.get(Certificate, cert_id)
    if cert is None:
        return jsonify({"error": "Certificate not found."}), 404
    if not _can_view_cert(current_user(), cert):
        return jsonify({"error": "You do not have permission."}), 403
    # Build a verify-URL prefix from the request scheme + host.
    verify_base = f"{request.scheme}://{request.host}"
    pdf_bytes = render_certificate_pdf(cert, verify_base_url=verify_base)
    filename = f"certificate-{cert.certificate_number}.pdf"
    return Response(
        pdf_bytes,
        mimetype="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{filename}"',
        },
    )


# ---------------------------------------------------------------------------
# Admin revoke
# ---------------------------------------------------------------------------
@certificates_bp.route("/certificates/<string:cert_id>/revoke", methods=["POST"])
@require_admin
def revoke_cert(cert_id: str):
    cert = db.session.get(Certificate, cert_id)
    if cert is None:
        return jsonify({"error": "Certificate not found."}), 404
    try:
        payload = require_json(request.get_json(silent=True))
        reason = as_str(payload.get("reason") or "", "reason", max_len=500) or None
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400
    if cert.revoked:
        return jsonify({"error": "Certificate is already revoked."}), 409
    cert.revoked = True
    cert.revoked_at = utc_now()
    cert.revoked_reason = reason
    cert.revoked_by_id = current_user().id
    db.session.commit()
    return jsonify(cert.to_dict(include_names=True)), 200


# ---------------------------------------------------------------------------
# PUBLIC verify — no auth, restricted response shape
# ---------------------------------------------------------------------------
@certificates_bp.route("/verify/<string:cert_number>", methods=["GET"])
def public_verify(cert_number: str):
    """Anyone with the cert number can verify it exists. Returns limited
    fields (name, course, date, revoked status). No enrollment/grade
    internals ever leak here.

    Phase 11 audit fix L2: rate-limited to 30 req/min/IP so the 64-bit
    number space isn't grindable at internet speed. Enough headroom for a
    hiring manager pasting a URL, tight enough to make bulk enumeration
    a many-year job even from a botnet.
    """
    ip = request.remote_addr or "-"
    ok, retry_after = check_rate("verify", ip, limit=30, window=60)
    if not ok:
        resp = jsonify({"error": "Too many requests. Try again shortly."})
        resp.status_code = 429
        resp.headers["Retry-After"] = str(retry_after)
        return resp
    cert = Certificate.query.filter_by(certificate_number=cert_number).first()
    if cert is None:
        return jsonify({"error": "Certificate not found."}), 404
    return jsonify(cert.public_to_dict()), 200
