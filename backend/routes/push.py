"""Phase 28 — Web Push subscribe / unsubscribe / public-key.

The client:
  1. GETs `/api/push/public-key` and passes the returned key into
     `navigator.serviceWorker.getRegistration().pushManager.subscribe()`.
  2. POSTs `/api/push/subscribe` with the browser's `PushSubscription`
     JSON (endpoint + keys.p256dh + keys.auth).
  3. Optionally POSTs `/api/push/unsubscribe` on sign-out or user opt-out.

Trust-core: no writes to grades, enrollments, or certificates. Subs are
tied to the caller (`user_id = current_user().id`); unsubscribing your
own endpoint is allowed but you can't touch anyone else's row.
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from models import PushSubscription, db
from routes.auth import current_user, login_required
from utils.push import load_or_create_keys, push_available
from utils.validation import (
    ValidationError,
    as_str,
    require_json,
)
from utils.time import utc_now

push_bp = Blueprint("push", __name__)


@push_bp.route("/push/public-key", methods=["GET"])
@login_required
def public_key():
    """Return {"publicKey": "<base64url>"} or {"pushEnabled": false}
    when the server can't sign VAPID (missing deps, unwritable dir)."""
    keys = load_or_create_keys()
    if not keys:
        return jsonify({"pushEnabled": False, "publicKey": None}), 200
    return jsonify({
        "pushEnabled": push_available(),
        "publicKey": keys["public_key"],
    }), 200


@push_bp.route("/push/subscribe", methods=["POST"])
@login_required
def subscribe():
    """Register a push endpoint for the caller.

    Two payload shapes are accepted:

      * Web (browser Push API):
          {
            "endpoint": "https://...",
            "keys": {"p256dh": "...", "auth": "..."},
            "platform": "web"    # or omitted
          }

      * Mobile (Phase 29 · T4 scaffolding — FCM / APNs):
          {
            "token": "<device-token>",
            "platform": "fcm"    # or "apns"
          }
        The device token is stored in `endpoint` (with the two required
        `p256dh` / `auth` columns filled with sentinel `"mobile"` so the
        NOT NULL constraint holds). The mobile-side sender lives in
        `utils/push.py::send_push` behind a `pywebpush` guard — it
        currently no-ops for fcm/apns until the Firebase project is
        wired (see PUSH_SETUP.md).
    """
    user = current_user()
    try:
        payload = require_json(request.get_json(silent=True))
        platform = as_str(payload.get("platform") or "web", "platform", max_len=20)
        if platform not in ("web", "fcm", "apns"):
            raise ValidationError("platform must be 'web', 'fcm', or 'apns'.")
        user_agent = payload.get("userAgent")
        if user_agent is not None:
            user_agent = as_str(user_agent, "userAgent", max_len=400)
        if platform == "web":
            endpoint = as_str(
                payload.get("endpoint") or "", "endpoint", max_len=1000)
            keys = payload.get("keys") or {}
            if not isinstance(keys, dict):
                raise ValidationError("keys must be an object.")
            p256dh = as_str(keys.get("p256dh") or "", "keys.p256dh", max_len=200)
            auth = as_str(keys.get("auth") or "", "keys.auth", max_len=80)
        else:
            # Mobile: `token` is the device identifier from FCM/APNs.
            # Store it under `endpoint` and stub the two crypto fields
            # with a fixed sentinel — the send-time branch looks at
            # `platform`, not at `p256dh`/`auth`, so the values are
            # never dereferenced. Kept non-empty to satisfy NOT NULL.
            token = as_str(payload.get("token") or "", "token", max_len=1000)
            endpoint = token
            p256dh = "mobile"
            auth = "mobile"
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400

    # Upsert on (user_id, endpoint) — the browser re-subscribes on many
    # events (SW update, permission re-grant), and we don't want a
    # duplicate row per re-subscribe. Refresh `last_seen_at` too so a
    # future "prune subs unseen for N months" job has a signal.
    # Phase 33 fix #10 — savepoint the insert branch so two parallel
    # subscribes (SW update fires them in pairs) can't both pass the
    # SELECT and both INSERT → 500 on the unique constraint. On
    # collision we fall through to the UPDATE path with the winning
    # row.
    from sqlalchemy.exc import IntegrityError
    sub = PushSubscription.query.filter_by(
        user_id=user.id, endpoint=endpoint,
    ).first()
    if sub is None:
        candidate = PushSubscription(
            user_id=user.id,
            endpoint=endpoint,
            p256dh=p256dh,
            auth=auth,
            user_agent=user_agent,
            platform=platform,
        )
        try:
            with db.session.begin_nested():
                db.session.add(candidate)
            sub = candidate
        except IntegrityError:
            db.session.rollback()
            sub = PushSubscription.query.filter_by(
                user_id=user.id, endpoint=endpoint,
            ).first()
            if sub is None:
                return jsonify({"error": "Could not register subscription."}), 500
            sub.p256dh = p256dh
            sub.auth = auth
            sub.user_agent = user_agent
            sub.last_seen_at = utc_now()
    else:
        sub.p256dh = p256dh
        sub.auth = auth
        sub.user_agent = user_agent
        sub.last_seen_at = utc_now()
    db.session.commit()
    return jsonify(sub.to_dict()), 201


@push_bp.route("/push/unsubscribe", methods=["POST"])
@login_required
def unsubscribe():
    user = current_user()
    try:
        payload = require_json(request.get_json(silent=True))
        endpoint = as_str(payload.get("endpoint") or "", "endpoint", max_len=1000)
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400
    sub = PushSubscription.query.filter_by(
        user_id=user.id, endpoint=endpoint,
    ).first()
    if sub is None:
        return jsonify({"ok": True, "removed": 0}), 200
    db.session.delete(sub)
    db.session.commit()
    return jsonify({"ok": True, "removed": 1}), 200
