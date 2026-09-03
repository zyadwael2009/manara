"""Small in-memory sliding-window rate limiter.

No new dependency — deliberately tiny. Used to gate the public certificate
verify endpoint so the 64-bit search space isn't grindable at internet
speed. Not a general-purpose limiter; if the app ever grows more than one
process worker, swap this for Flask-Limiter with a Redis backend.

Usage:
    from utils.rate_limit import check_rate

    ok, retry_after = check_rate("verify", request.remote_addr, limit=30, window=60)
    if not ok:
        resp = jsonify({"error": "Too many requests."})
        resp.status_code = 429
        resp.headers["Retry-After"] = str(retry_after)
        return resp
"""
from __future__ import annotations

import threading
import time
from collections import deque
from typing import Deque

_LOCK = threading.Lock()
# {(bucket, key) -> deque[timestamps]}. Deques are trimmed on every check.
_STATE: dict[tuple[str, str], Deque[float]] = {}


def check_rate(
    bucket: str,
    key: str,
    *,
    limit: int,
    window: float,
) -> tuple[bool, int]:
    """Return (allowed, retry_after_seconds).

    `bucket` scopes the counter (so different endpoints have independent
    quotas even for the same client IP). `key` is usually `request.remote_addr`.
    `limit` requests per `window` seconds. Returns retry_after=0 when allowed.
    """
    now = time.monotonic()
    cutoff = now - window
    ident = (bucket, key or "-")
    with _LOCK:
        dq = _STATE.setdefault(ident, deque())
        # Drop timestamps outside the window.
        while dq and dq[0] < cutoff:
            dq.popleft()
        if len(dq) >= limit:
            oldest = dq[0]
            retry_after = max(1, int(oldest + window - now) + 1)
            return False, retry_after
        dq.append(now)
        return True, 0


def _reset_all() -> None:
    """Test-only helper — clears every bucket. Real code should never call."""
    with _LOCK:
        _STATE.clear()
