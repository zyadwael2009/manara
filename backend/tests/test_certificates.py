"""Certificates — the eligibility gate, auto-issue, verify, and revoke.

Originally Phase 5.
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


def _bootstrap_full(client, admin_tok):
    """Grade 9 / class 9-A / course with rubric + grading scale + Q1 term.
    Returns ids you need plus a helper to complete a student."""
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
                    json={"title": "Alg1", "gradeId": g9, "category": "math"},
                    headers=h)
    course = r.get_json()
    r = client.post(f"/api/courses/{course['id']}/modules",
                    json={"title": "M1"}, headers=h)
    module = r.get_json()
    # 2 lessons for progress math.
    for i in range(2):
        client.post(f"/api/modules/{module['id']}/lessons",
                    json={"title": f"L{i+1}", "type": "text", "contentText": "x"},
                    headers=h)
    client.post(f"/api/courses/{course['id']}/publish", headers=h)

    # Grading infra.
    cats = {}
    for slug, name in [
        ("commitment", "Commitment"),
        ("final_exam", "Final Exam"),
    ]:
        r = client.post("/api/grade-categories", json={"name": name, "slug": slug}, headers=h)
        cats[slug] = r.get_json()["id"]
    for mn, mx, letter, gpa in [
        (93, 100, "A", 4.0),
        (60, 92, "B", 3.0),
        (0, 59, "F", 0.0),
    ]:
        client.post("/api/grading-scale",
                    json={"minPercent": mn, "maxPercent": mx, "letter": letter, "gpaValue": gpa},
                    headers=h)
    client.put(f"/api/courses/{course['id']}/rubric",
               json={"items": [
                   {"gradeCategoryId": cats["commitment"], "maxScore": 40, "orderIndex": 0},
                   {"gradeCategoryId": cats["final_exam"], "maxScore": 60, "orderIndex": 1},
               ]}, headers=h)

    r = client.post("/api/school-years",
                    json={"name": "2025-2026", "isCurrent": True}, headers=h)
    year = r.get_json()["id"]
    r = client.post(f"/api/school-years/{year}/terms",
                    json={"name": "Q1", "orderIndex": 0}, headers=h)
    q1 = r.get_json()["id"]

    return {"g9": g9, "class9a": c9a, "course": course, "module": module, "q1": q1, "cats": cats}


def _complete_all_lessons(client, stu_tok, course_id):
    r = client.get(f"/api/courses/{course_id}", headers=_h(stu_tok))
    body = r.get_json()
    for mod in body["modules"]:
        for lesson in mod["lessons"]:
            client.post(f"/api/lessons/{lesson['id']}/complete", headers=_h(stu_tok))


# ---------------------------------------------------------------------------
# Happy path: full gate → auto-issue
# ---------------------------------------------------------------------------
def test_full_gate_auto_issues_certificate(client):
    admin_tok = _login_admin(client)
    ids = _bootstrap_full(client, admin_tok)

    r = _register(client, email="a@t.local", role="student")
    sid = r.get_json()["user"]["id"]
    client.put(f"/api/users/{sid}/class",
               json={"classId": ids["class9a"]}, headers=_h(admin_tok))
    stu = _login(client, email="a@t.local", password="password12")

    # Get enrollment id.
    enrollment_id = client.get("/api/enrollments/mine",
                                headers=_h(stu)).get_json()[0]["id"]

    # Grade the student well.
    client.put(f"/api/enrollments/{enrollment_id}/grades",
               json={"termId": ids["q1"],
                     "entries": [
                         {"gradeCategoryId": ids["cats"]["commitment"], "score": 40},
                         {"gradeCategoryId": ids["cats"]["final_exam"], "score": 60},
                     ]},
               headers=_h(admin_tok))

    # Complete every lesson → last write should trigger auto-issue.
    _complete_all_lessons(client, stu, ids["course"]["id"])

    # Cert should now exist.
    r = client.get("/api/certificates/mine", headers=_h(stu))
    body = r.get_json()
    assert len(body) == 1
    assert body[0]["certificateNumber"].startswith("LMS-")
    assert body[0]["revoked"] is False


# ---------------------------------------------------------------------------
# Gate stays closed with low grade
# ---------------------------------------------------------------------------
def test_low_grade_blocks_certificate(client):
    admin_tok = _login_admin(client)
    ids = _bootstrap_full(client, admin_tok)

    r = _register(client, email="b@t.local", role="student")
    sid = r.get_json()["user"]["id"]
    client.put(f"/api/users/{sid}/class",
               json={"classId": ids["class9a"]}, headers=_h(admin_tok))
    stu = _login(client, email="b@t.local", password="password12")
    enrollment_id = client.get("/api/enrollments/mine",
                                headers=_h(stu)).get_json()[0]["id"]

    # Grade below 60 (default threshold): 40+15 = 55/100 → 55% → F.
    client.put(f"/api/enrollments/{enrollment_id}/grades",
               json={"termId": ids["q1"],
                     "entries": [
                         {"gradeCategoryId": ids["cats"]["commitment"], "score": 40},
                         {"gradeCategoryId": ids["cats"]["final_exam"], "score": 15},
                     ]},
               headers=_h(admin_tok))
    _complete_all_lessons(client, stu, ids["course"]["id"])

    r = client.get("/api/certificates/mine", headers=_h(stu))
    assert r.get_json() == []


# ---------------------------------------------------------------------------
# Gate stays closed with unpassed quiz
# ---------------------------------------------------------------------------
def test_unpassed_quiz_blocks_certificate(client):
    admin_tok = _login_admin(client)
    ids = _bootstrap_full(client, admin_tok)
    # Add a quiz with a required correct answer.
    r = client.post(f"/api/modules/{ids['module']['id']}/quizzes",
                    json={"title": "Q", "passingScore": 60}, headers=_h(admin_tok))
    quiz = r.get_json()
    r = client.post(f"/api/quizzes/{quiz['id']}/questions",
                    json={"type": "mc_single", "prompt": "?", "points": 1},
                    headers=_h(admin_tok))
    qq = r.get_json()
    client.post(f"/api/quiz-questions/{qq['id']}/options",
                json={"text": "A", "isCorrect": True}, headers=_h(admin_tok))
    client.post(f"/api/quiz-questions/{qq['id']}/options",
                json={"text": "B", "isCorrect": False}, headers=_h(admin_tok))
    client.post(f"/api/quizzes/{quiz['id']}/publish", headers=_h(admin_tok))

    r = _register(client, email="c@t.local", role="student")
    sid = r.get_json()["user"]["id"]
    client.put(f"/api/users/{sid}/class",
               json={"classId": ids["class9a"]}, headers=_h(admin_tok))
    stu = _login(client, email="c@t.local", password="password12")
    enrollment_id = client.get("/api/enrollments/mine",
                                headers=_h(stu)).get_json()[0]["id"]
    # Great grades.
    client.put(f"/api/enrollments/{enrollment_id}/grades",
               json={"termId": ids["q1"],
                     "entries": [
                         {"gradeCategoryId": ids["cats"]["commitment"], "score": 40},
                         {"gradeCategoryId": ids["cats"]["final_exam"], "score": 60},
                     ]},
               headers=_h(admin_tok))
    _complete_all_lessons(client, stu, ids["course"]["id"])

    r = client.get("/api/certificates/mine", headers=_h(stu))
    assert r.get_json() == []


# ---------------------------------------------------------------------------
# Empty-quizzes case: cert IS issued (no quiz required to pass)
# ---------------------------------------------------------------------------
def test_no_quizzes_still_issues(client):
    # This is exactly what test_full_gate_auto_issues_certificate covers —
    # no quizzes exist on the seeded course, and cert issues.
    pass


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------
def test_idempotent_issue(client):
    admin_tok = _login_admin(client)
    ids = _bootstrap_full(client, admin_tok)
    r = _register(client, email="d@t.local", role="student")
    sid = r.get_json()["user"]["id"]
    client.put(f"/api/users/{sid}/class",
               json={"classId": ids["class9a"]}, headers=_h(admin_tok))
    stu = _login(client, email="d@t.local", password="password12")
    enrollment_id = client.get("/api/enrollments/mine",
                                headers=_h(stu)).get_json()[0]["id"]
    client.put(f"/api/enrollments/{enrollment_id}/grades",
               json={"termId": ids["q1"],
                     "entries": [
                         {"gradeCategoryId": ids["cats"]["commitment"], "score": 40},
                         {"gradeCategoryId": ids["cats"]["final_exam"], "score": 60},
                     ]},
               headers=_h(admin_tok))
    _complete_all_lessons(client, stu, ids["course"]["id"])
    r = client.get("/api/certificates/mine", headers=_h(stu))
    first_id = r.get_json()[0]["id"]
    # Another triggering write shouldn't create a second cert.
    client.put(f"/api/enrollments/{enrollment_id}/grades",
               json={"termId": ids["q1"],
                     "entries": [
                         {"gradeCategoryId": ids["cats"]["commitment"], "score": 40}
                     ]},
               headers=_h(admin_tok))
    r = client.get("/api/certificates/mine", headers=_h(stu))
    body = r.get_json()
    assert len(body) == 1
    assert body[0]["id"] == first_id


# ---------------------------------------------------------------------------
# Public verify
# ---------------------------------------------------------------------------
def test_public_verify_returns_limited_fields(client):
    admin_tok = _login_admin(client)
    ids = _bootstrap_full(client, admin_tok)
    r = _register(client, email="v@t.local", role="student", name="Vera Verify")
    sid = r.get_json()["user"]["id"]
    client.put(f"/api/users/{sid}/class",
               json={"classId": ids["class9a"]}, headers=_h(admin_tok))
    stu = _login(client, email="v@t.local", password="password12")
    enrollment_id = client.get("/api/enrollments/mine",
                                headers=_h(stu)).get_json()[0]["id"]
    client.put(f"/api/enrollments/{enrollment_id}/grades",
               json={"termId": ids["q1"],
                     "entries": [
                         {"gradeCategoryId": ids["cats"]["commitment"], "score": 40},
                         {"gradeCategoryId": ids["cats"]["final_exam"], "score": 60},
                     ]},
               headers=_h(admin_tok))
    _complete_all_lessons(client, stu, ids["course"]["id"])
    cert_num = client.get("/api/certificates/mine",
                          headers=_h(stu)).get_json()[0]["certificateNumber"]

    # Anonymous verify.
    client.delete_cookie("lms_session")
    r = client.get(f"/api/verify/{cert_num}")
    assert r.status_code == 200
    body = r.get_json()
    assert body["certificateNumber"] == cert_num
    assert body["studentName"] == "Vera Verify"
    assert body["courseTitle"] == "Alg1"
    assert body["revoked"] is False
    # Should NOT leak grade or enrollment fields.
    assert "cachedPercent" not in body
    assert "enrollmentId" not in body


def test_public_verify_bad_number_404(client):
    r = client.get("/api/verify/LMS-2026-DEADBEEF")
    assert r.status_code == 404


def test_revoke_shows_up_on_verify(client):
    admin_tok = _login_admin(client)
    ids = _bootstrap_full(client, admin_tok)
    r = _register(client, email="rv@t.local", role="student")
    sid = r.get_json()["user"]["id"]
    client.put(f"/api/users/{sid}/class",
               json={"classId": ids["class9a"]}, headers=_h(admin_tok))
    stu = _login(client, email="rv@t.local", password="password12")
    enrollment_id = client.get("/api/enrollments/mine",
                                headers=_h(stu)).get_json()[0]["id"]
    client.put(f"/api/enrollments/{enrollment_id}/grades",
               json={"termId": ids["q1"],
                     "entries": [
                         {"gradeCategoryId": ids["cats"]["commitment"], "score": 40},
                         {"gradeCategoryId": ids["cats"]["final_exam"], "score": 60},
                     ]},
               headers=_h(admin_tok))
    _complete_all_lessons(client, stu, ids["course"]["id"])
    cert = client.get("/api/certificates/mine", headers=_h(stu)).get_json()[0]

    r = client.post(f"/api/certificates/{cert['id']}/revoke",
                    json={"reason": "issued in error"}, headers=_h(admin_tok))
    assert r.status_code == 200

    client.delete_cookie("lms_session")
    r = client.get(f"/api/verify/{cert['certificateNumber']}")
    body = r.get_json()
    assert body["revoked"] is True
    assert body["revokedReason"] == "issued in error"


# ---------------------------------------------------------------------------
# Trust-core negatives
# ---------------------------------------------------------------------------
def test_non_admin_cannot_revoke(client):
    admin_tok = _login_admin(client)
    ids = _bootstrap_full(client, admin_tok)
    r = _register(client, email="s@t.local", role="student")
    sid = r.get_json()["user"]["id"]
    client.put(f"/api/users/{sid}/class",
               json={"classId": ids["class9a"]}, headers=_h(admin_tok))
    stu = _login(client, email="s@t.local", password="password12")
    enrollment_id = client.get("/api/enrollments/mine",
                                headers=_h(stu)).get_json()[0]["id"]
    client.put(f"/api/enrollments/{enrollment_id}/grades",
               json={"termId": ids["q1"],
                     "entries": [
                         {"gradeCategoryId": ids["cats"]["commitment"], "score": 40},
                         {"gradeCategoryId": ids["cats"]["final_exam"], "score": 60},
                     ]},
               headers=_h(admin_tok))
    _complete_all_lessons(client, stu, ids["course"]["id"])
    cert = client.get("/api/certificates/mine", headers=_h(stu)).get_json()[0]

    r = client.post(f"/api/certificates/{cert['id']}/revoke",
                    json={"reason": "hah"}, headers=_h(stu))
    assert r.status_code == 403


def test_student_cannot_view_others_cert(client):
    admin_tok = _login_admin(client)
    ids = _bootstrap_full(client, admin_tok)
    # A completes a course.
    r = _register(client, email="a1@t.local", role="student")
    sid_a = r.get_json()["user"]["id"]
    client.put(f"/api/users/{sid_a}/class",
               json={"classId": ids["class9a"]}, headers=_h(admin_tok))
    a_tok = _login(client, email="a1@t.local", password="password12")
    en_a = client.get("/api/enrollments/mine", headers=_h(a_tok)).get_json()[0]["id"]
    client.put(f"/api/enrollments/{en_a}/grades",
               json={"termId": ids["q1"],
                     "entries": [
                         {"gradeCategoryId": ids["cats"]["commitment"], "score": 40},
                         {"gradeCategoryId": ids["cats"]["final_exam"], "score": 60},
                     ]},
               headers=_h(admin_tok))
    _complete_all_lessons(client, a_tok, ids["course"]["id"])
    cert = client.get("/api/certificates/mine", headers=_h(a_tok)).get_json()[0]

    # B tries to view A's cert.
    r = _register(client, email="b1@t.local", role="student")
    b_tok = _login(client, email="b1@t.local", password="password12")
    r = client.get(f"/api/certificates/{cert['id']}", headers=_h(b_tok))
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# PDF renders (byte length sanity)
# ---------------------------------------------------------------------------
def test_pdf_renders_bytes(client):
    admin_tok = _login_admin(client)
    ids = _bootstrap_full(client, admin_tok)
    r = _register(client, email="p@t.local", role="student", name="P DF")
    sid = r.get_json()["user"]["id"]
    client.put(f"/api/users/{sid}/class",
               json={"classId": ids["class9a"]}, headers=_h(admin_tok))
    stu = _login(client, email="p@t.local", password="password12")
    en = client.get("/api/enrollments/mine", headers=_h(stu)).get_json()[0]["id"]
    client.put(f"/api/enrollments/{en}/grades",
               json={"termId": ids["q1"],
                     "entries": [
                         {"gradeCategoryId": ids["cats"]["commitment"], "score": 40},
                         {"gradeCategoryId": ids["cats"]["final_exam"], "score": 60},
                     ]},
               headers=_h(admin_tok))
    _complete_all_lessons(client, stu, ids["course"]["id"])
    cert = client.get("/api/certificates/mine", headers=_h(stu)).get_json()[0]

    r = client.get(f"/api/certificates/{cert['id']}/pdf", headers=_h(stu))
    assert r.status_code == 200
    assert r.headers["Content-Type"].startswith("application/pdf")
    assert len(r.data) > 1000  # non-trivial PDF
    assert r.data[:4] == b"%PDF"


# ---------------------------------------------------------------------------
# Course delete guard
# ---------------------------------------------------------------------------
def test_course_delete_refused_with_active_cert(client):
    admin_tok = _login_admin(client)
    ids = _bootstrap_full(client, admin_tok)
    r = _register(client, email="d1@t.local", role="student")
    sid = r.get_json()["user"]["id"]
    client.put(f"/api/users/{sid}/class",
               json={"classId": ids["class9a"]}, headers=_h(admin_tok))
    stu = _login(client, email="d1@t.local", password="password12")
    en = client.get("/api/enrollments/mine", headers=_h(stu)).get_json()[0]["id"]
    client.put(f"/api/enrollments/{en}/grades",
               json={"termId": ids["q1"],
                     "entries": [
                         {"gradeCategoryId": ids["cats"]["commitment"], "score": 40},
                         {"gradeCategoryId": ids["cats"]["final_exam"], "score": 60},
                     ]},
               headers=_h(admin_tok))
    _complete_all_lessons(client, stu, ids["course"]["id"])

    # Unassign the student first (so the enrollment 409 doesn't fire first).
    client.delete(f"/api/users/{sid}/class", headers=_h(admin_tok))
    r = client.delete(f"/api/courses/{ids['course']['id']}", headers=_h(admin_tok))
    assert r.status_code == 409
    assert "certificate" in r.get_json()["error"].lower()
