"""PDF report cards and transcripts, and the withdrawal flow.

PDF surfaces are verified by content-type + size + magic-bytes (not by
parsing the PDF); the render helpers are called directly, so a broken
render throws at test time.

Withdraw flow guards:
  * Admin-only.
  * Flips is_active=False, sets withdrawn_at, nulls class_id.
  * Soft-drops active enrollments (status='dropped').
  * Preserves grade entries + certificates.
  * Writes a WithdrawalLog row.
  * Repeat withdraw returns 409.

Originally Phase 23.
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


def _scaffold(client, admin_tok):
    """Grade 9 / 9-A / English 9 / Amira placed with one grade entry."""
    h = _h(admin_tok)
    r = client.post("/api/sections", json={"name": "High"}, headers=h)
    high = r.get_json()["id"]
    r = client.post("/api/grades",
                    json={"name": "Grade 9", "sectionId": high, "orderIndex": 9},
                    headers=h)
    g9 = r.get_json()["id"]
    r = client.post("/api/classes", json={"name": "9-A", "gradeId": g9}, headers=h)
    c9a = r.get_json()["id"]
    r = client.post("/api/courses",
                    json={"title": "English 9", "gradeId": g9, "category": "english"},
                    headers=h)
    eng = r.get_json()
    r = client.post(f"/api/courses/{eng['id']}/modules",
                    json={"title": "M1"}, headers=h)
    module = r.get_json()
    client.post(f"/api/modules/{module['id']}/lessons",
                json={"title": "L", "type": "text", "contentText": "x"},
                headers=h)
    client.post(f"/api/courses/{eng['id']}/publish", headers=h)
    _register(client, "amira@t.local", role="student", name="Amira")
    amira_id = client.post("/api/auth/login", json={
        "email": "amira@t.local", "password": "password12",
    }).get_json()["user"]["id"]
    client.put(f"/api/users/{amira_id}/class", json={"classId": c9a}, headers=h)
    # School year + Q1 + grading scale + rubric + a grade entry.
    r = client.post("/api/school-years",
                    json={"name": "Y", "isCurrent": True}, headers=h)
    year = r.get_json()["id"]
    r = client.post(f"/api/school-years/{year}/terms",
                    json={"name": "Q1", "orderIndex": 0}, headers=h)
    q1 = r.get_json()["id"]
    r = client.post("/api/grade-categories",
                    json={"name": "Final", "slug": "final_exam"}, headers=h)
    final_cat = r.get_json()
    for mn, mx, letter, gpa in [(60, 100, "A", 4.0), (0, 59, "F", 0.0)]:
        client.post("/api/grading-scale", json={
            "minPercent": mn, "maxPercent": mx, "letter": letter, "gpaValue": gpa,
        }, headers=h)
    client.put(f"/api/courses/{eng['id']}/rubric", json={
        "items": [
            {"gradeCategoryId": final_cat["id"], "maxScore": 100, "orderIndex": 0},
        ],
    }, headers=h)
    from models import Enrollment
    e = Enrollment.query.filter_by(
        student_id=amira_id, course_id=eng["id"],
    ).first()
    client.put(f"/api/enrollments/{e.id}/grades", json={
        "termId": q1,
        "entries": [{"gradeCategoryId": final_cat["id"], "score": 88}],
    }, headers=h)
    return {"class_a": c9a, "amira_id": amira_id, "course": eng, "term": q1}


# ---------------------------------------------------------------------------
# PDF endpoints
# ---------------------------------------------------------------------------
def _looks_like_pdf(body: bytes) -> bool:
    return len(body) > 400 and body.startswith(b"%PDF-")


def test_report_card_pdf_student_can_download_own(client):
    admin = _login_admin(client)
    s = _scaffold(client, admin)
    stu = _login(client, email="amira@t.local", password="password12")
    r = client.get(f"/api/students/{s['amira_id']}/report-card.pdf",
                   headers=_h(stu))
    assert r.status_code == 200
    assert r.headers["Content-Type"].startswith("application/pdf")
    assert _looks_like_pdf(r.data)


def test_report_card_pdf_admin_can_download_any(client):
    admin = _login_admin(client)
    s = _scaffold(client, admin)
    r = client.get(f"/api/students/{s['amira_id']}/report-card.pdf",
                   headers=_h(admin))
    assert r.status_code == 200
    assert _looks_like_pdf(r.data)


def test_report_card_pdf_unrelated_forbidden(client):
    admin = _login_admin(client)
    s = _scaffold(client, admin)
    _register(client, "other@t.local", role="student", name="Other")
    other = _login(client, email="other@t.local", password="password12")
    r = client.get(f"/api/students/{s['amira_id']}/report-card.pdf",
                   headers=_h(other))
    assert r.status_code == 403


def test_transcript_pdf_admin_can_download(client):
    admin = _login_admin(client)
    s = _scaffold(client, admin)
    r = client.get(f"/api/students/{s['amira_id']}/transcript.pdf",
                   headers=_h(admin))
    assert r.status_code == 200
    assert _looks_like_pdf(r.data)


# ---------------------------------------------------------------------------
# Withdraw
# ---------------------------------------------------------------------------
def test_non_admin_cannot_withdraw(client):
    admin = _login_admin(client)
    s = _scaffold(client, admin)
    stu = _login(client, email="amira@t.local", password="password12")
    r = client.post(f"/api/users/{s['amira_id']}/withdraw",
                    json={"reason": "leaving"}, headers=_h(stu))
    assert r.status_code in (401, 403)


def test_withdraw_soft_deletes_and_preserves_history(client):
    admin = _login_admin(client)
    s = _scaffold(client, admin)
    r = client.post(f"/api/users/{s['amira_id']}/withdraw", json={
        "reason": "Moved schools", "effectiveDate": "2026-01-15",
    }, headers=_h(admin))
    assert r.status_code == 200, r.data
    body = r.get_json()
    assert body["student"]["isActive"] is False
    assert body["log"]["reason"] == "Moved schools"
    assert body["log"]["effectiveDate"] == "2026-01-15"
    assert body["droppedEnrollments"] >= 1

    # DB assertions: user is deactivated, class_id cleared, enrollments
    # soft-dropped, grade entries preserved.
    from models import Enrollment, GradeEntry, User, WithdrawalLog
    amira = User.query.filter_by(email="amira@t.local").first()
    assert amira.is_active is False
    assert amira.withdrawn_at is not None
    assert amira.class_id is None
    # Enrollments: all dropped.
    assert Enrollment.query.filter_by(
        student_id=amira.id, status="active",
    ).count() == 0
    assert Enrollment.query.filter_by(
        student_id=amira.id, status="dropped",
    ).count() >= 1
    # Grade entries preserved.
    assert GradeEntry.query.join(
        Enrollment, Enrollment.id == GradeEntry.enrollment_id
    ).filter(Enrollment.student_id == amira.id).count() >= 1
    # Withdrawal log row.
    assert WithdrawalLog.query.filter_by(student_id=amira.id).count() == 1


def test_repeat_withdraw_returns_409(client):
    admin = _login_admin(client)
    s = _scaffold(client, admin)
    client.post(f"/api/users/{s['amira_id']}/withdraw",
                json={"reason": "first"}, headers=_h(admin))
    r = client.post(f"/api/users/{s['amira_id']}/withdraw",
                    json={"reason": "second"}, headers=_h(admin))
    assert r.status_code == 409
