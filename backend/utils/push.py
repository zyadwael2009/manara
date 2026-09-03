"""Phase 28 — Web Push (VAPID) helpers.

Everything here is best-effort. The push transport is a nicety on top
of the existing bell notifications; a failed push (stale endpoint,
missing pywebpush install, missing/invalid VAPID keys) never blocks the
call site. Callers are inside `utils.notifications.enqueue`, which is
itself inside grade / attendance / assignment write pipelines — trust-
core must never fail because a browser subscription went stale.

VAPID key storage:
  * On first boot, generate an ECDSA P-256 key pair and write it to
    `instance/vapid.json` as {"private_key": "…", "public_key": "…"}.
  * Public key is served to the browser via `/api/push/public-key`.
  * Private key is used by pywebpush to sign every send.

The public key is returned in the Web Push URL-safe base64 uncompressed
format the browser's `PushManager.subscribe({ applicationServerKey })`
expects — a 65-byte 0x04-prefixed EC point.
"""
from __future__ import annotations

import base64
import json
import logging
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

# The pywebpush import is deferred; the whole feature no-ops when it
# (or its `cryptography`/`ecdsa`/`http-ece` deps) can't be imported.
_pywebpush = None
_pywebpush_error: Optional[str] = None
try:
    from pywebpush import WebPushException as _WebPushException
    from pywebpush import webpush as _webpush
    _pywebpush = _webpush
    WebPushException = _WebPushException
except Exception as e:  # pragma: no cover - depends on runtime deps
    _pywebpush_error = f"pywebpush import failed: {e!r}"

    class WebPushException(Exception):
        """Placeholder so `except WebPushException` doesn't NameError."""
        response = None


def _instance_path() -> Path:
    from flask import current_app
    return Path(current_app.instance_path)


def _keys_file() -> Path:
    return _instance_path() / "vapid.json"


def _b64url_uncompressed_public_key(private_key_pem: str) -> str:
    """Serialise the public half of a private-key PEM to the base64-url
    uncompressed EC point format the browser needs."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    priv = serialization.load_pem_private_key(
        private_key_pem.encode(), password=None,
    )
    assert isinstance(priv, ec.EllipticCurvePrivateKey)
    numbers = priv.public_key().public_numbers()
    x = numbers.x.to_bytes(32, byteorder="big")
    y = numbers.y.to_bytes(32, byteorder="big")
    uncompressed = b"\x04" + x + y
    return base64.urlsafe_b64encode(uncompressed).rstrip(b"=").decode()


def load_or_create_keys() -> Optional[dict]:
    """Return {"private_key": PEM, "public_key": b64url} or None on failure.

    Never raises: any exception (missing cryptography lib, unwritable
    instance dir, corrupt JSON) is logged and None is returned so the
    endpoint can respond with `pushEnabled: false` and the client falls
    back to the bell only.
    """
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import ec
    except Exception as e:
        log.info("push: cryptography import failed, disabling push: %r", e)
        return None

    f = _keys_file()
    if f.exists():
        try:
            data = json.loads(f.read_text())
            if data.get("private_key") and data.get("public_key"):
                return data
        except Exception as e:
            log.warning("push: could not read %s (%r); regenerating", f, e)

    try:
        priv = ec.generate_private_key(ec.SECP256R1())
        pem = priv.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode()
        pub_b64 = _b64url_uncompressed_public_key(pem)
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps({
            "private_key": pem, "public_key": pub_b64,
        }))
        return {"private_key": pem, "public_key": pub_b64}
    except Exception as e:
        log.warning("push: could not generate VAPID keys: %r", e)
        return None


def push_available() -> bool:
    """True when pywebpush AND VAPID keys are both usable this request."""
    if _pywebpush is None:
        return False
    return load_or_create_keys() is not None


def send_push(
    subscription: dict,
    payload: dict,
    *,
    vapid_claims_email: str = "admin@manara.school",
) -> tuple[bool, Optional[int]]:
    """Best-effort push.

    Returns (delivered, status_code). `status_code` == 410 means the
    subscription is dead and the caller should prune it. All other
    failures are logged and swallowed.
    """
    if _pywebpush is None:
        return (False, None)
    keys = load_or_create_keys()
    if not keys:
        return (False, None)
    try:
        _pywebpush(
            subscription_info=subscription,
            data=json.dumps(payload),
            vapid_private_key=keys["private_key"],
            vapid_claims={"sub": f"mailto:{vapid_claims_email}"},
        )
        return (True, None)
    except WebPushException as e:  # pragma: no cover - network path
        code = getattr(e.response, "status_code", None) if e.response else None
        if code and code != 410:
            log.warning("push: send failed status=%s err=%r", code, e)
        return (False, code)
    except Exception as e:  # pragma: no cover
        log.warning("push: unexpected error: %r", e)
        return (False, None)


def fan_out_to_user(user_id: str, payload: dict) -> None:
    """Send `payload` to every registered subscription for a user,
    pruning any that come back 410 Gone. Silent on all errors.

    Phase 29 · T4 — branches on `platform`:
      * "web"        → pywebpush (fully wired this phase).
      * "fcm"/"apns" → mobile sender (currently no-op with a `# TODO`;
                        drop in your Firebase service-account JSON at
                        `instance/firebase.json` and swap the branch
                        for `pyfcm.FCMNotification.notify_single_device`
                        to activate).
    """
    if not user_id:
        return
    from models import PushSubscription, db
    subs = PushSubscription.query.filter_by(user_id=user_id).all()
    if not subs:
        return
    to_delete: list[PushSubscription] = []
    for s in subs:
        if s.platform == "web":
            if _pywebpush is None:
                continue
            sub_info = {
                "endpoint": s.endpoint,
                "keys": {"p256dh": s.p256dh, "auth": s.auth},
            }
            _delivered, code = send_push(sub_info, payload)
            if code == 410:
                to_delete.append(s)
        elif s.platform in ("fcm", "apns"):
            _delivered, code = send_mobile_push(s.platform, s.endpoint, payload)
            # Both 404 and 410 semantics apply on FCM/APNs for a stale
            # token; prune on either once the sender is wired.
            if code in (404, 410):
                to_delete.append(s)
        else:
            # Unknown platform — leave the row alone but don't try.
            continue
    for s in to_delete:
        db.session.delete(s)
    if to_delete:
        try:
            db.session.commit()
        except Exception:  # pragma: no cover
            db.session.rollback()


# Phase 30 · T6 — pyfcm import gated behind a `try` so the whole app
# boots either way. When you uncomment `pyfcm>=2.0.0` in
# requirements.txt and `pip install`, `send_mobile_push` activates
# automatically. Until then it stays a documented no-op — same
# defensive shape we use for pywebpush above.
_pyfcm = None
try:
    from pyfcm import FCMNotification as _FCMNotification
    _pyfcm = _FCMNotification
except Exception:  # pragma: no cover - dep gated on activation
    pass


def send_mobile_push(
    platform: str, device_token: str, payload: dict,
) -> tuple[bool, int | None]:
    """Mobile push sender (FCM / APNs).

    Contract:
      * Returns (delivered, status_code). `status_code in (404, 410)`
        means the device token is stale and the caller should prune it.
      * Failure is silent — enqueue() is called from grade / attendance
        / assignment write pipelines; a broken mobile transport must
        NEVER break trust-core.

    Activation path (see backend/PUSH_SETUP.md):
      1. Create a Firebase project + register the mobile bundles.
      2. Drop the service-account JSON at `instance/firebase.json`.
      3. Uncomment `pyfcm>=2.0.0` in requirements.txt and pip install.
      Steps done → this function starts delivering; nothing else changes.
    """
    if _pyfcm is None:
        return (False, None)
    firebase_json = _instance_path() / "firebase.json"
    if not firebase_json.exists():
        # Sender library imported but the Firebase config isn't there.
        # Log once (best-effort) so the operator notices, then no-op.
        log.info(
            "push: mobile send skipped; drop the service-account "
            "JSON at %s to activate", firebase_json,
        )
        return (False, None)
    try:
        push = _pyfcm(service_account_file=str(firebase_json))
        r = push.notify(
            fcm_token=device_token,
            notification_title=(payload.get("title") or "Manara"),
            notification_body=(payload.get("body") or ""),
            data_payload={
                # Every value is stringified for FCM's data-payload
                # contract (which only accepts str→str).
                "kind": str(payload.get("kind") or ""),
                "refType": str(payload.get("refType") or ""),
                "refId": str(payload.get("refId") or ""),
                "platform": platform,
            },
        )
        # pyfcm normalizes the response shape across FCM HTTP v1 quirks.
        delivered = bool(r.get("success"))
        code = r.get("failure_status_code")
        return (delivered, code)
    except Exception as e:  # pragma: no cover - network / dep path
        log.warning("push: mobile send failed: %r", e)
        return (False, None)
