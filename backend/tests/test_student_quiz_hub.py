"""The student Quizzes hub and last-mark decoration on course detail.

Guards two read-only surfaces:
  * `GET /api/quizzes/my` — the top-level quizzes list for the caller's own
    enrollments, with attempt history + best/last projections.
  * `GET /api/courses/<id>` — the module quiz summaries now carry
    myLastPercent/myBestPercent/myAttemptsCount when the caller is a
    student enrolled in the course.

Both are pure projections — no writes, no trust-core touched.

Originally Phase 16.
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


def _bootstrap(client, admin_tok):
    """Grade 9 + class 9-A + a published course (Algebra 1) with one module."""
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
    client.post(f"/api/modules/{module['id']}/lessons",
                json={"title": "L", "type": "text", "contentText": "x"},
                headers=h)
    client.post(f"/api/courses/{course['id']}/publish", headers=h)
    return {"g9": g9, "class9a": c9a, "course": course, "module": module}


def _make_quiz(client, admin_tok, module_id, *, title="Pop quiz",
               passing_score=60, publish=True, max_attempts=None):
    body = {"title": title, "passingScore": passing_score}
    if max_attempts is not None:
        body["maxAttempts"] = max_attempts
    r = client.post(f"/api/modules/{module_id}/quizzes",
                    json=body, headers=_h(admin_tok))
    assert r.status_code == 201, r.data
    quiz = r.get_json()
    # One trivial mc_single question.
    r = client.post(f"/api/quizzes/{quiz['id']}/questions",
                    json={"type": "mc_single", "prompt": "1+1?", "points": 1},
                    headers=_h(admin_tok))
    q = r.get_json()
    client.post(f"/api/quiz-questions/{q['id']}/options",
                json={"text": "1", "isCorrect": False}, headers=_h(admin_tok))
    client.post(f"/api/quiz-questions/{q['id']}/options",
                json={"text": "2", "isCorrect": True}, headers=_h(admin_tok))
    if publish:
        r2 = client.post(f"/api/quizzes/{quiz['id']}/publish", headers=_h(admin_tok))
        assert r2.status_code == 200, r2.data
    return quiz


def _place_student(client, admin_tok, *, email, class_id):
    r = _register(client, email=email, role="student")
    sid = r.get_json()["user"]["id"]
    client.put(f"/api/users/{sid}/class",
               json={"classId": class_id}, headers=_h(admin_tok))
    return sid


def _take_quiz(client, stu_tok, quiz_id, *, correct: bool):
    """Start the quiz, submit an answer (correct or wrong), return the attempt."""
    r = client.post(f"/api/quizzes/{quiz_id}/start", headers=_h(stu_tok))
    assert r.status_code in (200, 201), r.data
    env = r.get_json()
    attempt = env["attempt"]
    q = env["quiz"]["questions"][0]
    opt = [o for o in q["options"] if o["text"] == ("2" if correct else "1")][0]
    r = client.post(
        f"/api/quiz-attempts/{attempt['id']}/submit",
        json={"answers": [{"questionId": q["id"], "selectedOptionIds": [opt["id"]]}]},
        headers=_h(stu_tok),
    )
    assert r.status_code == 200, r.data
    return r.get_json()["attempt"]


# ---------------------------------------------------------------------------
# /api/quizzes/my
# ---------------------------------------------------------------------------
def test_my_quizzes_lists_published_quizzes_in_my_enrollments(client):
    admin = _login_admin(client)
    ids = _bootstrap(client, admin)
    quiz = _make_quiz(client, admin, ids["module"]["id"], title="Q1")
    _place_student(client, admin, email="amira@t.local", class_id=ids["class9a"])
    stu = _login(client, email="amira@t.local", password="password12")

    r = client.get("/api/quizzes/my", headers=_h(stu))
    assert r.status_code == 200
    body = r.get_json()
    titles = [row["quiz"]["title"] for row in body]
    assert "Q1" in titles
    row = [r for r in body if r["quiz"]["title"] == "Q1"][0]
    assert row["course"]["title"] == "Algebra 1"
    assert row["quiz"]["moduleTitle"] == "M1"
    # Fresh — no attempts yet.
    assert row["attemptsCount"] == 0
    assert row["bestPercent"] is None
    assert row["lastPercent"] is None
    assert row["passed"] is False


def test_my_quizzes_excludes_unpublished(client):
    admin = _login_admin(client)
    ids = _bootstrap(client, admin)
    _make_quiz(client, admin, ids["module"]["id"], title="draft-only", publish=False)
    _make_quiz(client, admin, ids["module"]["id"], title="live")
    _place_student(client, admin, email="s@t.local", class_id=ids["class9a"])
    stu = _login(client, email="s@t.local", password="password12")

    r = client.get("/api/quizzes/my", headers=_h(stu))
    titles = [row["quiz"]["title"] for row in r.get_json()]
    assert "live" in titles
    assert "draft-only" not in titles


def test_my_quizzes_scoped_to_my_enrollments(client):
    admin = _login_admin(client)
    ids = _bootstrap(client, admin)
    _make_quiz(client, admin, ids["module"]["id"])
    # A student registered but NOT placed in any class → no enrollments.
    _register(client, email="orph@t.local", role="student")
    tok = _login(client, email="orph@t.local", password="password12")

    r = client.get("/api/quizzes/my", headers=_h(tok))
    assert r.status_code == 200
    assert r.get_json() == []


def test_my_quizzes_reports_best_last_and_passed_across_attempts(client):
    admin = _login_admin(client)
    ids = _bootstrap(client, admin)
    quiz = _make_quiz(client, admin, ids["module"]["id"],
                      title="Retakes", passing_score=100, max_attempts=3)
    _place_student(client, admin, email="a@t.local", class_id=ids["class9a"])
    stu = _login(client, email="a@t.local", password="password12")

    # 3 attempts: wrong, right, wrong. best = 100%, last = 0%, passed = True.
    _take_quiz(client, stu, quiz["id"], correct=False)
    _take_quiz(client, stu, quiz["id"], correct=True)
    _take_quiz(client, stu, quiz["id"], correct=False)

    r = client.get("/api/quizzes/my", headers=_h(stu))
    row = [r for r in r.get_json() if r["quiz"]["title"] == "Retakes"][0]
    assert row["attemptsCount"] == 3
    assert row["bestPercent"] == 100.0
    assert row["lastPercent"] == 0.0
    assert row["lastAttemptNumber"] == 3
    assert row["passed"] is True
    assert row["canRetake"] is False   # hit max_attempts
    # attempt history is included, ordered by attempt_number.
    assert [a["attemptNumber"] for a in row["attempts"]] == [1, 2, 3]


def test_my_quizzes_never_leaks_other_students_attempts(client):
    admin = _login_admin(client)
    ids = _bootstrap(client, admin)
    quiz = _make_quiz(client, admin, ids["module"]["id"], title="Shared")
    _place_student(client, admin, email="a@t.local", class_id=ids["class9a"])
    _place_student(client, admin, email="b@t.local", class_id=ids["class9a"])
    a = _login(client, email="a@t.local", password="password12")
    b = _login(client, email="b@t.local", password="password12")

    _take_quiz(client, a, quiz["id"], correct=True)

    # B looks at their own hub — sees the quiz but zero attempts, no leakage.
    body = client.get("/api/quizzes/my", headers=_h(b)).get_json()
    row = [r for r in body if r["quiz"]["title"] == "Shared"][0]
    assert row["attemptsCount"] == 0
    assert row["bestPercent"] is None
    assert row["attempts"] == []


def test_my_quizzes_empty_for_teacher_or_admin(client):
    admin = _login_admin(client)
    ids = _bootstrap(client, admin)
    _make_quiz(client, admin, ids["module"]["id"])
    # Admin has no enrollments.
    r = client.get("/api/quizzes/my", headers=_h(admin))
    assert r.status_code == 200
    assert r.get_json() == []

    # A teacher with no enrollments.
    _register(client, email="t@t.local", role="instructor")
    t = _login(client, email="t@t.local", password="password12")
    r = client.get("/api/quizzes/my", headers=_h(t))
    assert r.status_code == 200
    assert r.get_json() == []


# ---------------------------------------------------------------------------
# Course-detail decoration
# ---------------------------------------------------------------------------
def test_course_detail_decorates_quiz_summaries_for_the_student(client):
    admin = _login_admin(client)
    ids = _bootstrap(client, admin)
    quiz = _make_quiz(client, admin, ids["module"]["id"], title="Q", passing_score=100)
    _place_student(client, admin, email="s@t.local", class_id=ids["class9a"])
    stu = _login(client, email="s@t.local", password="password12")

    # Before any attempt: fields present but null / zero.
    r = client.get(f"/api/courses/{ids['course']['id']}", headers=_h(stu))
    body = r.get_json()
    qs = body["modules"][0]["quizzes"][0]
    assert qs["myAttemptsCount"] == 0
    assert qs["myBestPercent"] is None
    assert qs["myLastPercent"] is None
    assert qs["myPassed"] is False

    _take_quiz(client, stu, quiz["id"], correct=True)

    r = client.get(f"/api/courses/{ids['course']['id']}", headers=_h(stu))
    qs = r.get_json()["modules"][0]["quizzes"][0]
    assert qs["myAttemptsCount"] == 1
    assert qs["myBestPercent"] == 100.0
    assert qs["myLastPercent"] == 100.0
    assert qs["myPassed"] is True


def test_course_detail_no_decoration_for_admin_or_teacher(client):
    admin = _login_admin(client)
    ids = _bootstrap(client, admin)
    _make_quiz(client, admin, ids["module"]["id"])
    r = client.get(f"/api/courses/{ids['course']['id']}", headers=_h(admin))
    qs = r.get_json()["modules"][0]["quizzes"][0]
    # Non-student callers never get the decoration keys.
    assert "myAttemptsCount" not in qs
    assert "myBestPercent" not in qs
    assert "myLastPercent" not in qs
    assert "myPassed" not in qs
