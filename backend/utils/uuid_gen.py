"""UUID helper used as the default for every model's primary key.

Kept in its own module so `models.py` can `from utils.uuid_gen import
generate_uuid` and every table declares `default=generate_uuid` the same way
(matches the ClubHub convention of UUID4 string PKs, not autoincrement ints).
"""
from __future__ import annotations

import uuid


def generate_uuid() -> str:
    """Return a new UUID4 as a plain string (36 chars, hyphenated)."""
    return str(uuid.uuid4())
