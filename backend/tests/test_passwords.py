"""Password change, admin reset, and the forced-change flag.

None of this existed before: `routes/auth.py` exposed only register / login /
me / logout, and `routes/users.py` set a password exactly once at account
creation. A school that bulk-imported 400 students had 400 accounts stuck for
good on a password the office had picked — the import UI even told the admin
to "ask each to reset on first login", with nothing to reset it with.

Named for the feature rather than the build phase it landed in, unlike the
`test_phaseNN.py` files around it.
"""
from __future__ import annotations

import io

from tests.conftest import register_user as _register


def _h(tok):
    return {"X-Session-Token": tok}


def _login(client, email, password):
    return client.post("/api/auth/login", json={"email": email, "password": password})


def _login_admin(client):
    return _login(client, "admin@t.local", "adminpass1").get_json()["sessionToken"]


# =============================================================================
# Changing your own password
# =============================================================================
def test_change_password_then_sign_in_with_the_new_one(client):
    tok = _register(client, email="s@t.local", role="student").get_json()["sessionToken"]

    r = client.post(
        "/api/auth/password",
        json={"currentPassword": "password12", "newPassword": "brand-new-pw-9"},
        headers=_h(tok),
    )
    assert r.status_code == 200, r.data

    assert _login(client, "s@t.local", "password12").status_code == 401
    assert _login(client, "s@t.local", "brand-new-pw-9").status_code == 200


def test_change_password_requires_the_current_one(client):
    tok = _register(client, email="s@t.local", role="student").get_json()["sessionToken"]

    r = client.post(
        "/api/auth/password",
        json={"currentPassword": "not-my-password", "newPassword": "brand-new-pw-9"},
        headers=_h(tok),
    )
    assert r.status_code == 403
    # The old password still works — nothing was changed.
    assert _login(client, "s@t.local", "password12").status_code == 200


def test_change_password_revokes_other_sessions_but_keeps_this_one(client):
    """A password change is what you do when someone else knows it, so every
    other device has to lose access — while the device that made the change
    stays signed in on a freshly issued token."""
    _register(client, email="s@t.local", role="student")
    other_device = _login(client, "s@t.local", "password12").get_json()["sessionToken"]
    this_device = _login(client, "s@t.local", "password12").get_json()["sessionToken"]

    r = client.post(
        "/api/auth/password",
        json={"currentPassword": "password12", "newPassword": "brand-new-pw-9"},
        headers=_h(this_device),
    )
    assert r.status_code == 200
    reissued = r.get_json()["sessionToken"]

    assert client.get("/api/auth/me", headers=_h(other_device)).status_code == 401
    assert client.get("/api/auth/me", headers=_h(reissued)).status_code == 200


def test_change_password_rejects_weak_and_unchanged_values(client):
    tok = _register(client, email="s@t.local", role="student").get_json()["sessionToken"]

    for candidate in ("short", "changeme123", "password12"):
        r = client.post(
            "/api/auth/password",
            json={"currentPassword": "password12", "newPassword": candidate},
            headers=_h(tok),
        )
        assert r.status_code == 400, f"{candidate!r} should have been refused"


def test_change_password_requires_authentication(client):
    r = client.post(
        "/api/auth/password",
        json={"currentPassword": "password12", "newPassword": "brand-new-pw-9"},
    )
    assert r.status_code == 401


# =============================================================================
# Admin reset
# =============================================================================
def test_admin_reset_issues_a_working_temporary_password(client):
    admin_tok = _login_admin(client)
    student_id = _register(client, email="s@t.local", role="student").get_json()["user"]["id"]

    r = client.post(f"/api/users/{student_id}/password", headers=_h(admin_tok))
    assert r.status_code == 200, r.data
    temporary = r.get_json()["temporaryPassword"]
    assert temporary and temporary != "password12"

    assert _login(client, "s@t.local", "password12").status_code == 401
    signed_in = _login(client, "s@t.local", temporary)
    assert signed_in.status_code == 200
    assert signed_in.get_json()["user"]["mustChangePassword"] is True


def test_admin_reset_signs_the_holder_out_everywhere(client):
    admin_tok = _login_admin(client)
    reg = _register(client, email="s@t.local", role="student").get_json()
    student_id, student_tok = reg["user"]["id"], reg["sessionToken"]

    assert client.get("/api/auth/me", headers=_h(student_tok)).status_code == 200
    client.post(f"/api/users/{student_id}/password", headers=_h(admin_tok))
    assert client.get("/api/auth/me", headers=_h(student_tok)).status_code == 401


def test_admin_cannot_reset_another_admins_password(client):
    """One admin quietly taking over a peer admin account is exactly the hole
    that `_ADMIN_CREATE_ROLES` closes on the create path."""
    admin_tok = _login_admin(client)
    me = client.get("/api/auth/me", headers=_h(admin_tok)).get_json()["user"]

    r = client.post(f"/api/users/{me['id']}/password", headers=_h(admin_tok))
    assert r.status_code == 403


def test_non_admin_cannot_reset_anyone(client):
    victim_id = _register(client, email="v@t.local", role="student").get_json()["user"]["id"]
    attacker = _register(client, email="a@t.local", role="student").get_json()["sessionToken"]

    r = client.post(f"/api/users/{victim_id}/password", headers=_h(attacker))
    assert r.status_code == 403


def test_admin_reset_404s_for_an_unknown_user(client):
    admin_tok = _login_admin(client)
    r = client.post("/api/users/no-such-id/password", headers=_h(admin_tok))
    assert r.status_code == 404


# =============================================================================
# The forced-change flag
# =============================================================================
def test_admin_created_accounts_must_change_password(client):
    signed_in = _register(client, email="t@t.local", role="instructor").get_json()
    assert signed_in["user"]["mustChangePassword"] is True


def test_self_registered_students_are_not_forced_to_change(client):
    signed_in = _register(client, email="s@t.local", role="student").get_json()
    assert signed_in["user"]["mustChangePassword"] is False


def test_changing_your_password_clears_the_flag(client):
    reg = _register(client, email="t@t.local", role="instructor").get_json()
    assert reg["user"]["mustChangePassword"] is True

    r = client.post(
        "/api/auth/password",
        json={"currentPassword": "password12", "newPassword": "chosen-by-me-1"},
        headers=_h(reg["sessionToken"]),
    )
    assert r.status_code == 200
    assert r.get_json()["user"]["mustChangePassword"] is False


def test_bulk_import_gives_every_user_a_distinct_password(client):
    """A single shared `changeme123` meant one leaked row handed you the
    whole school."""
    admin_tok = _login_admin(client)
    csv = (
        "email,name,role\n"
        "a@t.local,A One,student\n"
        "b@t.local,B Two,student\n"
        "c@t.local,C Three,student\n"
    )
    r = client.post(
        "/api/admin/users/import",
        data={"file": (io.BytesIO(csv.encode()), "users.csv")},
        headers=_h(admin_tok),
        content_type="multipart/form-data",
    )
    assert r.status_code == 200, r.data
    created = r.get_json()["created"]
    assert len(created) == 3

    passwords = [row["temporaryPassword"] for row in created]
    assert all(passwords), "every created row must carry its own password"
    assert len(set(passwords)) == 3, "passwords must not be shared between users"
    assert "changeme123" not in passwords

    # And each one actually signs its own user in, flagged for a change.
    signed_in = _login(client, "a@t.local", passwords[0])
    assert signed_in.status_code == 200
    assert signed_in.get_json()["user"]["mustChangePassword"] is True


# =============================================================================
# Self-registration is students-only
# =============================================================================
def test_self_registration_refuses_instructor_role(client):
    r = client.post(
        "/api/auth/register",
        json={
            "name": "Walk In",
            "email": "walkin@t.local",
            "password": "password12",
            "role": "instructor",
        },
    )
    assert r.status_code == 400
    assert "role" in r.get_json()["error"].lower()


def test_self_registration_rejects_a_banned_password(client):
    r = client.post(
        "/api/auth/register",
        json={
            "name": "S",
            "email": "s@t.local",
            "password": "changeme123",
            "role": "student",
        },
    )
    assert r.status_code == 400
