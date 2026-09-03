"""Phase 21 — student/parent/teacher notification inbox."""
from __future__ import annotations

from datetime import datetime

from flask import Blueprint, jsonify, request

from models import (
    NOTIFICATION_KINDS,
    Notification,
    NotificationPreference,
    db,
)
from routes.auth import current_user, login_required
from utils.validation import require_json
from utils.time import utc_now

notifications_bp = Blueprint("notifications", __name__)


@notifications_bp.route("/notifications/mine", methods=["GET"])
@notifications_bp.route("/notifications/mine/", methods=["GET"])
@login_required
def my_notifications():
    """Most recent notifications for the caller. Newest first.

    Phase 29 · T3 — pagination:
      * `?page=N&pageSize=M` (max 50 per page).
      * Response adds `page/pageSize/hasMore` so the client can wire
        infinite scroll.
      * Legacy `?limit=N` (max 200) still honoured for callers that
        haven't migrated — those get the old single-batch shape with
        `page/pageSize/hasMore` filled in as if the whole batch were
        one page.
      * The pre-existing `notifications` key is kept alongside the new
        `items` key for one release so clients can migrate at their own
        pace.
    """
    user = current_user()
    unread_only = request.args.get("unreadOnly", "").lower() == "true"

    q = Notification.query.filter_by(user_id=user.id)
    if unread_only:
        q = q.filter(Notification.read_at.is_(None))
    q = q.order_by(Notification.created_at.desc())

    from utils.pagination import paginate
    # `?limit=N` legacy path — clamp and bypass the page cap.
    if request.args.get("limit"):
        try:
            legacy_limit = max(1, min(200, int(request.args["limit"])))
        except (TypeError, ValueError):
            legacy_limit = 50
        page = paginate(
            q, render_item=lambda n: n.to_dict(),
            page=1, page_size=legacy_limit, max_page_size=200,
        )
    else:
        page = paginate(q, render_item=lambda n: n.to_dict())

    unread_count = (
        Notification.query.filter_by(user_id=user.id)
        .filter(Notification.read_at.is_(None)).count()
    )
    return jsonify({
        # Legacy alias — remove in the next release once every client is on `items`.
        "notifications": page["items"],
        "items": page["items"],
        "page": page["page"],
        "pageSize": page["pageSize"],
        "hasMore": page["hasMore"],
        "unreadCount": unread_count,
    }), 200


@notifications_bp.route("/notifications/mark-read", methods=["POST"])
@login_required
def mark_notifications_read():
    """Body: `{ids: [...]}` marks those ids read; `{all: true}` marks the
    caller's whole inbox read. Silent success if the ids don't exist or
    belong to a different user — the caller sees only their own set of
    ids anyway, and duplicates are safe.
    """
    user = current_user()
    # Phase 25 hard-audit fix: guard against bare `require_json` throwing
    # ValidationError → 500 on missing/non-JSON bodies. Return 400 instead.
    from utils.validation import ValidationError
    try:
        payload = require_json(request.get_json(silent=True))
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400
    now = utc_now()
    if payload.get("all") is True:
        Notification.query.filter_by(user_id=user.id).filter(
            Notification.read_at.is_(None)
        ).update({Notification.read_at: now})
    else:
        ids = payload.get("ids") or []
        if not isinstance(ids, list):
            return jsonify({"error": "ids must be a list."}), 400
        if ids:
            Notification.query.filter(
                Notification.user_id == user.id,
                Notification.id.in_(ids),
                Notification.read_at.is_(None),
            ).update({Notification.read_at: now}, synchronize_session=False)
    db.session.commit()
    unread_count = (
        Notification.query.filter_by(user_id=user.id)
        .filter(Notification.read_at.is_(None)).count()
    )
    return jsonify({"unreadCount": unread_count}), 200


# ---------------------------------------------------------------------------
# Phase 32 · T1 — Notification preferences
#
# GET returns every known kind + the caller's enabled/disabled state
# for that kind (missing row = enabled). PUT accepts a partial map
# `{kind: bool, ...}` and upserts the corresponding rows.
# ---------------------------------------------------------------------------
@notifications_bp.route("/notifications/preferences", methods=["GET"])
@login_required
def get_preferences():
    user = current_user()
    rows = NotificationPreference.query.filter_by(user_id=user.id).all()
    by_kind = {r.kind: bool(r.enabled) for r in rows}
    return jsonify({
        "kinds": list(NOTIFICATION_KINDS),
        "preferences": {
            k: by_kind.get(k, True) for k in NOTIFICATION_KINDS
        },
    }), 200


@notifications_bp.route("/notifications/preferences", methods=["PUT"])
@login_required
def put_preferences():
    user = current_user()
    from utils.validation import ValidationError
    try:
        payload = require_json(request.get_json(silent=True))
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400
    prefs = payload.get("preferences") or payload
    if not isinstance(prefs, dict):
        return jsonify({"error": "preferences must be a map."}), 400
    for kind, enabled in prefs.items():
        # Fail-open on unknown kinds (matches enqueue's behavior) but
        # don't persist bogus keys — a client typo shouldn't create
        # ghost rows the UI never surfaces.
        if kind not in NOTIFICATION_KINDS:
            continue
        row = NotificationPreference.query.filter_by(
            user_id=user.id, kind=kind,
        ).first()
        if row is None:
            row = NotificationPreference(
                user_id=user.id, kind=kind, enabled=bool(enabled),
            )
            db.session.add(row)
        else:
            row.enabled = bool(enabled)
    db.session.commit()
    return get_preferences()
