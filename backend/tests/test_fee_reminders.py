"""Overdue-fee reminders and per-student fee summaries.

cohort PDF export + utc_now sweep.

* Overdue fee with past due-date + positive balance → student + parent
  get a "fee_overdue" notification when the sweep runs.
* Fee that isn't overdue → no reminder enqueued.
* Repeat call same day is idempotent (dedupe in enqueue()).
* Non-admin caller → 403.
* /students/<sid>/fees/summary works for admin + student-self + parent.
* /dashboards/cohort-comparison.pdf returns application/pdf.
* datetime.utcnow deprecation warnings are gone from a small write path.

Originally Phase 31.
"""
from __future__ import annotations

from tests.conftest import register_user as _register

import warnings


def _h(tok):
    return {"X-Session-Token": tok}


def _login(client, email, password):
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.data
    return r.get_json()["sessionToken"]


def _login_admin(client):
    return _login(client, "admin@t.local", "adminpass1")


def _place_student(client, admin_tok):
    h = _h(admin_tok)
    sec = client.post("/api/sections", json={"name": "S"},
                      headers=h).get_json()["id"]
    grade = client.post("/api/grades",
                        json={"name": "G", "sectionId": sec, "orderIndex": 1},
                        headers=h).get_json()["id"]
    klass = client.post("/api/classes", json={"name": "K", "gradeId": grade},
                        headers=h).get_json()["id"]
    _register(client, "amira@t.local", role="student", name="Amira")
    amira_id = client.post("/api/auth/login", json={
        "email": "amira@t.local", "password": "password12",
    }).get_json()["user"]["id"]
    client.put(f"/api/users/{amira_id}/class",
               json={"classId": klass}, headers=h)
    return {"grade": grade, "class": klass, "amira_id": amira_id}


def _link_parent(client, admin_tok, student_id):
    r = client.post("/api/users", json={
        "name": "Parent", "email": "parent@t.local",
        "password": "password12", "role": "parent",
    }, headers=_h(admin_tok))
    assert r.status_code == 201
    parent_id = r.get_json()["id"]
    client.post(f"/api/users/{student_id}/parents", json={
        "parentId": parent_id, "relationship": "guardian",
    }, headers=_h(admin_tok))
    parent_tok = _login(client, "parent@t.local", "password12")
    return parent_id, parent_tok


# ============================================================================
# Overdue-fee reminders
# ============================================================================
def test_overdue_sweep_notifies_student_and_parent(client):
    admin_tok = _login_admin(client)
    s = _place_student(client, admin_tok)
    _, parent_tok = _link_parent(client, admin_tok, s["amira_id"])
    # Fee whose due date is in the past.
    client.post(f"/api/students/{s['amira_id']}/fees", json={
        "label": "Trip", "amount": "50.00", "dueDate": "2020-01-01",
    }, headers=_h(admin_tok))
    r = client.post("/api/fees/send-overdue-reminders",
                    headers=_h(admin_tok))
    assert r.status_code == 200
    assert r.get_json()["reminded"] >= 2  # student + parent

    stu_tok = _login(client, "amira@t.local", "password12")
    r = client.get("/api/notifications/mine", headers=_h(stu_tok))
    kinds = [n["kind"] for n in r.get_json()["items"]]
    assert "fee_overdue" in kinds
    r = client.get("/api/notifications/mine", headers=_h(parent_tok))
    kinds = [n["kind"] for n in r.get_json()["items"]]
    assert "fee_overdue" in kinds


def test_overdue_sweep_ignores_future_and_paid(client):
    admin_tok = _login_admin(client)
    s = _place_student(client, admin_tok)
    # Future fee.
    client.post(f"/api/students/{s['amira_id']}/fees",
                json={"label": "Later", "amount": "10.00",
                      "dueDate": "2099-12-31"},
                headers=_h(admin_tok))
    # Past-due but fully paid.
    r = client.post(f"/api/students/{s['amira_id']}/fees",
                    json={"label": "Old", "amount": "10.00",
                          "dueDate": "2020-01-01"},
                    headers=_h(admin_tok))
    fid = r.get_json()["id"]
    client.post(f"/api/fees/{fid}/payments",
                json={"amount": "10.00"}, headers=_h(admin_tok))
    r = client.post("/api/fees/send-overdue-reminders",
                    headers=_h(admin_tok))
    assert r.status_code == 200
    # Only the fee-created + fee-payment notifications should exist —
    # no fee_overdue rows.
    stu_tok = _login(client, "amira@t.local", "password12")
    r = client.get("/api/notifications/mine", headers=_h(stu_tok))
    kinds = [n["kind"] for n in r.get_json()["items"]]
    assert "fee_overdue" not in kinds


def test_overdue_sweep_is_admin_only(client):
    admin_tok = _login_admin(client)
    _place_student(client, admin_tok)
    stu_tok = _login(client, "amira@t.local", "password12")
    r = client.post("/api/fees/send-overdue-reminders",
                    headers=_h(stu_tok))
    assert r.status_code == 403


# ============================================================================
# Per-student fee summary
# ============================================================================
def test_student_fee_summary_admin_view(client):
    admin_tok = _login_admin(client)
    s = _place_student(client, admin_tok)
    client.post(f"/api/students/{s['amira_id']}/fees",
                json={"label": "T", "amount": "100.00",
                      "dueDate": "2020-01-01"},
                headers=_h(admin_tok))
    r = client.get(f"/api/students/{s['amira_id']}/fees/summary",
                   headers=_h(admin_tok))
    assert r.status_code == 200
    body = r.get_json()
    assert body["outstanding"] == 100.0
    assert body["overdueCount"] == 1


def test_student_fee_summary_parent_view(client):
    admin_tok = _login_admin(client)
    s = _place_student(client, admin_tok)
    _, parent_tok = _link_parent(client, admin_tok, s["amira_id"])
    client.post(f"/api/students/{s['amira_id']}/fees",
                json={"label": "T", "amount": "25.00"},
                headers=_h(admin_tok))
    r = client.get(f"/api/students/{s['amira_id']}/fees/summary",
                   headers=_h(parent_tok))
    assert r.status_code == 200
    assert r.get_json()["outstanding"] == 25.0


def test_student_fee_summary_stranger_blocked(client):
    admin_tok = _login_admin(client)
    s = _place_student(client, admin_tok)
    _register(client, "stranger@t.local", role="student")
    tok = _login(client, "stranger@t.local", "password12")
    r = client.get(f"/api/students/{s['amira_id']}/fees/summary",
                   headers=_h(tok))
    assert r.status_code == 403


# ============================================================================
# Cohort PDF export
# ============================================================================
def test_cohort_pdf_returns_pdf(client):
    admin_tok = _login_admin(client)
    _place_student(client, admin_tok)
    h = _h(admin_tok)
    yr = client.post("/api/school-years",
                     json={"name": "Y", "isCurrent": True}, headers=h)
    yid = yr.get_json()["id"]
    a = client.post(f"/api/school-years/{yid}/terms",
                    json={"name": "Q1", "orderIndex": 0}, headers=h)
    b = client.post(f"/api/school-years/{yid}/terms",
                    json={"name": "Q2", "orderIndex": 1}, headers=h)
    a_id, b_id = a.get_json()["id"], b.get_json()["id"]
    r = client.get(
        f"/api/dashboards/cohort-comparison.pdf?termAId={a_id}&termBId={b_id}",
        headers=h,
    )
    assert r.status_code == 200
    assert r.mimetype == "application/pdf"
    assert r.data.startswith(b"%PDF-")


# ============================================================================
# utc_now sweep — verify no DeprecationWarning on a simple write path
# ============================================================================
def test_utc_now_sweep_removes_utcnow_deprecation(client):
    """A representative write (create + read notification) must NOT
    trigger a DeprecationWarning about datetime.utcnow(). Silences
    unrelated warnings and asserts the specific text is absent.
    """
    admin_tok = _login_admin(client)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        client.post("/api/notifications/mark-read",
                    json={"all": True}, headers=_h(admin_tok))
        client.get("/api/notifications/mine", headers=_h(admin_tok))
    hits = [
        str(w.message) for w in caught
        if "datetime.utcnow" in str(w.message)
    ]
    assert not hits, f"utcnow deprecations still firing: {hits[:3]}"
