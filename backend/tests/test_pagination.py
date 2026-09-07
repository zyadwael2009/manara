"""Pagination on notifications, message threads, and announcements.

* Notifications: 60 notifications for one user; page=1 returns 20 items
  with hasMore=True; last page returns hasMore=False. Legacy `limit=`
  still respected. Legacy `notifications` key still present.
* Messages threads: bare-array shape kept when no page arg; paged
  envelope when page/pageSize supplied.
* Announcements: same back-compat shape rule.

Originally Phase 29.
"""
from __future__ import annotations


def _h(tok):
    return {"X-Session-Token": tok}


def _login(client, email, password):
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.data
    return r.get_json()["sessionToken"]


def _login_admin(client):
    return _login(client, "admin@t.local", "adminpass1")


# ============================================================================
# Notifications pagination
# ============================================================================
def test_notifications_page_shape(client):
    admin_tok = _login_admin(client)
    # Seed 60 notifications on the admin.
    from models import Notification, User, db
    with client.application.app_context():
        admin = User.query.filter_by(email="admin@t.local").first()
        for i in range(60):
            db.session.add(Notification(
                user_id=admin.id,
                kind="test",
                title=f"n{i}",
                body="",
            ))
        db.session.commit()
    r = client.get("/api/notifications/mine?page=1&pageSize=20",
                   headers=_h(admin_tok))
    assert r.status_code == 200
    body = r.get_json()
    assert body["page"] == 1
    assert body["pageSize"] == 20
    assert body["hasMore"] is True
    assert len(body["items"]) == 20
    # Back-compat: legacy `notifications` key still populated.
    assert body["notifications"] == body["items"]

    r = client.get("/api/notifications/mine?page=3&pageSize=20",
                   headers=_h(admin_tok))
    body = r.get_json()
    assert body["hasMore"] is False
    assert len(body["items"]) == 20


def test_notifications_legacy_limit_still_works(client):
    admin_tok = _login_admin(client)
    from models import Notification, User, db
    with client.application.app_context():
        admin = User.query.filter_by(email="admin@t.local").first()
        for i in range(10):
            db.session.add(Notification(
                user_id=admin.id, kind="test", title=f"n{i}", body=""))
        db.session.commit()
    r = client.get("/api/notifications/mine?limit=5", headers=_h(admin_tok))
    assert r.status_code == 200
    body = r.get_json()
    assert len(body["items"]) == 5


def test_notifications_page_size_clamped_to_max(client):
    admin_tok = _login_admin(client)
    r = client.get("/api/notifications/mine?page=1&pageSize=9999",
                   headers=_h(admin_tok))
    assert r.status_code == 200
    body = r.get_json()
    assert body["pageSize"] == 50  # max_page_size default


# ============================================================================
# Threads pagination — back-compat + envelope
# ============================================================================
def test_threads_bare_array_when_no_page_arg(client):
    admin_tok = _login_admin(client)
    r = client.get("/api/messages/threads/mine", headers=_h(admin_tok))
    assert r.status_code == 200
    body = r.get_json()
    # Bare list shape preserved for pre-Phase-29 clients.
    assert isinstance(body, list)


def test_threads_envelope_when_page_supplied(client):
    admin_tok = _login_admin(client)
    r = client.get("/api/messages/threads/mine?page=1&pageSize=10",
                   headers=_h(admin_tok))
    assert r.status_code == 200
    body = r.get_json()
    assert isinstance(body, dict)
    assert set(body.keys()) >= {"items", "page", "pageSize", "hasMore"}


# ============================================================================
# Announcements pagination
# ============================================================================
def test_announcements_bare_array_when_no_page_arg(client):
    admin_tok = _login_admin(client)
    r = client.get("/api/announcements/mine", headers=_h(admin_tok))
    assert r.status_code == 200
    assert isinstance(r.get_json(), list)


def test_announcements_envelope_when_page_supplied(client):
    admin_tok = _login_admin(client)
    r = client.get("/api/announcements/mine?page=1&pageSize=5",
                   headers=_h(admin_tok))
    assert r.status_code == 200
    body = r.get_json()
    assert isinstance(body, dict)
    assert body["pageSize"] == 5
    assert body["hasMore"] is False
    assert body["items"] == []


# ============================================================================
# T4 · FCM scaffolding — subscribe accepts mobile shape
# ============================================================================
def test_push_subscribe_accepts_fcm_token(client):
    """Phase 29 · T4 — server accepts a mobile-shaped subscription so
    the Flutter FCM branch can register even before the Firebase send
    side is activated. Row lands with platform='fcm' and endpoint=token."""
    admin_tok = _login_admin(client)
    r = client.post("/api/push/subscribe", json={
        "token": "fake-fcm-device-token-abc123",
        "platform": "fcm",
    }, headers=_h(admin_tok))
    assert r.status_code == 201, r.data
    body = r.get_json()
    assert body["platform"] == "fcm"
    assert body["endpoint"] == "fake-fcm-device-token-abc123"


def test_push_subscribe_accepts_apns_token(client):
    admin_tok = _login_admin(client)
    r = client.post("/api/push/subscribe", json={
        "token": "fake-apns-device-token-xyz789",
        "platform": "apns",
    }, headers=_h(admin_tok))
    assert r.status_code == 201, r.data
    assert r.get_json()["platform"] == "apns"


def test_fanout_no_ops_on_fcm_sub_when_sender_not_wired(client):
    """Fan-out should NOT raise when the only sub is mobile+unwired."""
    admin_tok = _login_admin(client)
    client.post("/api/push/subscribe", json={
        "token": "t1", "platform": "fcm",
    }, headers=_h(admin_tok))
    # Trigger enqueue by asking for the admin's own bell — enqueue is
    # normally called from write pipelines, but we can just invoke it
    # directly via the helper to prove the branch doesn't blow up.
    from utils.push import fan_out_to_user
    from models import User
    with client.application.app_context():
        admin = User.query.filter_by(email="admin@t.local").first()
        # Should NOT raise.
        fan_out_to_user(admin.id, {
            "title": "hi", "body": "test", "kind": "test",
        })


# =============================================================================
# Attendance history
# =============================================================================
def _h(tok):
    return {"X-Session-Token": tok}


def test_attendance_history_paginates_on_request(client):
    """Attendance is the one list that grows with time rather than roster
    size — one row per school day. It stays a bare array by default so the
    calendar view is unaffected, and returns the envelope when asked."""
    from tests.conftest import register_user

    admin_tok = client.post(
        "/api/auth/login", json={"email": "admin@t.local", "password": "adminpass1"},
    ).get_json()["sessionToken"]
    h = _h(admin_tok)

    section = client.post("/api/sections", json={"name": "Upper"}, headers=h).get_json()
    grade = client.post(
        "/api/grades",
        json={"name": "G9", "sectionId": section["id"], "orderIndex": 9},
        headers=h,
    ).get_json()
    klass = client.post(
        "/api/classes", json={"name": "9-A", "gradeId": grade["id"]}, headers=h,
    ).get_json()

    student = register_user(client, email="amira@t.local", role="student").get_json()
    student_id = student["user"]["id"]
    client.put(
        f"/api/users/{student_id}/class", json={"classId": klass["id"]}, headers=h,
    )

    for day in range(1, 8):
        r = client.put(
            f"/api/classes/{klass['id']}/attendance",
            json={
                "date": f"2026-03-{day:02d}",
                "marks": [{"studentId": student_id, "status": "present"}],
            },
            headers=h,
        )
        assert r.status_code == 200, r.data

    # Default: bare array, every mark.
    bare = client.get(f"/api/users/{student_id}/attendance", headers=h)
    assert bare.status_code == 200
    assert isinstance(bare.get_json(), list)
    assert len(bare.get_json()) == 7

    # Opt in: envelope, page-sized.
    paged = client.get(
        f"/api/users/{student_id}/attendance?page=1&pageSize=3", headers=h,
    ).get_json()
    # jsonify sorts keys, so compare as a set.
    assert set(paged) == {"items", "page", "pageSize", "hasMore"}
    assert len(paged["items"]) == 3
    assert paged["hasMore"] is True

    last = client.get(
        f"/api/users/{student_id}/attendance?page=3&pageSize=3", headers=h,
    ).get_json()
    assert len(last["items"]) == 1
    assert last["hasMore"] is False


def test_my_attendance_paginates_on_request(client):
    from tests.conftest import register_user

    admin_tok = client.post(
        "/api/auth/login", json={"email": "admin@t.local", "password": "adminpass1"},
    ).get_json()["sessionToken"]
    h = _h(admin_tok)

    section = client.post("/api/sections", json={"name": "Upper"}, headers=h).get_json()
    grade = client.post(
        "/api/grades",
        json={"name": "G9", "sectionId": section["id"], "orderIndex": 9},
        headers=h,
    ).get_json()
    klass = client.post(
        "/api/classes", json={"name": "9-A", "gradeId": grade["id"]}, headers=h,
    ).get_json()

    student = register_user(client, email="amira@t.local", role="student").get_json()
    client.put(
        f"/api/users/{student['user']['id']}/class",
        json={"classId": klass["id"]},
        headers=h,
    )
    for day in range(1, 5):
        client.put(
            f"/api/classes/{klass['id']}/attendance",
            json={
                "date": f"2026-03-{day:02d}",
                "marks": [{"studentId": student["user"]["id"], "status": "present"}],
            },
            headers=h,
        )

    own = _h(student["sessionToken"])
    assert len(client.get("/api/attendance/mine", headers=own).get_json()) == 4

    paged = client.get("/api/attendance/mine?pageSize=2", headers=own).get_json()
    assert len(paged["items"]) == 2
    assert paged["hasMore"] is True
