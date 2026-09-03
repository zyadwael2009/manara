"""Phase 29 — shared list-endpoint pagination helper.

The default before this file: unbounded lists (`limit(200)`, `limit(50)`,
or no limit at all). That reads fine for a demo school but the query
patterns keep coming up in the audit rounds — an admin with 3,000
students hitting a "list all threads" endpoint pulls a lot of rows the
UI never renders.

Contract:
    result = paginate(query, page, page_size, max_page_size=50)
    # -> {
    #      "items": [...] as returned by `render_item`,
    #      "page": 1,          # 1-indexed
    #      "pageSize": 20,
    #      "hasMore": True,    # is there at least one more row?
    #      "total": Optional[int],   # provided when compute_total=True
    #    }

Notes:
  * `page` clamps to 1. `page_size` clamps to `[1, max_page_size]`.
  * `hasMore` is cheap — we fetch `page_size + 1` rows and check the
    length. That avoids a second COUNT round trip on every list read.
  * `compute_total=True` still calls `query.count()` when the client
    needs pagination controls (e.g. "Page 4 of 12"). Skipped by default.
  * `render_item` lets the caller pick which `to_dict()` variant to
    call without pulling the shape into this helper.
"""
from __future__ import annotations

from typing import Any, Callable, TypeVar

from flask import request

T = TypeVar("T")


def paginate(
    query,
    *,
    render_item: Callable[[T], dict] | None = None,
    page: int | None = None,
    page_size: int | None = None,
    max_page_size: int = 50,
    compute_total: bool = False,
) -> dict[str, Any]:
    """See module docstring."""
    if page is None:
        page = _get_int_arg("page", default=1)
    if page_size is None:
        page_size = _get_int_arg("pageSize", default=20)
    page = max(1, page)
    page_size = max(1, min(max_page_size, page_size))

    offset = (page - 1) * page_size
    # Fetch one extra to detect `hasMore` without a second COUNT.
    rows = query.limit(page_size + 1).offset(offset).all()
    has_more = len(rows) > page_size
    if has_more:
        rows = rows[:page_size]

    result: dict[str, Any] = {
        "items": [render_item(r) if render_item else r for r in rows],
        "page": page,
        "pageSize": page_size,
        "hasMore": has_more,
    }
    if compute_total:
        result["total"] = query.count()
    return result


def _get_int_arg(name: str, *, default: int) -> int:
    raw = request.args.get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default
