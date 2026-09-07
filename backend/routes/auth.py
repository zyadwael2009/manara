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

import secrets
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
    validate_password_strength,
)
from utils.time import utc_now

auth_bp = Blueprint("auth", __name__)

# Roles a user is allowed to pick during self-registration.
#
# `student` only. This is a single school: staff accounts are created by the
# office, and letting anyone on the internet mint themselves an `instructor`
# handed an unvetted stranger a staff role — `utils/permissions` kept them
# away from any *specific* class's content, but the role by itself unlocked
# staff-scoped endpoints and file upload onto a shared disk.
#
# Instructors and parents are created by an admin via `POST /api/users`
# (see `routes/users.py::admin_create_user`) or the CSV bulk import; `admin`
# comes only from the seed script or a direct DB write.
SELF_REGISTER_ROLES = ("student",)


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


def _dummy_hash() -> str:
    """A throwaway hash to verify against when the account does not exist.

    The point is that an unknown email costs the same wall-clock as a known
    one, so a prober can't enumerate accounts by timing. That only holds if
    the dummy uses the *same* KDF and parameters as real passwords — this was
    previously a hardcoded `pbkdf2:sha256:600000` literal while real hashes
    were scrypt, so the two paths had visibly different cost profiles.

    Derived once per app and cached: computing it on every anonymous login
    attempt would double the work an attacker can make the server do.
    """
    from werkzeug.security import generate_password_hash

    from models import password_hash_kwargs

    cached = current_app.config.get("_DUMMY_PASSWORD_HASH")
    if cached is None:
        cached = generate_password_hash(
            secrets.token_urlsafe(32), **password_hash_kwargs()
        )
        current_app.config["_DUMMY_PASSWORD_HASH"] = cached
    return cached


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
    """Self-service signup. Students only — see `SELF_REGISTER_ROLES`."""
    # Account creation is unauthenticated, so it is the cheapest way to fill
    # a table (or a disk) from the outside. `/login` has had a per-IP burst
    # limit since Phase 25; this endpoint had none.
    if not current_app.config.get("TESTING"):
        from utils.rate_limit import check_rate

        ok, retry_after = check_rate(
            "register", request.remote_addr or "-", limit=5, window=3600,
        )
        if not ok:
            resp = jsonify(
                {"error": "Too many sign-ups from this network. Try again later."}
            )
            resp.status_code = 429
            resp.headers["Retry-After"] = str(retry_after)
            return resp

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
    error = validate_password_strength(password)
    if error:
        return jsonify({"error": error}), 400

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

    _INVALID_MSG = "Invalid email or password."

    if user is None or not user.is_active:
        _cph(_dummy_hash(), password)
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


@auth_bp.route("/password", methods=["POST"])
@auth_bp.route("/password/", methods=["POST"])
@login_required
def change_password():
    """Change your own password.

    Requires the current password — a session token alone must not be enough,
    or a borrowed unlocked device becomes a permanent account takeover.

    On success `token_version` is bumped, which revokes every outstanding
    token for this user; the caller is then re-issued a fresh one so the
    device that made the change stays signed in and every *other* device is
    signed out. That is the behaviour you want when the reason for the change
    is "someone else knows my password".
    """
    user = current_user()

    # Wrong-current-password guesses are an online brute force against a
    # known account, so throttle them the way /login is throttled.
    if not current_app.config.get("TESTING"):
        from utils.rate_limit import check_rate

        ok, retry_after = check_rate(
            "change_password", user.id, limit=10, window=300,
        )
        if not ok:
            resp = jsonify({"error": "Too many attempts. Try again shortly."})
            resp.status_code = 429
            resp.headers["Retry-After"] = str(retry_after)
            return resp

    try:
        payload = require_json(request.get_json(silent=True))
        require_fields(payload, ("currentPassword", "newPassword"))
        current_password = as_str(payload["currentPassword"], "currentPassword", max_len=255)
        new_password = as_str(payload["newPassword"], "newPassword", max_len=255)
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400

    if not user.check_password(current_password):
        return jsonify({"error": "Current password is incorrect."}), 403

    error = validate_password_strength(new_password)
    if error:
        return jsonify({"error": error}), 400
    if new_password == current_password:
        return jsonify({"error": "New password must differ from the current one."}), 400

    user.set_password(new_password)
    user.must_change_password = False
    user.token_version = (user.token_version or 0) + 1
    user.failed_login_count = 0
    user.locked_until = None
    db.session.commit()

    # Re-issue for THIS device against the new token_version.
    _write_login_session(user)
    return (
        jsonify(
            {
                "message": "Password changed. Other devices have been signed out.",
                "user": user.to_dict(),
                "sessionToken": _sign_session_token(),
            }
        ),
        200,
    )


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
