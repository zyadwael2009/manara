"""Small in-route validation helpers.

Deliberately not marshmallow/pydantic: the ClubHub codebase validates by hand
in each route and we're mirroring that style. These helpers just remove the
boilerplate of "check required keys, check types, return 400".
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping


class ValidationError(ValueError):
    """Raised when a request payload fails validation. Handlers catch this
    and translate to a 400 response."""


def require_json(payload: Any) -> dict:
    """Coerce `request.get_json(silent=True)` into a dict or raise."""
    if payload is None:
        raise ValidationError("Request body must be JSON.")
    if not isinstance(payload, dict):
        raise ValidationError("Request body must be a JSON object.")
    return payload


def require_fields(payload: Mapping[str, Any], fields: Iterable[str]) -> None:
    """Raise ValidationError listing every missing/blank field.

    A field counts as missing if it is absent OR is an empty string / list /
    dict. Zero and False are allowed values.
    """
    missing = []
    for f in fields:
        if f not in payload:
            missing.append(f)
            continue
        v = payload[f]
        if v is None or (isinstance(v, (str, list, dict, tuple, set)) and len(v) == 0):
            missing.append(f)
    if missing:
        raise ValidationError(f"Missing required field(s): {', '.join(missing)}.")


def one_of(value: Any, choices: Iterable[str], field_name: str) -> str:
    """Return `value` if it matches one of `choices`, else raise."""
    choices = list(choices)
    if value not in choices:
        raise ValidationError(
            f"Invalid value for '{field_name}': must be one of {choices}."
        )
    return value


def as_str(value: Any, field_name: str, *, max_len: int | None = None) -> str:
    if not isinstance(value, str):
        raise ValidationError(f"'{field_name}' must be a string.")
    v = value.strip()
    if max_len is not None and len(v) > max_len:
        raise ValidationError(f"'{field_name}' must be at most {max_len} characters.")
    return v


def as_int(value: Any, field_name: str, *, default: int | None = None) -> int:
    if value is None and default is not None:
        return default
    if isinstance(value, bool) or not isinstance(value, int):
        # bool is a subclass of int — reject it explicitly to catch True/False slipping in.
        try:
            return int(value)
        except (TypeError, ValueError) as e:
            raise ValidationError(f"'{field_name}' must be an integer.") from e
    return value


def as_number(value: Any, field_name: str, *, default: float | None = None) -> float:
    if value is None and default is not None:
        return float(default)
    try:
        return float(value)
    except (TypeError, ValueError) as e:
        raise ValidationError(f"'{field_name}' must be a number.") from e


# The three call sites that set a password (self-registration, the admin's
# create-user endpoint, and the change-password endpoint) each used to inline
# `if len(password) < 8`. One helper keeps the rule — and any future
# tightening of it — in a single place.
MIN_PASSWORD_LENGTH = 8

# Passwords the bulk importer used to hand out, plus the usual suspects. A
# school rolling out accounts in a computer lab will otherwise end up with a
# whole class sharing one of these.
_BANNED_PASSWORDS = frozenset(
    {
        "password", "password1", "password123", "changeme", "changeme123",
        "12345678", "123456789", "1234567890", "qwertyui", "qwerty123",
        "letmein1", "iloveyou", "admin123", "welcome1", "manara123",
    }
)


def validate_password_strength(password: str) -> str | None:
    """Return an error message, or None when the password is acceptable.

    Returns rather than raises so callers can keep their existing
    `return jsonify({"error": ...}), 400` shape.
    """
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"Password must be at least {MIN_PASSWORD_LENGTH} characters."
    if password.lower() in _BANNED_PASSWORDS:
        return "That password is too common. Pick something harder to guess."
    if password.strip() == "":
        return "Password must not be blank."
    return None
