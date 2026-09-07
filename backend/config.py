"""Runtime configuration for the LMS backend.

Env-driven with sensible dev defaults, matching the single-Config-class
convention used across the developer's other Flask projects. `.env` is
auto-loaded from `backend/.env` if present.
"""
from __future__ import annotations

import os
import re
import secrets
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

# --- Paths ------------------------------------------------------------------
BACKEND_DIR = Path(__file__).resolve().parent
INSTANCE_DIR = BACKEND_DIR / "instance"
INSTANCE_DIR.mkdir(parents=True, exist_ok=True)

# Load .env from backend/ without overriding real env vars.
load_dotenv(BACKEND_DIR / ".env", override=False)

def _is_production() -> bool:
    """Phase 10 audit fix M3: SESSION_COOKIE_SECURE + prod-only defaults must
    NOT hinge on the presence of DATABASE_URL — a deploy that uses sqlite
    (or injects the URL via a different env var) would ship cookies over
    plaintext. `MANARA_ENV=production` is now the explicit signal.
    """
    v = os.environ.get("MANARA_ENV", "").strip().lower()
    if v in ("prod", "production"):
        return True
    if v in ("dev", "development", "test"):
        return False
    # Back-compat heuristic for existing deploys that never set MANARA_ENV.
    return bool(os.environ.get("DATABASE_URL"))


_IS_PRODUCTION = _is_production()


def _resolve_secret_key() -> str:
    """SECRET_KEY resolution: env -> instance/.secret_key -> ephemeral.

    The cached file is created once with 64 bytes of `secrets.token_urlsafe`
    so dev sessions survive process restarts without needing a .env entry.
    """
    env_val = os.environ.get("SECRET_KEY")
    if env_val:
        return env_val

    cache_path = INSTANCE_DIR / ".secret_key"
    if cache_path.exists():
        val = cache_path.read_text(encoding="utf-8").strip()
        if val:
            return val

    generated = secrets.token_urlsafe(64)
    try:
        cache_path.write_text(generated, encoding="utf-8")
    except OSError:
        # Read-only filesystem — fall back to an ephemeral key.
        pass
    return generated


def _resolve_database_uri() -> str:
    """Build SQLALCHEMY_DATABASE_URI from DATABASE_URL or default to SQLite.

    Normalizations (matching ClubHub's convention):
      * `postgres://`  -> `postgresql://`
      * `mysql://`     -> `mysql+pymysql://`
      * MySQL URLs get `?charset=utf8mb4` forced on.
    """
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        return f"sqlite:///{(INSTANCE_DIR / 'lms.db').as_posix()}"

    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://") :]
    if url.startswith("mysql://"):
        url = "mysql+pymysql://" + url[len("mysql://") :]
    if url.startswith("mysql+pymysql://") and "charset=" not in url:
        url += ("&" if "?" in url else "?") + "charset=utf8mb4"
    return url


def _resolve_cors_origins() -> list[str]:
    raw = os.environ.get("CORS_ORIGINS", "").strip()
    if raw:
        return [o.strip() for o in raw.split(",") if o.strip() and o.strip() != "*"]

    # No whitelist configured. In production that is a misconfiguration, not a
    # default: falling through to the localhost dev regex below leaves the
    # deployed web app unable to call its own API, and the only symptom is an
    # opaque CORS error in the browser console — nothing in the server log.
    # Fail at boot instead, where the message is readable.
    if _IS_PRODUCTION:
        raise RuntimeError(
            "CORS_ORIGINS must be set when MANARA_ENV=production. "
            "Set it to the deployed web origin(s), comma-separated, e.g. "
            "CORS_ORIGINS=https://<gh-user>.github.io"
        )
    # Dev defaults: `flutter run -d chrome` uses a random port each time, so
    # a fixed whitelist doesn't work. Instead accept any http://localhost:<port>
    # or http://127.0.0.1:<port> via a regex. Flask-CORS accepts compiled
    # regex patterns alongside plain strings.
    #
    # This is DEV ONLY — production must set CORS_ORIGINS explicitly to the
    # real deployed origin(s).
    localhost_any_port = re.compile(r"^http://(localhost|127\.0\.0\.1)(:\d+)?$")
    return [localhost_any_port]


class Config:
    # --- Flask core ---
    SECRET_KEY = _resolve_secret_key()

    # --- SQLAlchemy ---
    SQLALCHEMY_DATABASE_URI = _resolve_database_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # Pool tuning only applies to real DB engines; SQLite ignores it and can
    # actually break with pool_size, so guard by scheme.
    if not SQLALCHEMY_DATABASE_URI.startswith("sqlite"):
        SQLALCHEMY_ENGINE_OPTIONS = {
            "pool_pre_ping": True,
            "pool_recycle": 280,
            "pool_size": 5,
            "max_overflow": 5,
            "isolation_level": "READ COMMITTED",
        }

    # --- Session cookie (also used to sign X-Session-Token) ---
    SESSION_COOKIE_NAME = "lms_session"
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = _IS_PRODUCTION
    PERMANENT_SESSION_LIFETIME = timedelta(days=90)  # sliding

    # --- App-level ---
    CORS_ORIGINS = _resolve_cors_origins()
    IS_PRODUCTION = _IS_PRODUCTION

    # Failed-login lockout thresholds (mirrors ClubHub).
    LOGIN_MAX_ATTEMPTS = 5
    LOGIN_LOCKOUT_MINUTES = 15
