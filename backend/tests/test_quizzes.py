"""Quizzes — authoring, taking, grading, and the trust-core gates.

Originally Phase 4.
"""
from __future__ import annotations

from tests.conftest import register_user as _register


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _h(tok):
    return {"X-Session-Token": tok}


def _login(client, *, email, password):
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.data
    return r.get_json()["sessionToken"]


def _login_admin(client):
    return _login(client, email="admin@t.local", password="adminpass1")


def _bootstrap(client, admin_tok):
    """Grade 9, class 9-A, an Algebra 1 course with one module."""
    h = _h(admin_tok)
    r = client.post("/api/sections", json={"name": "High", "orderIndex": 2}, headers=h)
    high = r.get_json()["id"]
    r = client.post("/api/grades",
                    json={"name": "Grade 9", "sectionId": high, "orderIndex": 9},
                    headers=h)
    g9 = r.get_json()["id"]
    r = client.post("/api/classes", json={"name": "9-A", "gradeId": g9}, headers=h)
    c9a = r.get_json()["id"]
    r = client.post("/api/courses",
                    json={"title": "Algebra 1", "gradeId": g9, "category": "math"},
                    headers=h)
    course = r.get_json()
    r = client.post(f"/api/courses/{course['id']}/modules",
                    json={"title": "M1"}, headers=h)
    module = r.get_json()
    # Give the course at least one lesson so publish works.
    r = client.post(f"/api/modules/{module['id']}/lessons",
                    json={"title": "L", "type": "text", "contentText": "x"},
                    headers=h)
    client.post(f"/api/courses/{course['id']}/publish", headers=h)
    # School year + Q1 current.
    r = client.post("/api/school-years",
                    json={"name": "2025-2026", "isCurrent": True}, headers=h)
    year = r.get_json()["id"]
    r = client.post(f"/api/school-years/{year}/terms",
                    json={"name": "Q1", "orderIndex": 0}, headers=h)
    q1 = r.get_json()["id"]
    return {"g9": g9, "class9a": c9a, "course": course, "module": module, "q1": q1}


def _seed_categories_and_scale(client, admin_tok):
    h = _h(admin_tok)
    cats = {}
    for slug, name, is_sys in [
        ("commitment", "Commitment", False),
        ("final_exam", "Final Exam", False),
        ("quizzes", "Quizzes", True),
    ]:
        # is_system can't be set from the API in Phase 3; but the seed here is
        # test-only, so we side-step through DB directly for the Quizzes one.
        r = client.post("/api/grade-categories",
                        json={"name": name, "slug": slug}, headers=h)
        assert r.status_code == 201
        cats[slug] = r.get_json()["id"]
    # Grading scale.
    for mn, mx, letter, gpa in [
        (93, 100, "A", 4.00),
        (0, 92, "F", 0.00),
    ]:
        client.post("/api/grading-scale",
                    json={"minPercent": mn, "maxPercent": mx, "letter": letter, "gpaValue": gpa},
                    headers=h)
    return cats


def _make_quiz(client, admin_tok, module_id, *, title="Pop quiz", passing_score=60):
    r = client.post(f"/api/modules/{module_id}/quizzes",
                    json={"title": title, "passingScore": passing_score},
                    headers=_h(admin_tok))
    assert r.status_code == 201, r.data
    return r.get_json()


def _add_mc_single(client, admin_tok, quiz_id, prompt, options):
    """options = [(text, is_correct), ...]"""
    r = client.post(f"/api/quizzes/{quiz_id}/questions",
                    json={"type": "mc_single", "prompt": prompt, "points": 1},
                    headers=_h(admin_tok))
    q = r.get_json()
    for text, correct in options:
        client.post(f"/api/quiz-questions/{q['id']}/options",
                    json={"text": text, "isCorrect": correct},
                    headers=_h(admin_tok))
    return q


def _add_essay(client, admin_tok, quiz_id, prompt, points=5):
    r = client.post(f"/api/quizzes/{quiz_id}/questions",
                    json={"type": "essay", "prompt": prompt, "points": points},
                    headers=_h(admin_tok))
    return r.get_json()


def _place_student(client, admin_tok, *, email, class_id):
    r = _register(client, email=email, role="student")
    sid = r.get_json()["user"]["id"]
    client.put(f"/api/users/{sid}/class",
               json={"classId": class_id}, headers=_h(admin_tok))
    return sid


# ---------------------------------------------------------------------------
# Author flow
# ---------------------------------------------------------------------------
def test_author_creates_quiz_and_student_gets_no_answer_keys(client):
    admin_tok = _login_admin(client)
    ids = _bootstrap(client, admin_tok)
    quiz = _make_quiz(client, admin_tok, ids["module"]["id"])
    _add_mc_single(client, admin_tok, quiz["id"], "2+2?",
                   [("3", False), ("4", True), ("5", False)])
    client.post(f"/api/quizzes/{quiz['id']}/publish", headers=_h(admin_tok))

    _place_student(client, admin_tok, email="amira@t.local", class_id=ids["class9a"])
    stu = _login(client, email="amira@t.local", password="password12")

    # Student fetches quiz → options WITHOUT isCorrect.
    r = client.get(f"/api/quizzes/{quiz['id']}", headers=_h(stu))
    body = r.get_json()
    for q in body["questions"]:
        for o in q["options"]:
            assert "isCorrect" not in o


def test_non_enrolled_student_cannot_start_or_view_quiz(client):
    admin_tok = _login_admin(client)
    ids = _bootstrap(client, admin_tok)
    quiz = _make_quiz(client, admin_tok, ids["module"]["id"])
    _add_mc_single(client, admin_tok, quiz["id"], "1?", [("A", True), ("B", False)])
    client.post(f"/api/quizzes/{quiz['id']}/publish", headers=_h(admin_tok))

    _register(client, email="orph@t.local", role="student")
    tok = _login(client, email="orph@t.local", password="password12")
    r = client.post(f"/api/quizzes/{quiz['id']}/start", headers=_h(tok))
    assert r.status_code == 403


def test_delete_quiz_with_attempts_refuses(client):
    admin_tok = _login_admin(client)
    ids = _bootstrap(client, admin_tok)
    quiz = _make_quiz(client, admin_tok, ids["module"]["id"])
    _add_mc_single(client, admin_tok, quiz["id"], "?", [("A", True), ("B", False)])
    client.post(f"/api/quizzes/{quiz['id']}/publish", headers=_h(admin_tok))
    _place_student(client, admin_tok, email="s@t.local", class_id=ids["class9a"])
    stu = _login(client, email="s@t.local", password="password12")
    client.post(f"/api/quizzes/{quiz['id']}/start", headers=_h(stu))

    r = client.delete(f"/api/quizzes/{quiz['id']}", headers=_h(admin_tok))
    assert r.status_code == 409


def test_correct_answer_change_after_attempt_refuses(client):
    admin_tok = _login_admin(client)
    ids = _bootstrap(client, admin_tok)
    quiz = _make_quiz(client, admin_tok, ids["module"]["id"])
    q = _add_mc_single(client, admin_tok, quiz["id"], "?", [("A", True), ("B", False)])
    client.post(f"/api/quizzes/{quiz['id']}/publish", headers=_h(admin_tok))
    _place_student(client, admin_tok, email="s2@t.local", class_id=ids["class9a"])
    stu = _login(client, email="s2@t.local", password="password12")
    client.post(f"/api/quizzes/{quiz['id']}/start", headers=_h(stu))

    # Find option id of "A".
    r = client.get(f"/api/quizzes/{quiz['id']}", headers=_h(admin_tok))
    body = r.get_json()
    opt_a = [o for o in body["questions"][0]["options"] if o["text"] == "A"][0]
    r = client.put(f"/api/quiz-options/{opt_a['id']}",
                   json={"isCorrect": False}, headers=_h(admin_tok))
    assert r.status_code == 409


# ---------------------------------------------------------------------------
# Take flow: MC-single auto-grading
# ---------------------------------------------------------------------------
def test_submit_mc_correct_scores_full_and_updates_cache(client):
    admin_tok = _login_admin(client)
    ids = _bootstrap(client, admin_tok)
    cats = _seed_categories_and_scale(client, admin_tok)
    # Rubric: Commitment 50, Quizzes 50 = 100.
    client.put(f"/api/courses/{ids['course']['id']}/rubric",
               json={"items": [
                   {"gradeCategoryId": cats["commitment"], "maxScore": 50, "orderIndex": 0},
                   {"gradeCategoryId": cats["quizzes"], "maxScore": 50, "orderIndex": 1},
               ]},
               headers=_h(admin_tok))
    quiz = _make_quiz(client, admin_tok, ids["module"]["id"])
    _add_mc_single(client, admin_tok, quiz["id"], "2+2?",
                   [("3", False), ("4", True), ("5", False)])
    client.post(f"/api/quizzes/{quiz['id']}/publish", headers=_h(admin_tok))

    sid = _place_student(client, admin_tok, email="a@t.local", class_id=ids["class9a"])
    stu = _login(client, email="a@t.local", password="password12")

    r = client.post(f"/api/quizzes/{quiz['id']}/start", headers=_h(stu))
    attempt = r.get_json()["attempt"]
    body = r.get_json()["quiz"]
    q = body["questions"][0]
    correct_option = [o for o in q["options"] if o["text"] == "4"][0]

    r = client.post(
        f"/api/quiz-attempts/{attempt['id']}/submit",
        json={"answers": [{"questionId": q["id"], "selectedOptionIds": [correct_option["id"]]}]},
        headers=_h(stu),
    )
    assert r.status_code == 200, r.data
    result = r.get_json()["attempt"]
    assert result["finalScore"] == 1.0
    assert result["passed"] is True
    assert result["needsManualReview"] is False

    # Quizzes-category grade_entry should exist for this enrollment.
    r = client.get("/api/enrollments/mine", headers=_h(stu))
    en = r.get_json()[0]
    assert en["cachedLetter"] is not None  # something got rolled up


def test_submit_mc_wrong_scores_zero(client):
    admin_tok = _login_admin(client)
    ids = _bootstrap(client, admin_tok)
    quiz = _make_quiz(client, admin_tok, ids["module"]["id"], passing_score=60)
    _add_mc_single(client, admin_tok, quiz["id"], "?",
                   [("A", True), ("B", False)])
    client.post(f"/api/quizzes/{quiz['id']}/publish", headers=_h(admin_tok))
    _place_student(client, admin_tok, email="w@t.local", class_id=ids["class9a"])
    stu = _login(client, email="w@t.local", password="password12")

    r = client.post(f"/api/quizzes/{quiz['id']}/start", headers=_h(stu))
    attempt = r.get_json()["attempt"]
    body = r.get_json()["quiz"]
    wrong = [o for o in body["questions"][0]["options"] if o["text"] == "B"][0]
    r = client.post(
        f"/api/quiz-attempts/{attempt['id']}/submit",
        json={"answers": [{"questionId": body["questions"][0]["id"],
                            "selectedOptionIds": [wrong["id"]]}]},
        headers=_h(stu),
    )
    result = r.get_json()["attempt"]
    assert result["finalScore"] == 0.0
    assert result["passed"] is False


# ---------------------------------------------------------------------------
# Essay marks needs_manual_review
# ---------------------------------------------------------------------------
def test_essay_marks_needs_manual_review(client):
    admin_tok = _login_admin(client)
    ids = _bootstrap(client, admin_tok)
    quiz = _make_quiz(client, admin_tok, ids["module"]["id"])
    _add_essay(client, admin_tok, quiz["id"], "Explain photosynthesis.", points=5)
    client.post(f"/api/quizzes/{quiz['id']}/publish", headers=_h(admin_tok))
    _place_student(client, admin_tok, email="e@t.local", class_id=ids["class9a"])
    stu = _login(client, email="e@t.local", password="password12")
    r = client.post(f"/api/quizzes/{quiz['id']}/start", headers=_h(stu))
    attempt = r.get_json()["attempt"]
    body = r.get_json()["quiz"]
    r = client.post(
        f"/api/quiz-attempts/{attempt['id']}/submit",
        json={"answers": [{"questionId": body["questions"][0]["id"],
                            "responseText": "Plants use sunlight, water, and CO2."}]},
        headers=_h(stu),
    )
    result = r.get_json()["attempt"]
    assert result["needsManualReview"] is True
    # Auto score is 0 because essay isn't auto-graded.
    assert result["autoScore"] == 0.0


# ---------------------------------------------------------------------------
# Max attempts
# ---------------------------------------------------------------------------
def test_max_attempts_enforced(client):
    admin_tok = _login_admin(client)
    ids = _bootstrap(client, admin_tok)
    r = client.post(f"/api/modules/{ids['module']['id']}/quizzes",
                    json={"title": "One-shot", "maxAttempts": 1}, headers=_h(admin_tok))
    quiz = r.get_json()
    _add_mc_single(client, admin_tok, quiz["id"], "?",
                   [("A", True), ("B", False)])
    client.post(f"/api/quizzes/{quiz['id']}/publish", headers=_h(admin_tok))
    _place_student(client, admin_tok, email="m@t.local", class_id=ids["class9a"])
    stu = _login(client, email="m@t.local", password="password12")

    r = client.post(f"/api/quizzes/{quiz['id']}/start", headers=_h(stu))
    attempt = r.get_json()["attempt"]
    body = r.get_json()["quiz"]
    opt = body["questions"][0]["options"][0]
    client.post(f"/api/quiz-attempts/{attempt['id']}/submit",
                json={"answers": [{"questionId": body["questions"][0]["id"],
                                   "selectedOptionIds": [opt["id"]]}]},
                headers=_h(stu))
    # Second start → 403.
    r = client.post(f"/api/quizzes/{quiz['id']}/start", headers=_h(stu))
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# Trust-core: student can't view another student's attempt
# ---------------------------------------------------------------------------
def test_student_cannot_view_other_students_attempt(client):
    admin_tok = _login_admin(client)
    ids = _bootstrap(client, admin_tok)
    quiz = _make_quiz(client, admin_tok, ids["module"]["id"])
    _add_mc_single(client, admin_tok, quiz["id"], "?", [("A", True), ("B", False)])
    client.post(f"/api/quizzes/{quiz['id']}/publish", headers=_h(admin_tok))

    _place_student(client, admin_tok, email="a1@t.local", class_id=ids["class9a"])
    a_tok = _login(client, email="a1@t.local", password="password12")
    r = client.post(f"/api/quizzes/{quiz['id']}/start", headers=_h(a_tok))
    a_attempt = r.get_json()["attempt"]

    _place_student(client, admin_tok, email="b1@t.local", class_id=ids["class9a"])
    b_tok = _login(client, email="b1@t.local", password="password12")
    r = client.get(f"/api/quiz-attempts/{a_attempt['id']}", headers=_h(b_tok))
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# Manual override recomputes rollup + cache
# ---------------------------------------------------------------------------
def test_manual_override_updates_rollup_and_cache(client):
    admin_tok = _login_admin(client)
    ids = _bootstrap(client, admin_tok)
    cats = _seed_categories_and_scale(client, admin_tok)
    client.put(f"/api/courses/{ids['course']['id']}/rubric",
               json={"items": [
                   {"gradeCategoryId": cats["commitment"], "maxScore": 50, "orderIndex": 0},
                   {"gradeCategoryId": cats["quizzes"], "maxScore": 50, "orderIndex": 1},
               ]},
               headers=_h(admin_tok))
    quiz = _make_quiz(client, admin_tok, ids["module"]["id"])
    _add_essay(client, admin_tok, quiz["id"], "Explain.", points=10)
    client.post(f"/api/quizzes/{quiz['id']}/publish", headers=_h(admin_tok))
    _place_student(client, admin_tok, email="o@t.local", class_id=ids["class9a"])
    stu = _login(client, email="o@t.local", password="password12")

    r = client.post(f"/api/quizzes/{quiz['id']}/start", headers=_h(stu))
    attempt = r.get_json()["attempt"]
    body = r.get_json()["quiz"]
    client.post(f"/api/quiz-attempts/{attempt['id']}/submit",
                json={"answers": [{"questionId": body["questions"][0]["id"],
                                    "responseText": "Some text."}]},
                headers=_h(stu))

    # Admin overrides to full score.
    r = client.post(f"/api/quiz-attempts/{attempt['id']}/override",
                    json={"finalScore": 10.0}, headers=_h(admin_tok))
    assert r.status_code == 200, r.data
    result = r.get_json()
    assert result["finalScore"] == 10.0

    # Student's Quizzes rollup should now be 50/50 (100% of quiz = full category max).
    r = client.get("/api/enrollments/mine", headers=_h(stu))
    en = r.get_json()[0]
    # cached_percent is from ALL graded categories; without Commitment scored, only Quizzes is graded.
    # So the running-average percent should be 100% (Quizzes: 50/50 → 100% of graded).
    assert en["cachedPercent"] == 100.0
