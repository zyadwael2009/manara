"""Shared foundations for the model package.

`db`, the id and timestamp helpers, the serialization helper, and the
enum-ish tuples more than one model refers to. Every module in this
package imports from here; nothing here imports from them.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash


def password_hash_kwargs() -> dict:
    """Keyword arguments for `generate_password_hash`.

    Werkzeug's default (scrypt) everywhere, which is what you want: it costs
    roughly 80 ms per call by design. The test suite hashes or verifies a
    dozen passwords per test, and that was the single largest component of
    its runtime, so `PASSWORD_HASH_METHOD` may swap in a cheap KDF.

    It is honoured ONLY when `TESTING` is set, so no production configuration
    — env var, .env file or typo — can weaken real password storage.
    """
    try:
        from flask import current_app

        if current_app.config.get("TESTING"):
            method = current_app.config.get("PASSWORD_HASH_METHOD")
            if method:
                return {"method": method}
    except RuntimeError:
        pass  # no application context — fall through to the strong default
    return {}

from utils.uuid_gen import generate_uuid
from utils.time import utc_now

db = SQLAlchemy()


# --- Enum-ish string sets (kept as plain constants; the DB stores strings) ---
USER_ROLES = ("student", "instructor", "admin", "parent")
PARENT_RELATIONSHIPS = ("father", "mother", "guardian")
COURSE_STATUSES = ("draft", "published")
LESSON_TYPES = ("video", "text", "pdf")

# Phase 2 additions ---------------------------------------------------------
ENROLLMENT_STATUSES = ("active", "dropped", "completed")
ENROLLED_VIA = ("auto_mandatory", "elective_choice", "manual")

# Common elective groups; free-form string so admins can add more without
# migrations. See curriculum-model memory.
COMMON_ELECTIVE_GROUPS = (
    "language",
    "science_track",
    "math_track",
    "humanities",
    "arts",
)

# Departments — match the categories field on courses. Free-form for the
# same reason.
COMMON_DEPARTMENTS = (
    "math",
    "science",
    "english",
    "social_studies",
    "languages",
    "arts",
    "pe",
    "computer_science",
    "general",
)


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None
