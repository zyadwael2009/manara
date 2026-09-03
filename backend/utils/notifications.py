"""Phase 21 — the notification enqueue helper.

Called from inside the existing writer pipelines (grade cache recompute,
cert issuance, announcement fan-out, assignment grading, attendance
marking). Idempotency guard: same-day duplicate on
(user_id, kind, ref_type, ref_id) is suppressed so a re-run of a rollup
doesn't spam the bell.

Trust-core: this helper NEVER touches enrollments, grade entries, or
certificates. It only appends rows to the `notifications` table.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Optional
from utils.time import utc_now


def enqueue(
    user_id: str,
    kind: str,
    title: str,
    body: str = "",
    ref_type: Optional[str] = None,
    ref_id: Optional[str] = None,
) -> Optional[Any]:
    """Append one notification, or return the existing same-day duplicate.

    Silent no-op when `user_id` is falsy (defensive against callers that
    computed a target user of None, e.g. no linked parent for a mark).

    Model + `db` imported lazily so the test suite's per-fixture
    `sys.modules` reset (which produces a fresh `db` instance per app)
    doesn't leave this helper holding a stale reference — the classic
    "current Flask app is not registered with this SQLAlchemy instance"
    failure across cross-cutting write pipelines.
    """
    if not user_id:
        return None
    from models import Notification, NotificationPreference, db
    # Phase 32 · T1 — respect the user's per-kind opt-out. Missing row
    # means "enabled" (the default) so a freshly-registered user hears
    # everything. Fail-open on unknown kinds so a new notification
    # type doesn't need a per-user backfill before it can fire.
    pref = NotificationPreference.query.filter_by(
        user_id=user_id, kind=kind,
    ).first()
    if pref is not None and pref.enabled is False:
        return None
    since = utc_now() - timedelta(days=1)
    existing = (
        Notification.query
        .filter_by(user_id=user_id, kind=kind, ref_type=ref_type, ref_id=ref_id)
        .filter(Notification.created_at >= since)
        .first()
    )
    if existing is not None:
        return existing
    row = Notification(
        user_id=user_id,
        kind=kind,
        title=title.strip()[:200],
        body=(body or "").strip(),
        ref_type=ref_type,
        ref_id=ref_id,
    )
    db.session.add(row)
    # Phase 28 — best-effort Web Push fan-out. Wrapped so a broken
    # push transport (missing pywebpush, dead endpoint, network hiccup)
    # NEVER breaks the caller's grade / attendance / assignment write.
    try:
        from utils.push import fan_out_to_user
        fan_out_to_user(user_id, {
            "kind": kind,
            "title": row.title,
            "body": row.body,
            "refType": ref_type,
            "refId": ref_id,
        })
    except Exception:  # pragma: no cover - purely defensive
        pass
    return row
