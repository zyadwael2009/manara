"""Shared test fixtures.

This file replaces 29 near-identical copies of a `client` fixture, one per
test module. Each copy rebuilt the world for every single test function: it
popped ~30 entries out of `sys.modules`, re-imported the whole application
(2,500 lines of models plus 48 route modules), then ran `drop_all()` +
`create_all()` over 50-odd tables against a fresh on-disk SQLite file.

That cost about two seconds per test, so the suite took over ten minutes —
and the repeated re-import churn is what made pytest itself die with a
`MemoryError` while rendering a warning summary.

The app is now built once per session and the per-test isolation comes from
deleting rows, which is what the tests actually depend on. The module-reload
dance existed to pick up `monkeypatch.setenv` before `config` was imported;
setting the environment here at import time, before pytest collects any test
module, achieves the same thing once instead of 292 times.
"""
from __future__ import annotations

import os

import pytest

# Must happen before anything imports `config`, which reads the environment at
# class-definition time. conftest is imported ahead of every test module, so
# this is the earliest hook available.
os.environ["DATABASE_URL"] = ""
os.environ["SECRET_KEY"] = "test-secret-key-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
os.environ["MANARA_ENV"] = "test"

ADMIN_EMAIL = "admin@t.local"
ADMIN_PASSWORD = "adminpass1"


@pytest.fixture(scope="session")
def app(tmp_path_factory):
    """One application, one database, for the whole session."""
    root = tmp_path_factory.mktemp("manara")
    instance = root / "instance"
    (instance / "uploads").mkdir(parents=True)

    from app import create_app
    from config import Config

    class TestConfig(Config):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{(root / 'test.db').as_posix()}"
        TESTING = True
        SQLALCHEMY_ENGINE_OPTIONS = {}
        # Several tests assert the 413 branch; 5 MB keeps those payloads small.
        MAX_CONTENT_LENGTH = 5 * 1024 * 1024
        # Password hashing is ~80 ms a call by design, and the suite does a
        # dozen per test. `models.password_hash_kwargs` only honours this
        # when TESTING is set, so production storage is untouched.
        PASSWORD_HASH_METHOD = "pbkdf2:sha256:1"

    application = create_app(TestConfig)
    application.instance_path = str(instance)

    from models import db

    with application.app_context():
        db.drop_all()
        db.create_all()

    return application


@pytest.fixture()
def client(app):
    """A signed-out test client against an empty school with one root admin.

    Isolation is by truncation rather than `drop_all()`/`create_all()`:
    dropping and recreating 50-odd tables is DDL, which is by far the most
    expensive thing a fixture can do, and nothing here depends on the schema
    being rebuilt.
    """
    from models import User, db

    with app.app_context():
        _truncate_all(db)
        root_admin = User(name="Root Admin", email=ADMIN_EMAIL, role="admin")
        root_admin.set_password(ADMIN_PASSWORD)
        db.session.add(root_admin)
        db.session.commit()

    # The in-memory rate limiter is process-global. It used to be discarded
    # with the module reload; now it has to be cleared by hand, or a test that
    # exercises a limit poisons whatever runs after it.
    from utils.rate_limit import _reset_all

    _reset_all()

    with app.test_client() as test_client:
        # A few tests reach for `client.application` to push a context.
        test_client.application = app
        yield test_client


def _truncate_all(db) -> None:
    """Delete every row, children first.

    `sorted_tables` is dependency-ordered (parents first), so reversing it
    deletes children before the rows they point at and no FK is ever left
    dangling mid-teardown.
    """
    for table in reversed(db.metadata.sorted_tables):
        db.session.execute(table.delete())
    db.session.commit()


@pytest.fixture()
def app_context(app):
    """For the handful of tests that call model/util code directly."""
    with app.app_context():
        yield app


# ---------------------------------------------------------------------------
# Account creation
# ---------------------------------------------------------------------------
def register_user(
    client,
    email=None,
    *,
    password="password12",
    role="student",
    name="U",
):
    """Create an account and return a response carrying user + sessionToken.

    Self-registration is students-only, so staff and parent accounts are
    created by the root admin and then signed in — the same two steps the
    school office takes. Callers get the same `{"user", "sessionToken"}`
    envelope either way, which is why ~30 tests could keep calling this
    without caring which path ran.

    Accepts `email` positionally or by keyword: the per-module helpers this
    replaced were split between the two spellings.
    """
    payload = {"name": name, "email": email, "password": password, "role": role}

    if role in ("student",):
        return client.post("/api/auth/register", json=payload)

    admin_token = client.post(
        "/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    ).get_json()["sessionToken"]

    created = client.post(
        "/api/users",
        json=payload,
        headers={"X-Session-Token": admin_token},
    )
    if created.status_code != 201:
        return created  # let the caller's assertion report the real error

    return client.post(
        "/api/auth/login", json={"email": email, "password": password},
    )
