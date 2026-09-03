"""Phase 31 · T4 — one place that returns "now" as a naive UTC datetime.

Python 3.12 deprecated `datetime.utcnow()`; the recommended
replacement is `datetime.now(datetime.UTC)`, but that returns a
tz-aware object. Every `DateTime` column in `models.py` is declared
without `timezone=True`, i.e. naive UTC — mixing the two shapes
raises "can't subtract offset-naive and offset-aware datetimes" at
random join points.

`utc_now()` is the drop-in: naive UTC "now", identical in behavior
to the deprecated `datetime.utcnow()` but without the warning.
"""
from __future__ import annotations

from datetime import datetime, timezone


def utc_now() -> datetime:
    """Return the current time as a NAIVE UTC datetime.

    Equivalent to the deprecated `datetime.utcnow()` but built on the
    non-deprecated `datetime.now(timezone.utc)` API.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)
