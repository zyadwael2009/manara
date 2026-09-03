"""Auth endpoints and role-check decorators.

Auth model (matches ClubHub):
  * Login writes `session['user_id']`, `session['role']`, `session['tv']`
    (a copy of `User.token_version`) into Flask's signed session cookie.
  * The same signed payload is ALSO returned in the response body as
    `sessionToken`, using Flask's session interface serializer. Flutter web
    replays that token in the `X-Session-Token` header on every request
    because it can't rely on browser cookies across origins.
  * `@app.before_request` (in app.py) hydrates the session from the header
    when no cookie is present.
  * `/api/auth/me` re-issues the token every call → 90-day sliding session.
  * Revocation: bump `User.token_version` and every outstanding token whose
    embedded `tv` no longer matches is rejected on the next request.

Role gating:
  * `@login_required`
  * `@require_role('instructor', 'admin', ...)`
  * `@require_admin`
Every decorator returns a JSON error (401/403) rather than redirecting.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from functools import wraps
from typing import Any, Callable

from flask import Blueprint, current_app, g, jsonify, request, session

from models import USER_ROLES, User, db
from utils.validation import (
    ValidationError,
    as_str,
    one_of,
    require_fields,
    require_json,
)
from utils.time import utc_now

auth_bp = Blueprint("auth", __name__)

# Roles a user is allowed to pick during self-registration. `admin` is
# excluded — admins are seeded manually / promoted by another admin.
# Phase 6: parent accounts are created by the school office only. Self-
# registration is limited to students and instructors; a POST with role
# 'parent' or 'admin' is rejected below regardless of what the picker sent.
SELF_REGISTER_ROLES = ("student", "instructor")


# -----------------------------------------------------------------------------
# Session token helpers
# -----------------------------------------------------------------------------
def _sign_session_token() -> str:
    """Serialize the current session dict into a signed token string.

    The Flutter web client stores this and sends it back as `X-Session-Token`
    on subsequent requests.
    """
    serializer = current_app.session_interface.get_signing_serializer(current_app)
    if serializer is None:  # pragma: no cover — Flask always provides one for the default interface
        raise RuntimeError("Session signing serializer unavailable.")
    return serializer.dumps(dict(session))


def load_session_from_header() -> None:
    """`before_request` hook: rehydrate `session` from `X-Session-Token`.

    Runs on every request. Called from app.py. When the header is present it
    OVERRIDES any cookie session — the header is an explicit auth intent
    from the (typically web) client, and letting a stale cookie win could
    resolve the request to the wrong user. If the header is absent or
    invalid, we leave whatever cookie session exists intact.
    """
    token = request.headers.get("X-Session-Token")
    if not token:
        return  # No explicit header — fall through to cookie session (if any).

    serializer = current_app.session_interface.get_signing_serializer(current_app)
    if serializer is None:  # pragma: no cover
        return
    max_age = int(current_app.config["PERMANENT_SESSION_LIFETIME"].total_seconds())
    try:
        payload = serializer.loads(token, max_age=max_age)
    except Exception:
        # Phase 11 audit fix L4: invalid/expired header — DON'T touch the
        # cookie session. Previous behaviour nuked the cookie on any bad
        # header (stale localStorage token, browser extension replay, SPA
        # refresh race) and silently logged the user out. Refusing to
        # adopt the bad token still leaves the cookie session — if it too
        # is invalid, the downstream @login_required just 401s.
        return

    if not isinstance(payload, dict):
        return

    # Explicit header wins — drop the cookie session and rebuild from the token.
    session.clear()
    for k, v in payload.items():
        session[k] = v
    session.permanent = True


# -----------------------------------------------------------------------------
# Current-user resolution + decorators
# -----------------------------------------------------------------------------
def current_user() -> User | None:
    """Return the logged-in User or None. Caches on `flask.g` per request.

    The session's `tv` (token_version) must still match the DB row — otherwise
    the token has been revoked (logout / password change) and we treat the
    request as anonymous.
    """
    cached = getattr(g, "_current_user", None)
    if cached is not None:
        return cached

    user_id = session.get("user_id")
    if not user_id:
        g._current_user = None
        return None

    user = db.session.get(User, user_id)
    if user is None or not user.is_active:
        g._current_user = None
        return None

    if session.get("tv") != user.token_version:
        g._current_user = None
        return None

    g._current_user = user
    return user


def login_required(view: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(view)
    def wrapper(*args, **kwargs):
        user = current_user()
        if user is None:
            return jsonify({"error": "Authentication required."}), 401
        return view(*args, **kwargs)

    return wrapper


def require_role(*allowed_roles: str) -> Callable[..., Callable[..., Any]]:
    """Decorator factory: allow only the listed roles."""
    def decorator(view: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(view)
        def wrapper(*args, **kwargs):
            user = current_user()
            if user is None:
                return jsonify({"error": "Authentication required."}), 401
            if user.role not in allowed_roles:
                return jsonify({"error": "You do not have permission to perform this action."}), 403
            return view(*args, **kwargs)

        return wrapper

    return decorator


def require_admin(view: Callable[..., Any]) -> Callable[..., Any]:
    return require_role("admin")(view)


# -----------------------------------------------------------------------------
# Login state helpers
# -----------------------------------------------------------------------------
def _write_login_session(user: User) -> None:
    session.clear()
    session["user_id"] = user.id
    session["role"] = user.role
    session["tv"] = user.token_version
    session.permanent = True


def _is_locked_out(user: User) -> bool:
    return bool(user.locked_until and user.locked_until > utc_now())


def _register_failed_login(user: User) -> None:
    user.failed_login_count = (user.failed_login_count or 0) + 1
    if user.failed_login_count >= current_app.config["LOGIN_MAX_ATTEMPTS"]:
        user.locked_until = utc_now() + timedelta(
            minutes=current_app.config["LOGIN_LOCKOUT_MINUTES"]
        )
    db.session.commit()


def _reset_failed_login(user: User) -> None:
    if user.failed_login_count or user.locked_until:
        user.failed_login_count = 0
        user.locked_until = None
        db.session.commit()


# -----------------------------------------------------------------------------
# Routes
# -----------------------------------------------------------------------------
@auth_bp.route("/register", methods=["POST"])
@auth_bp.route("/register/", methods=["POST"])
def register():
    """Create a new user. Roles: student / instructor / parent."""
    try:
        payload = require_json(request.get_json(silent=True))
        require_fields(payload, ("name", "email", "password", "role"))
        name = as_str(payload["name"], "name", max_len=120)
        email = as_str(payload["email"], "email", max_len=190).lower()
        password = as_str(payload["password"], "password", max_len=255)
        role = one_of(payload["role"], SELF_REGISTER_ROLES, "role")
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400

    if "@" not in email or "." not in email.split("@")[-1]:
        return jsonify({"error": "Invalid email address."}), 400
    if len(password) < 8:
        return jsonify({"error": "Password must be at least 8 characters."}), 400

    if User.query.filter_by(email=email).first() is not None:
        return jsonify({"error": "An account with this email already exists."}), 409

    user = User(name=name, email=email, role=role)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()

    _write_login_session(user)
    return (
        jsonify({"user": user.to_dict(), "sessionToken": _sign_session_token()}),
        201,
    )


@auth_bp.route("/login", methods=["POST"])
@auth_bp.route("/login/", methods=["POST"])
def login():
    # Phase 25 hard-audit fix H-10: per-user lockout at 5 attempts
    # exists (below) but doesn't stop an attacker who rotates through
    # thousands of usernames — that's a full password-grinding attack
    # with no counter tripping. Add a per-IP burst limit as the first
    # gate so any single origin gets throttled fast.
    #
    # Skip in TESTING so the existing suite (which hammers /login as
    # setup for hundreds of fixtures) doesn't self-lock. Production
    # runs with TESTING=False and gets the limit.
    from flask import current_app
    if not current_app.config.get("TESTING"):
        from utils.rate_limit import check_rate
        ok, retry_after = check_rate(
            "login", request.remote_addr or "-",
            limit=20, window=60,
        )
        if not ok:
            resp = jsonify({"error": "Too many login attempts. Try again shortly."})
            resp.status_code = 429
            resp.headers["Retry-After"] = str(retry_after)
            return resp

    try:
        payload = require_json(request.get_json(silent=True))
        require_fields(payload, ("email", "password"))
        email = as_str(payload["email"], "email").lower()
        password = as_str(payload["password"], "password")
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400

    user = User.query.filter_by(email=email).first()

    # Phase 10 audit fix M2: run a password check on EVERY code path so
    # attackers can't distinguish unknown-account vs locked-account vs
    # wrong-password by response latency or status code:
    #   - Unknown/inactive account → dummy hash + 401.
    #   - Locked account → real hash + 401 UNLESS the password was actually
    #     valid, in which case surface the 423 (the lock signal never
    #     reaches an unauth prober).
    #   - Wrong password → 401 with the same shape as unknown-account.
    # `_register_failed_login` also normalises so its extra commit doesn't
    # leak "this is a real user" timing.
    from werkzeug.security import check_password_hash as _cph
    _DUMMY_HASH = (
        "pbkdf2:sha256:600000$dummy$0000000000000000000000000000000000"
        "000000000000000000000000000000"
    )
    _INVALID_MSG = "Invalid email or password."

    if user is None or not user.is_active:
        _cph(_DUMMY_HASH, password)
        return jsonify({"error": _INVALID_MSG}), 401

    password_ok = user.check_password(password)

    if not password_ok:
        _register_failed_login(user)
        return jsonify({"error": _INVALID_MSG}), 401

    # Password was correct. Only NOW check the lock — so probers with wrong
    # passwords never learn the account is locked.
    if _is_locked_out(user):
        return (
            jsonify({"error": "This account is temporarily locked. Try again later."}),
            423,
        )

    _reset_failed_login(user)
    _write_login_session(user)
    return jsonify({"user": user.to_dict(), "sessionToken": _sign_session_token()}), 200


@auth_bp.route("/me", methods=["GET"])
@auth_bp.route("/me/", methods=["GET"])
@login_required
def me():
    """Current user + a freshly-signed session token (sliding session)."""
    user = current_user()
    # Refresh token_version snapshot in session in case it changed elsewhere
    # (shouldn't happen in Phase 1, but keeps the sliding token honest).
    session["tv"] = user.token_version
    session.permanent = True
    return jsonify({"user": user.to_dict(), "sessionToken": _sign_session_token()}), 200


@auth_bp.route("/logout", methods=["POST"])
@auth_bp.route("/logout/", methods=["POST"])
@login_required
def logout():
    """Invalidate every outstanding token for this user."""
    user = current_user()
    user.token_version = (user.token_version or 0) + 1
    db.session.commit()
    session.clear()
    return jsonify({"message": "Logged out."}), 200
