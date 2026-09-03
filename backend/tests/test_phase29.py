"""Phase 29 tests — pagination on notifications/threads/announcements.

* Notifications: 60 notifications for one user; page=1 returns 20 items
  with hasMore=True; last page returns hasMore=False. Legacy `limit=`
  still respected. Legacy `notifications` key still present.
* Messages threads: bare-array shape kept when no page arg; paged
  envelope when page/pageSize supplied.
* Announcements: same back-compat shape rule.
"""
from __future__ import annotations

import sys

import pytest


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx")
    for mod in [
        "config", "models",
        "utils.permissions", "utils.grading", "utils.quizzes",
        "utils.certificates", "utils.analytics", "utils.attendance",
        "utils.timetables", "utils.assignments", "utils.notifications",
        "utils.push", "utils.pdf", "utils.pagination",
        "routes", "routes.auth", "routes.users",
        "routes.sections", "routes.grades", "routes.classes",
        "routes.courses", "routes.modules", "routes.lessons",
        "routes.enrollments", "routes.students",
        "routes.department_leaders", "routes.uploads",
        "routes.progress", "routes.grading_admin",
        "routes.rubrics", "routes.grade_reports",
        "routes.quizzes", "routes.quiz_take", "routes.quiz_admin",
        "routes.certificates", "routes.dashboards", "routes.parents",
        "routes.attendance", "routes.timetables", "routes.assignments",
        "routes.checkpoints", "routes.assignment_groups",
        "routes.push", "routes.fees",
        "routes.notifications", "routes.messages", "routes.announcements",
        "app",
    ]:
        sys.modules.pop(mod, None)
    from app import create_app
    from config import Config
    from models import User, db

    inst = tmp_path / "instance"
    inst.mkdir()
    (inst / "uploads").mkdir()

    class TestConfig(Config):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{(tmp_path / 'test.db').as_posix()}"
        TESTING = True
        SQLALCHEMY_ENGINE_OPTIONS = {}
        MAX_CONTENT_LENGTH = 5 * 1024 * 1024

    app = create_app(TestConfig)
    app.instance_path = str(inst)
    with app.app_context():
        db.drop_all()
        db.create_all()
        u = User(name="Root Admin", email="admin@t.local", role="admin")
        u.set_password("adminpass1")
        db.session.add(u)
        db.session.commit()
    with app.test_client() as c:
        c.application = app
        yield c


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
