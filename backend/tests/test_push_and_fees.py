"""Web push subscriptions, fee items, and cohort comparison.

Push:
  * GET /push/public-key returns pushEnabled + publicKey when
    cryptography is available (or pushEnabled=false gracefully).
  * POST /push/subscribe upserts on (user_id, endpoint) and returns the
    row; re-subscribe with same endpoint returns the same id.
  * POST /push/unsubscribe removes the sub, is idempotent.
  * A non-subscribing user can't touch someone else's endpoint.

Fees:
  * Admin creates a fee for a student, student sees it in `/fees/mine`.
  * Parent linked to student sees the same fee.
  * Unrelated student cannot read another student's fees.
  * Admin logs partial payment → balance updates.
  * Payment > balance is refused.
  * PDF endpoint returns application/pdf when reportlab is available.

Cohort comparison:
  * Admin GETs /dashboards/cohort-comparison?termAId=…&termBId=…
    with a scaffolded student → both snapshots come back and shape
    matches the plan (perClass + overall metrics).

Originally Phase 28.
"""
from __future__ import annotations

from tests.conftest import register_user as _register


def _h(tok):
    return {"X-Session-Token": tok}


def _login(client, *, email, password):
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.data
    return r.get_json()["sessionToken"]


def _login_admin(client):
    return _login(client, email="admin@t.local", password="adminpass1")


def _place_student(client, admin_tok):
    """One section + grade + class + one student `amira@t.local` placed."""
    h = _h(admin_tok)
    section = client.post("/api/sections", json={"name": "S"},
                          headers=h).get_json()["id"]
    grade = client.post("/api/grades",
                        json={"name": "G", "sectionId": section, "orderIndex": 1},
                        headers=h).get_json()["id"]
    klass = client.post("/api/classes", json={"name": "K", "gradeId": grade},
                        headers=h).get_json()["id"]
    _register(client, "amira@t.local", role="student", name="Amira")
    amira_id = client.post("/api/auth/login", json={
        "email": "amira@t.local", "password": "password12",
    }).get_json()["user"]["id"]
    client.put(f"/api/users/{amira_id}/class",
               json={"classId": klass}, headers=h)
    return {"section": section, "grade": grade, "class": klass,
            "amira_id": amira_id}


# ============================================================================
# Push
# ============================================================================
def test_push_public_key_endpoint(client):
    admin_tok = _login_admin(client)
    r = client.get("/api/push/public-key", headers=_h(admin_tok))
    assert r.status_code == 200
    body = r.get_json()
    assert "pushEnabled" in body
    # publicKey may be null when cryptography lib is missing — that's OK.
    if body["pushEnabled"]:
        assert isinstance(body["publicKey"], str)
        assert len(body["publicKey"]) > 30


def test_push_subscribe_upserts_on_endpoint(client):
    admin_tok = _login_admin(client)
    body = {
        "endpoint": "https://push.example/xyz",
        "keys": {"p256dh": "p256dh-key", "auth": "auth-key"},
    }
    r = client.post("/api/push/subscribe", json=body, headers=_h(admin_tok))
    assert r.status_code == 201, r.data
    first_id = r.get_json()["id"]
    # Same endpoint again → same row.
    r = client.post("/api/push/subscribe", json=body, headers=_h(admin_tok))
    assert r.status_code == 201
    assert r.get_json()["id"] == first_id


def test_push_unsubscribe(client):
    admin_tok = _login_admin(client)
    body = {
        "endpoint": "https://push.example/z1",
        "keys": {"p256dh": "p", "auth": "a"},
    }
    client.post("/api/push/subscribe", json=body, headers=_h(admin_tok))
    r = client.post("/api/push/unsubscribe",
                    json={"endpoint": "https://push.example/z1"},
                    headers=_h(admin_tok))
    assert r.status_code == 200
    assert r.get_json()["removed"] == 1
    # Idempotent second call.
    r = client.post("/api/push/unsubscribe",
                    json={"endpoint": "https://push.example/z1"},
                    headers=_h(admin_tok))
    assert r.status_code == 200
    assert r.get_json()["removed"] == 0


def test_push_subscribe_rejects_bad_platform(client):
    admin_tok = _login_admin(client)
    r = client.post("/api/push/subscribe", json={
        "endpoint": "https://push.example/x",
        "keys": {"p256dh": "p", "auth": "a"},
        "platform": "smoke_signal",
    }, headers=_h(admin_tok))
    assert r.status_code == 400


# ============================================================================
# Fees
# ============================================================================
def test_admin_creates_fee_student_reads_it(client):
    admin_tok = _login_admin(client)
    s = _place_student(client, admin_tok)
    r = client.post(f"/api/students/{s['amira_id']}/fees", json={
        "label": "Term 1 tuition",
        "amount": "500.00",
        "currency": "USD",
        "dueDate": "2026-09-30",
    }, headers=_h(admin_tok))
    assert r.status_code == 201, r.data
    fee_id = r.get_json()["id"]

    stu_tok = _login(client, email="amira@t.local", password="password12")
    r = client.get("/api/fees/mine", headers=_h(stu_tok))
    assert r.status_code == 200
    body = r.get_json()
    assert body["totalAmount"] == 500.0
    assert body["totalBalance"] == 500.0
    assert any(i["id"] == fee_id for i in body["items"])


def test_partial_payment_updates_balance(client):
    admin_tok = _login_admin(client)
    s = _place_student(client, admin_tok)
    r = client.post(f"/api/students/{s['amira_id']}/fees", json={
        "label": "Trip fee", "amount": "120.00",
    }, headers=_h(admin_tok))
    fee_id = r.get_json()["id"]
    r = client.post(f"/api/fees/{fee_id}/payments",
                    json={"amount": "40.00", "method": "cash"},
                    headers=_h(admin_tok))
    assert r.status_code == 201, r.data
    body = r.get_json()
    assert body["fee"]["paidAmount"] == 40.0
    assert body["fee"]["balance"] == 80.0


def test_payment_exceeding_balance_is_refused(client):
    admin_tok = _login_admin(client)
    s = _place_student(client, admin_tok)
    r = client.post(f"/api/students/{s['amira_id']}/fees",
                    json={"label": "Small", "amount": "10.00"},
                    headers=_h(admin_tok))
    fee_id = r.get_json()["id"]
    r = client.post(f"/api/fees/{fee_id}/payments",
                    json={"amount": "999.00"}, headers=_h(admin_tok))
    assert r.status_code == 400


def test_other_student_cannot_read_fees(client):
    admin_tok = _login_admin(client)
    s = _place_student(client, admin_tok)
    client.post(f"/api/students/{s['amira_id']}/fees",
                json={"label": "T", "amount": "50.00"}, headers=_h(admin_tok))
    _register(client, "outsider@t.local", role="student", name="Out")
    out_tok = _login(client, email="outsider@t.local", password="password12")
    r = client.get(f"/api/students/{s['amira_id']}/fees",
                   headers=_h(out_tok))
    assert r.status_code == 403


def test_fees_pdf_returns_pdf(client):
    admin_tok = _login_admin(client)
    s = _place_student(client, admin_tok)
    client.post(f"/api/students/{s['amira_id']}/fees",
                json={"label": "T1", "amount": "300.00"},
                headers=_h(admin_tok))
    r = client.get(f"/api/students/{s['amira_id']}/fees.pdf",
                   headers=_h(admin_tok))
    assert r.status_code == 200
    assert r.mimetype == "application/pdf"
    assert r.data.startswith(b"%PDF-")


# ============================================================================
# Cohort comparison
# ============================================================================
def test_cohort_comparison_shape(client):
    admin_tok = _login_admin(client)
    s = _place_student(client, admin_tok)
    h = _h(admin_tok)
    yr = client.post("/api/school-years",
                     json={"name": "Y", "isCurrent": True}, headers=h)
    year_id = yr.get_json()["id"]
    a = client.post(f"/api/school-years/{year_id}/terms",
                    json={"name": "Q1", "orderIndex": 0}, headers=h)
    b = client.post(f"/api/school-years/{year_id}/terms",
                    json={"name": "Q2", "orderIndex": 1}, headers=h)
    a_id = a.get_json()["id"]
    b_id = b.get_json()["id"]

    r = client.get(
        f"/api/dashboards/cohort-comparison?termAId={a_id}&termBId={b_id}",
        headers=h,
    )
    assert r.status_code == 200, r.data
    body = r.get_json()
    assert body["termA"]["termId"] == a_id
    assert body["termB"]["termId"] == b_id
    for side in ("termA", "termB"):
        snap = body[side]
        assert isinstance(snap["perClass"], list)
        overall = snap["overall"]
        assert set(overall.keys()) == {
            "attendanceRate", "avgPercent", "passRate", "certCount",
        }


def test_cohort_comparison_requires_admin(client):
    admin_tok = _login_admin(client)
    _place_student(client, admin_tok)
    stu_tok = _login(client, email="amira@t.local", password="password12")
    r = client.get(
        "/api/dashboards/cohort-comparison?termAId=x&termBId=y",
        headers=_h(stu_tok),
    )
    assert r.status_code == 403
