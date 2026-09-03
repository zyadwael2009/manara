"""Phase 3 tests — progress tracking, grading rubric, grade entry,
report card, trust-core negatives.
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
        "utils.permissions", "utils.grading", "utils.quizzes", "utils.certificates",
        "utils.analytics", "utils.attendance", "utils.timetables", "utils.assignments",
        "routes.dashboards", "routes.parents", "routes.attendance", "routes.timetables", "routes.assignments",
        "routes", "routes.auth", "routes.users",
        "routes.sections", "routes.grades", "routes.classes",
        "routes.courses", "routes.modules", "routes.lessons",
        "routes.enrollments", "routes.students",
        "routes.department_leaders", "routes.uploads",
        "routes.progress", "routes.grading_admin",
        "routes.rubrics", "routes.grade_reports",
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
        yield c


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


def _register(client, *, email, password="password12", role="student", name="U"):
    return client.post(
        "/api/auth/register",
        json={"email": email, "password": password, "role": role, "name": name},
    )


def _bootstrap_school(client, admin_tok):
    """Create Elementary/High/Grade 9/9-A, a term-year with Q1 as current."""
    h = _h(admin_tok)
    r = client.post("/api/sections", json={"name": "High", "orderIndex": 2}, headers=h)
    high = r.get_json()["id"]
    r = client.post("/api/grades",
                    json={"name": "Grade 9", "sectionId": high, "orderIndex": 9},
                    headers=h)
    g9 = r.get_json()["id"]
    r = client.post("/api/classes", json={"name": "9-A", "gradeId": g9}, headers=h)
    c9a = r.get_json()["id"]

    # School year + one current term.
    r = client.post("/api/school-years",
                    json={"name": "2025-2026", "isCurrent": True},
                    headers=h)
    year = r.get_json()["id"]
    r = client.post(f"/api/school-years/{year}/terms",
                    json={"name": "Q1", "orderIndex": 0},
                    headers=h)
    q1 = r.get_json()["id"]

    return {"high": high, "g9": g9, "class9a": c9a, "year": year, "q1": q1}


def _seed_categories(client, admin_tok):
    """Create Commitment, Final Exam, Quizzes."""
    h = _h(admin_tok)
    cats = {}
    for slug, name in [
        ("commitment", "Commitment"),
        ("final_exam", "Final Exam"),
        ("quizzes", "Quizzes"),
    ]:
        r = client.post("/api/grade-categories",
                        json={"name": name, "slug": slug},
                        headers=h)
        assert r.status_code == 201, r.data
        cats[slug] = r.get_json()["id"]
    return cats


def _seed_grading_scale(client, admin_tok):
    h = _h(admin_tok)
    # Just enough bands for the tests to exercise letter/GPA lookup.
    bands = [
        (93, 100, "A", 4.00),
        (80, 92, "B", 3.00),
        (70, 79, "C", 2.00),
        (0, 69, "F", 0.00),
    ]
    for mn, mx, letter, gpa in bands:
        r = client.post("/api/grading-scale",
                        json={"minPercent": mn, "maxPercent": mx, "letter": letter,
                              "gpaValue": gpa},
                        headers=h)
        assert r.status_code == 201, r.data


def _make_course(client, admin_tok, *, title, grade_id, category="math"):
    h = _h(admin_tok)
    r = client.post("/api/courses",
                    json={"title": title, "gradeId": grade_id, "category": category},
                    headers=h)
    assert r.status_code == 201, r.data
    course = r.get_json()
    # module + two lessons so progress is meaningful.
    r = client.post(f"/api/courses/{course['id']}/modules",
                    json={"title": "M1"}, headers=h)
    module_id = r.get_json()["id"]
    for i in range(2):
        r = client.post(f"/api/modules/{module_id}/lessons",
                        json={"title": f"L{i+1}", "type": "text",
                              "contentText": f"body-{i+1}"},
                        headers=h)
        assert r.status_code == 201
    client.post(f"/api/courses/{course['id']}/publish", headers=h)
    return course


def _set_standard_rubric(client, admin_tok, course_id, cats):
    """Rubric that sums to 100: Commitment 30, Final Exam 60, Quizzes 10."""
    r = client.put(
        f"/api/courses/{course_id}/rubric",
        json={
            "items": [
                {"gradeCategoryId": cats["commitment"], "maxScore": 30, "orderIndex": 0},
                {"gradeCategoryId": cats["final_exam"], "maxScore": 60, "orderIndex": 1},
                {"gradeCategoryId": cats["quizzes"], "maxScore": 10, "orderIndex": 2},
            ],
        },
        headers=_h(admin_tok),
    )
    assert r.status_code == 200, r.data
    return r.get_json()


# ---------------------------------------------------------------------------
# Progress
# ---------------------------------------------------------------------------
def test_mark_complete_updates_enrollment_progress(client):
    admin_tok = _login_admin(client)
    ids = _bootstrap_school(client, admin_tok)
    _make_course(client, admin_tok, title="Alg1", grade_id=ids["g9"])
    r = _register(client, email="s1@t.local", role="student")
    sid = r.get_json()["user"]["id"]
    client.put(f"/api/users/{sid}/class",
               json={"classId": ids["class9a"]}, headers=_h(admin_tok))

    stu = _login(client, email="s1@t.local", password="password12")
    r = client.get("/api/enrollments/mine", headers=_h(stu))
    enrollment = r.get_json()[0]
    course_id = enrollment["courseId"]

    r = client.get(f"/api/courses/{course_id}", headers=_h(stu))
    lessons = r.get_json()["modules"][0]["lessons"]
    assert len(lessons) == 2

    # Mark the first lesson complete → progress 50%.
    r = client.post(f"/api/lessons/{lessons[0]['id']}/complete", headers=_h(stu))
    assert r.status_code == 200
    r = client.get("/api/enrollments/mine", headers=_h(stu))
    assert r.get_json()[0]["progressPercent"] == 50

    # Second lesson → 100% and status becomes completed.
    r = client.post(f"/api/lessons/{lessons[1]['id']}/complete", headers=_h(stu))
    r = client.get("/api/enrollments/mine", headers=_h(stu))
    assert r.get_json()[0]["progressPercent"] == 100
    assert r.get_json()[0]["status"] == "completed"


def test_non_enrolled_student_cannot_mark_complete(client):
    admin_tok = _login_admin(client)
    ids = _bootstrap_school(client, admin_tok)
    course = _make_course(client, admin_tok, title="Alg1", grade_id=ids["g9"])
    lesson_id = client.get(
        f"/api/courses/{course['id']}", headers=_h(admin_tok)
    ).get_json()["modules"][0]["lessons"][0]["id"]

    r = _register(client, email="orph@t.local", role="student")
    tok = _login(client, email="orph@t.local", password="password12")
    r = client.post(f"/api/lessons/{lesson_id}/complete", headers=_h(tok))
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# Rubric invariant
# ---------------------------------------------------------------------------
def test_rubric_sum_must_be_100(client):
    admin_tok = _login_admin(client)
    ids = _bootstrap_school(client, admin_tok)
    course = _make_course(client, admin_tok, title="Alg1", grade_id=ids["g9"])
    cats = _seed_categories(client, admin_tok)

    # Sum = 90 → 400.
    r = client.put(
        f"/api/courses/{course['id']}/rubric",
        json={"items": [
            {"gradeCategoryId": cats["commitment"], "maxScore": 40},
            {"gradeCategoryId": cats["final_exam"], "maxScore": 50},
        ]},
        headers=_h(admin_tok),
    )
    assert r.status_code == 400
    assert "100" in r.get_json()["error"]


# ---------------------------------------------------------------------------
# Grade entry happy path + cache
# ---------------------------------------------------------------------------
def test_grade_entry_populates_cache_and_report_card(client):
    admin_tok = _login_admin(client)
    ids = _bootstrap_school(client, admin_tok)
    course = _make_course(client, admin_tok, title="Alg1", grade_id=ids["g9"])
    cats = _seed_categories(client, admin_tok)
    _seed_grading_scale(client, admin_tok)
    _set_standard_rubric(client, admin_tok, course["id"], cats)

    r = _register(client, email="s2@t.local", role="student")
    sid = r.get_json()["user"]["id"]
    client.put(f"/api/users/{sid}/class",
               json={"classId": ids["class9a"]}, headers=_h(admin_tok))

    # Get the student's enrollment id.
    stu = _login(client, email="s2@t.local", password="password12")
    enrollment_id = client.get("/api/enrollments/mine",
                                headers=_h(stu)).get_json()[0]["id"]

    # Admin writes grades for the student: Commitment 30/30, Final 54/60 → 84/90 = 93.33% → A.
    r = client.put(
        f"/api/enrollments/{enrollment_id}/grades",
        json={
            "termId": ids["q1"],
            "entries": [
                {"gradeCategoryId": cats["commitment"], "score": 30},
                {"gradeCategoryId": cats["final_exam"], "score": 54},
            ],
        },
        headers=_h(admin_tok),
    )
    assert r.status_code == 200, r.data

    # Student's My Classes now shows the cached percent/letter/GPA.
    row = client.get("/api/enrollments/mine", headers=_h(stu)).get_json()[0]
    assert row["cachedLetter"] == "A"
    assert row["cachedGpa"] == 4.0
    # 84/90 = 93.33% (running average of the graded categories).
    assert abs(row["cachedPercent"] - 93.33) < 0.05

    # Report card for the student.
    r = client.get("/api/reports/mine", headers=_h(stu))
    body = r.get_json()
    assert body["cumulative"]["letter"] == "A"


# ---------------------------------------------------------------------------
# Trust-core negatives
# ---------------------------------------------------------------------------
def test_wrong_teacher_cannot_enter_grades(client):
    admin_tok = _login_admin(client)
    ids = _bootstrap_school(client, admin_tok)
    course = _make_course(client, admin_tok, title="Alg1", grade_id=ids["g9"])
    cats = _seed_categories(client, admin_tok)
    _seed_grading_scale(client, admin_tok)
    _set_standard_rubric(client, admin_tok, course["id"], cats)

    r = _register(client, email="s3@t.local", role="student")
    sid = r.get_json()["user"]["id"]
    client.put(f"/api/users/{sid}/class",
               json={"classId": ids["class9a"]}, headers=_h(admin_tok))

    # Random unrelated teacher — no class-course assignment.
    r = _register(client, email="rand@t.local", role="instructor")
    rand_tok = _login(client, email="rand@t.local", password="password12")

    enrollment_id = client.get(
        "/api/enrollments/mine",
        headers=_h(_login(client, email="s3@t.local", password="password12")),
    ).get_json()[0]["id"]

    r = client.put(
        f"/api/enrollments/{enrollment_id}/grades",
        json={
            "termId": ids["q1"],
            "entries": [{"gradeCategoryId": cats["commitment"], "score": 25}],
        },
        headers=_h(rand_tok),
    )
    assert r.status_code == 403


def test_locked_term_refuses_teacher_edits(client):
    admin_tok = _login_admin(client)
    ids = _bootstrap_school(client, admin_tok)
    course = _make_course(client, admin_tok, title="Alg1", grade_id=ids["g9"])
    cats = _seed_categories(client, admin_tok)
    _seed_grading_scale(client, admin_tok)
    _set_standard_rubric(client, admin_tok, course["id"], cats)

    r = _register(client, email="s4@t.local", role="student")
    sid = r.get_json()["user"]["id"]
    client.put(f"/api/users/{sid}/class",
               json={"classId": ids["class9a"]}, headers=_h(admin_tok))

    # Assign a class-course teacher.
    r = _register(client, email="rivera@t.local", role="instructor")
    riv_id = r.get_json()["user"]["id"]
    r = client.put(f"/api/classes/{ids['class9a']}/courses/{course['id']}/teacher",
                   json={"teacherId": riv_id}, headers=_h(admin_tok))
    assert r.status_code == 200

    # Lock the term.
    r = client.post(f"/api/terms/{ids['q1']}/lock", headers=_h(admin_tok))
    assert r.status_code == 200

    # Rivera tries to grade → 403 (locked).
    riv_tok = _login(client, email="rivera@t.local", password="password12")
    enrollment_id = client.get(
        "/api/enrollments/mine",
        headers=_h(_login(client, email="s4@t.local", password="password12")),
    ).get_json()[0]["id"]
    r = client.put(
        f"/api/enrollments/{enrollment_id}/grades",
        json={"termId": ids["q1"],
              "entries": [{"gradeCategoryId": cats["commitment"], "score": 20}]},
        headers=_h(riv_tok),
    )
    assert r.status_code == 403
    # Admin can still write.
    r = client.put(
        f"/api/enrollments/{enrollment_id}/grades",
        json={"termId": ids["q1"],
              "entries": [{"gradeCategoryId": cats["commitment"], "score": 20}]},
        headers=_h(admin_tok),
    )
    assert r.status_code == 200


def test_student_cannot_read_other_report_card(client):
    admin_tok = _login_admin(client)
    ids = _bootstrap_school(client, admin_tok)
    _make_course(client, admin_tok, title="Alg1", grade_id=ids["g9"])
    _seed_grading_scale(client, admin_tok)

    r = _register(client, email="a@t.local", role="student")
    sid_a = r.get_json()["user"]["id"]
    client.put(f"/api/users/{sid_a}/class",
               json={"classId": ids["class9a"]}, headers=_h(admin_tok))
    r = _register(client, email="b@t.local", role="student")
    _ = r.get_json()["user"]["id"]

    b_tok = _login(client, email="b@t.local", password="password12")
    r = client.get(f"/api/reports/students/{sid_a}", headers=_h(b_tok))
    assert r.status_code == 403


def test_grade_entry_writes_audit_row_on_update(client):
    admin_tok = _login_admin(client)
    ids = _bootstrap_school(client, admin_tok)
    course = _make_course(client, admin_tok, title="Alg1", grade_id=ids["g9"])
    cats = _seed_categories(client, admin_tok)
    _seed_grading_scale(client, admin_tok)
    _set_standard_rubric(client, admin_tok, course["id"], cats)

    r = _register(client, email="s5@t.local", role="student")
    sid = r.get_json()["user"]["id"]
    client.put(f"/api/users/{sid}/class",
               json={"classId": ids["class9a"]}, headers=_h(admin_tok))
    stu = _login(client, email="s5@t.local", password="password12")
    enrollment_id = client.get("/api/enrollments/mine",
                                headers=_h(stu)).get_json()[0]["id"]

    # First write.
    client.put(
        f"/api/enrollments/{enrollment_id}/grades",
        json={"termId": ids["q1"],
              "entries": [{"gradeCategoryId": cats["commitment"], "score": 25}]},
        headers=_h(admin_tok),
    )
    # Update.
    client.put(
        f"/api/enrollments/{enrollment_id}/grades",
        json={"termId": ids["q1"],
              "entries": [{"gradeCategoryId": cats["commitment"], "score": 28,
                           "reason": "recheck"}]},
        headers=_h(admin_tok),
    )
    # Assert the history row exists via a direct DB peek.
    from models import GradeEntry, GradeEntryHistory
    entry = GradeEntry.query.filter_by(enrollment_id=enrollment_id).first()
    hist = GradeEntryHistory.query.filter_by(grade_entry_id=entry.id).all()
    assert len(hist) == 2
    # First row was insert (old_score=None), second was update (old_score=25).
    olds = {h.old_score for h in hist}
    assert None in olds
