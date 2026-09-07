"""School hierarchy — sections, grades, classes, placement, electives.

content gate, uploads, and every trust-core (Rule #6) negative.

Runs against an isolated SQLite DB per test.

Originally Phase 2.
"""
from __future__ import annotations

from tests.conftest import register_user as _register

import io


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _login(client, *, email, password):
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.data
    return r.get_json()["sessionToken"]


def _h(tok):
    return {"X-Session-Token": tok}


def _login_admin(client):
    return _login(client, email="admin@t.local", password="adminpass1")


def _bootstrap_school(client, admin_tok):
    """Create Elementary/Middle/High sections, Grade 9 under High, and
    class 9-A. Returns dict with ids."""
    h = _h(admin_tok)
    r = client.post("/api/sections", json={"name": "High", "orderIndex": 2}, headers=h)
    assert r.status_code == 201, r.data
    high_id = r.get_json()["id"]
    r = client.post(
        "/api/grades",
        json={"name": "Grade 9", "sectionId": high_id, "orderIndex": 9},
        headers=h,
    )
    assert r.status_code == 201, r.data
    g9 = r.get_json()["id"]
    r = client.post("/api/classes", json={"name": "9-A", "gradeId": g9}, headers=h)
    assert r.status_code == 201, r.data
    class_9a = r.get_json()["id"]
    return {"high": high_id, "g9": g9, "class9a": class_9a}


def _make_course(client, admin_tok, *, title, grade_id, elective_group=None, category="math"):
    r = client.post(
        "/api/courses",
        json={
            "title": title,
            "gradeId": grade_id,
            "electiveGroup": elective_group,
            "category": category,
        },
        headers=_h(admin_tok),
    )
    assert r.status_code == 201, r.data
    course = r.get_json()
    # Add a module + a text lesson so the course can be published if needed.
    r = client.post(
        f"/api/courses/{course['id']}/modules",
        json={"title": "M1"},
        headers=_h(admin_tok),
    )
    module_id = r.get_json()["id"]
    r = client.post(
        f"/api/modules/{module_id}/lessons",
        json={"title": "L1", "type": "text", "contentText": f"secret-for-{title}"},
        headers=_h(admin_tok),
    )
    assert r.status_code == 201, r.data
    r = client.post(
        f"/api/courses/{course['id']}/publish",
        headers=_h(admin_tok),
    )
    assert r.status_code == 200, r.data
    return course


# ---------------------------------------------------------------------------
# Auto-enroll on placement (happy path)
# ---------------------------------------------------------------------------
def test_placing_student_auto_enrolls_mandatory_courses(client):
    admin_tok = _login_admin(client)
    ids = _bootstrap_school(client, admin_tok)
    eng = _make_course(client, admin_tok, title="English 9", grade_id=ids["g9"], category="english")
    alg = _make_course(client, admin_tok, title="Algebra 1", grade_id=ids["g9"], category="math")
    # Two electives in a 'language' group.
    fr = _make_course(client, admin_tok, title="French I", grade_id=ids["g9"], elective_group="language", category="languages")
    de = _make_course(client, admin_tok, title="German I", grade_id=ids["g9"], elective_group="language", category="languages")

    # Register a fresh student.
    r = _register(client, email="stu@t.local", role="student", name="Amira")
    student_id = r.get_json()["user"]["id"]

    # Admin places into 9-A.
    r = client.put(
        f"/api/users/{student_id}/class",
        json={"classId": ids["class9a"]},
        headers=_h(admin_tok),
    )
    assert r.status_code == 200, r.data
    assert r.get_json()["willAutoEnroll"] == 2  # 2 mandatory courses

    # Log in as the student, check enrollments/mine.
    stu_tok = _login(client, email="stu@t.local", password="password12")
    r = client.get("/api/enrollments/mine", headers=_h(stu_tok))
    assert r.status_code == 200
    course_ids = {e["courseId"] for e in r.get_json()}
    assert eng["id"] in course_ids and alg["id"] in course_ids
    # No electives yet.
    assert fr["id"] not in course_ids
    assert de["id"] not in course_ids


def test_pending_electives_surface(client):
    admin_tok = _login_admin(client)
    ids = _bootstrap_school(client, admin_tok)
    _make_course(client, admin_tok, title="English 9", grade_id=ids["g9"], category="english")
    _make_course(client, admin_tok, title="French I", grade_id=ids["g9"], elective_group="language", category="languages")
    _make_course(client, admin_tok, title="German I", grade_id=ids["g9"], elective_group="language", category="languages")

    r = _register(client, email="stu2@t.local", role="student", name="B")
    student_id = r.get_json()["user"]["id"]
    client.put(f"/api/users/{student_id}/class", json={"classId": ids["class9a"]}, headers=_h(admin_tok))

    r = client.get(f"/api/users/{student_id}/electives/pending", headers=_h(admin_tok))
    assert r.status_code == 200
    pending = r.get_json()
    assert len(pending) == 1
    assert pending[0]["group"] == "language"
    assert len(pending[0]["options"]) == 2


def test_pick_elective_creates_enrollment_and_switching_soft_drops(client):
    admin_tok = _login_admin(client)
    ids = _bootstrap_school(client, admin_tok)
    fr = _make_course(client, admin_tok, title="French I", grade_id=ids["g9"], elective_group="language", category="languages")
    de = _make_course(client, admin_tok, title="German I", grade_id=ids["g9"], elective_group="language", category="languages")

    r = _register(client, email="stu3@t.local", role="student", name="C")
    student_id = r.get_json()["user"]["id"]
    client.put(f"/api/users/{student_id}/class", json={"classId": ids["class9a"]}, headers=_h(admin_tok))

    # Pick French.
    r = client.put(
        f"/api/users/{student_id}/electives/language",
        json={"courseId": fr["id"]},
        headers=_h(admin_tok),
    )
    assert r.status_code == 201, r.data

    # Pick French again — idempotent 200 (same course).
    r = client.put(
        f"/api/users/{student_id}/electives/language",
        json={"courseId": fr["id"]},
        headers=_h(admin_tok),
    )
    assert r.status_code == 200

    # Switch to German — French soft-dropped.
    r = client.put(
        f"/api/users/{student_id}/electives/language",
        json={"courseId": de["id"]},
        headers=_h(admin_tok),
    )
    assert r.status_code == 201

    stu_tok = _login(client, email="stu3@t.local", password="password12")
    r = client.get("/api/enrollments/mine", headers=_h(stu_tok))
    # Only ACTIVE / COMPLETED enrollments visible via the list is fine to include dropped;
    # verify the active language pick is German.
    active_lang = [e for e in r.get_json() if e["status"] == "active" and e["courseId"] in (fr["id"], de["id"])]
    assert len(active_lang) == 1
    assert active_lang[0]["courseId"] == de["id"]


# ---------------------------------------------------------------------------
# Content gate
# ---------------------------------------------------------------------------
def test_enrolled_student_can_read_lesson_content(client):
    admin_tok = _login_admin(client)
    ids = _bootstrap_school(client, admin_tok)
    _make_course(client, admin_tok, title="Algebra 1", grade_id=ids["g9"], category="math")
    r = _register(client, email="s1@t.local", role="student", name="S1")
    sid = r.get_json()["user"]["id"]
    client.put(f"/api/users/{sid}/class", json={"classId": ids["class9a"]}, headers=_h(admin_tok))

    stu_tok = _login(client, email="s1@t.local", password="password12")

    # Find the lesson via the course tree.
    r = client.get("/api/courses", headers=_h(stu_tok))
    assert r.status_code == 200
    course_id = r.get_json()[0]["id"]
    r = client.get(f"/api/courses/{course_id}", headers=_h(stu_tok))
    body = r.get_json()
    lesson = body["modules"][0]["lessons"][0]
    assert lesson["previewLocked"] is False, "Enrolled student should see unlocked"

    # Fetch via single-lesson endpoint.
    r = client.get(f"/api/lessons/{lesson['id']}", headers=_h(stu_tok))
    assert r.status_code == 200
    assert "secret-for-Algebra 1" == r.get_json()["contentText"]


def test_non_enrolled_student_gets_403_on_lesson(client):
    admin_tok = _login_admin(client)
    ids = _bootstrap_school(client, admin_tok)
    course = _make_course(client, admin_tok, title="Algebra 1", grade_id=ids["g9"], category="math")
    # Find the lesson id as admin.
    r = client.get(f"/api/courses/{course['id']}", headers=_h(admin_tok))
    lesson_id = r.get_json()["modules"][0]["lessons"][0]["id"]

    # Different student, never placed.
    r = _register(client, email="orph@t.local", role="student", name="O")
    orph_tok = r.get_json()["sessionToken"]
    client.delete_cookie("lms_session")
    orph_tok = _login(client, email="orph@t.local", password="password12")

    r = client.get(f"/api/lessons/{lesson_id}", headers=_h(orph_tok))
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# Trust-core negatives
# ---------------------------------------------------------------------------
def test_student_cannot_self_enroll_or_pick_own_elective(client):
    admin_tok = _login_admin(client)
    ids = _bootstrap_school(client, admin_tok)
    course = _make_course(client, admin_tok, title="X", grade_id=ids["g9"], category="math")
    fr = _make_course(client, admin_tok, title="French", grade_id=ids["g9"], elective_group="language", category="languages")

    r = _register(client, email="stu4@t.local", role="student")
    sid = r.get_json()["user"]["id"]
    stu_tok = _login(client, email="stu4@t.local", password="password12")

    # No self-placement.
    r = client.put(f"/api/users/{sid}/class", json={"classId": ids["class9a"]}, headers=_h(stu_tok))
    assert r.status_code == 403

    # No self-elective — admin places first, then student tries to pick.
    client.put(f"/api/users/{sid}/class", json={"classId": ids["class9a"]}, headers=_h(admin_tok))
    r = client.put(
        f"/api/users/{sid}/electives/language",
        json={"courseId": fr["id"]},
        headers=_h(stu_tok),
    )
    assert r.status_code == 403

    # No manual enroll.
    r = client.post(
        f"/api/courses/{course['id']}/enrollments",
        json={"studentId": sid},
        headers=_h(stu_tok),
    )
    assert r.status_code == 403


def test_parent_cannot_place_or_pick_elective(client):
    admin_tok = _login_admin(client)
    ids = _bootstrap_school(client, admin_tok)
    fr = _make_course(client, admin_tok, title="French", grade_id=ids["g9"], elective_group="language", category="languages")

    r = _register(client, email="stu5@t.local", role="student")
    sid = r.get_json()["user"]["id"]
    client.put(f"/api/users/{sid}/class", json={"classId": ids["class9a"]}, headers=_h(admin_tok))

    # Phase 6: self-register with role='parent' is refused. Admin creates
    # the account.
    r = client.post(
        "/api/users",
        json={
            "name": "Par", "email": "par@t.local",
            "password": "password12", "role": "parent",
        },
        headers=_h(admin_tok),
    )
    assert r.status_code == 201, r.data
    par_tok = _login(client, email="par@t.local", password="password12")

    r = client.put(
        f"/api/users/{sid}/electives/language",
        json={"courseId": fr["id"]},
        headers=_h(par_tok),
    )
    assert r.status_code == 403


def test_wrong_group_elective_rejected(client):
    admin_tok = _login_admin(client)
    ids = _bootstrap_school(client, admin_tok)
    # science_track courses in Grade 9 — pretend.
    bio = _make_course(
        client, admin_tok, title="Bio", grade_id=ids["g9"], elective_group="science_track", category="science"
    )

    r = _register(client, email="stu6@t.local", role="student")
    sid = r.get_json()["user"]["id"]
    client.put(f"/api/users/{sid}/class", json={"classId": ids["class9a"]}, headers=_h(admin_tok))

    # Try to place Bio into the 'language' group.
    r = client.put(
        f"/api/users/{sid}/electives/language",
        json={"courseId": bio["id"]},
        headers=_h(admin_tok),
    )
    assert r.status_code == 400


def test_one_homeroom_per_teacher_enforced(client):
    admin_tok = _login_admin(client)
    ids = _bootstrap_school(client, admin_tok)
    # Two more classes in the same grade.
    r = client.post("/api/classes", json={"name": "9-B", "gradeId": ids["g9"]}, headers=_h(admin_tok))
    class_9b = r.get_json()["id"]

    r = _register(client, email="t1@t.local", role="instructor")
    t1 = r.get_json()["user"]["id"]

    # Assign t1 as homeroom of 9-A.
    r = client.put(
        f"/api/classes/{ids['class9a']}",
        json={"homeroomTeacherId": t1},
        headers=_h(admin_tok),
    )
    assert r.status_code == 200

    # Try to assign t1 as homeroom of 9-B — must be refused.
    r = client.put(
        f"/api/classes/{class_9b}",
        json={"homeroomTeacherId": t1},
        headers=_h(admin_tok),
    )
    assert r.status_code == 409


# ---------------------------------------------------------------------------
# Cross-grade re-placement swaps the curriculum
# ---------------------------------------------------------------------------
def test_cross_grade_replacement_swaps_enrollments(client):
    admin_tok = _login_admin(client)
    ids = _bootstrap_school(client, admin_tok)
    _make_course(client, admin_tok, title="Alg1", grade_id=ids["g9"], category="math")

    # Add Grade 10 with a class + mandatory course.
    r = client.post("/api/grades", json={"name": "Grade 10", "sectionId": ids["high"]}, headers=_h(admin_tok))
    g10 = r.get_json()["id"]
    r = client.post("/api/classes", json={"name": "10-A", "gradeId": g10}, headers=_h(admin_tok))
    class_10a = r.get_json()["id"]
    _make_course(client, admin_tok, title="Alg2", grade_id=g10, category="math")

    r = _register(client, email="mover@t.local", role="student")
    sid = r.get_json()["user"]["id"]

    # Place in 9-A.
    client.put(f"/api/users/{sid}/class", json={"classId": ids["class9a"]}, headers=_h(admin_tok))

    stu_tok = _login(client, email="mover@t.local", password="password12")
    r = client.get("/api/enrollments/mine", headers=_h(stu_tok))
    active_titles = {e["course"]["title"] for e in r.get_json() if e["status"] == "active"}
    assert active_titles == {"Alg1"}

    # Move to 10-A.
    r = client.put(f"/api/users/{sid}/class", json={"classId": class_10a}, headers=_h(admin_tok))
    assert r.status_code == 200

    r = client.get("/api/enrollments/mine", headers=_h(stu_tok))
    active_titles = {e["course"]["title"] for e in r.get_json() if e["status"] == "active"}
    assert active_titles == {"Alg2"}


# ---------------------------------------------------------------------------
# Uploads
# ---------------------------------------------------------------------------
def test_upload_pdf_and_fetch(client):
    admin_tok = _login_admin(client)
    r = client.post(
        "/api/uploads",
        data={"kind": "pdf", "file": (io.BytesIO(b"%PDF-1.4 fake"), "hello.pdf", "application/pdf")},
        headers=_h(admin_tok),
        content_type="multipart/form-data",
    )
    assert r.status_code == 201, r.data
    url = r.get_json()["url"]
    assert url.startswith("/media/pdfs/")

    # The uploader can read it back.
    r = client.get(url, headers=_h(admin_tok))
    assert r.status_code == 200
    assert r.data.startswith(b"%PDF")


def test_media_refuses_anonymous_readers(client):
    """`/media/<path>` used to be a bare `send_from_directory` with no auth:
    anyone holding a URL — a student's submitted essay included — got a 200.
    UUID filenames are obscurity, not access control."""
    admin_tok = _login_admin(client)
    r = client.post(
        "/api/uploads",
        data={"kind": "pdf", "file": (io.BytesIO(b"%PDF-1.4 secret"), "s.pdf", "application/pdf")},
        headers=_h(admin_tok),
        content_type="multipart/form-data",
    )
    url = r.get_json()["url"]

    client.delete_cookie("lms_session")
    assert client.get(url).status_code == 401


def test_media_refuses_unrelated_signed_in_reader(client):
    """Being signed in is not enough — the file has to be one you own or one
    attached to something you are entitled to see."""
    admin_tok = _login_admin(client)
    r = client.post(
        "/api/uploads",
        data={"kind": "pdf", "file": (io.BytesIO(b"%PDF-1.4 secret"), "s.pdf", "application/pdf")},
        headers=_h(admin_tok),
        content_type="multipart/form-data",
    )
    url = r.get_json()["url"]

    stu_tok = _register(client, email="nosy@t.local", role="student").get_json()["sessionToken"]
    # 404, not 403: a caller who may not read the file must not be able to
    # use this endpoint to learn whether it exists.
    assert client.get(url, headers=_h(stu_tok)).status_code == 404


def test_media_refuses_path_traversal(client):
    admin_tok = _login_admin(client)
    assert client.get("/media/../config.py", headers=_h(admin_tok)).status_code == 404


def test_upload_wrong_mime_rejected(client):
    admin_tok = _login_admin(client)
    r = client.post(
        "/api/uploads",
        data={"kind": "video", "file": (io.BytesIO(b"not a video"), "hello.exe", "application/x-msdownload")},
        headers=_h(admin_tok),
        content_type="multipart/form-data",
    )
    assert r.status_code == 400


def test_student_can_upload_pdf_but_not_video(client):
    tok = _register(client, email="upstu@t.local", role="student").get_json()["sessionToken"]

    r = client.post(
        "/api/uploads",
        data={"kind": "pdf", "file": (io.BytesIO(b"%PDF"), "x.pdf", "application/pdf")},
        headers=_h(tok),
        content_type="multipart/form-data",
    )
    assert r.status_code == 201, r.data

    r = client.post(
        "/api/uploads",
        data={"kind": "video", "file": (io.BytesIO(b"\x00ftypmp42"), "x.mp4", "video/mp4")},
        headers=_h(tok),
        content_type="multipart/form-data",
    )
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# End-of-year promotion + graduation
# ---------------------------------------------------------------------------
def _bootstrap_two_grades(client, admin_tok):
    """Create Grade 9 + Grade 10 under 'High' with a class each."""
    h = _h(admin_tok)
    r = client.post("/api/sections", json={"name": "High", "orderIndex": 2}, headers=h)
    high_id = r.get_json()["id"]
    r = client.post("/api/grades",
                    json={"name": "Grade 9", "sectionId": high_id, "orderIndex": 9},
                    headers=h)
    g9 = r.get_json()["id"]
    r = client.post("/api/grades",
                    json={"name": "Grade 10", "sectionId": high_id, "orderIndex": 10},
                    headers=h)
    g10 = r.get_json()["id"]
    r = client.post("/api/classes", json={"name": "9-A", "gradeId": g9}, headers=h)
    c9a = r.get_json()["id"]
    r = client.post("/api/classes", json={"name": "10-A", "gradeId": g10}, headers=h)
    c10a = r.get_json()["id"]
    return {"g9": g9, "g10": g10, "class9a": c9a, "class10a": c10a}


def test_promote_class_moves_students_and_swaps_curriculum(client):
    admin_tok = _login_admin(client)
    ids = _bootstrap_two_grades(client, admin_tok)
    _make_course(client, admin_tok, title="Alg1", grade_id=ids["g9"], category="math")
    _make_course(client, admin_tok, title="Alg2", grade_id=ids["g10"], category="math")

    # Two students in 9-A.
    r = _register(client, email="p1@t.local", role="student")
    s1 = r.get_json()["user"]["id"]
    client.put(f"/api/users/{s1}/class", json={"classId": ids["class9a"]}, headers=_h(admin_tok))
    r = _register(client, email="p2@t.local", role="student")
    s2 = r.get_json()["user"]["id"]
    client.put(f"/api/users/{s2}/class", json={"classId": ids["class9a"]}, headers=_h(admin_tok))

    r = client.post(
        f"/api/classes/{ids['class9a']}/promote",
        json={"toClassId": ids["class10a"]},
        headers=_h(admin_tok),
    )
    assert r.status_code == 200, r.data
    body = r.get_json()
    assert body["promoted"] == 2
    assert body["heldBack"] == 0

    # Both students now in 10-A with Alg2 enrollment.
    for email in ("p1@t.local", "p2@t.local"):
        tok = _login(client, email=email, password="password12")
        me = client.get("/api/auth/me", headers=_h(tok)).get_json()["user"]
        assert me["className"] == "10-A"
        enrolls = client.get("/api/enrollments/mine", headers=_h(tok)).get_json()
        active_titles = {e["course"]["title"] for e in enrolls if e["status"] == "active"}
        assert active_titles == {"Alg2"}


def test_promote_carries_forward_language_elective(client):
    admin_tok = _login_admin(client)
    ids = _bootstrap_two_grades(client, admin_tok)
    # Grade 9 language electives.
    fr1 = _make_course(client, admin_tok, title="French I",
                       grade_id=ids["g9"], elective_group="language",
                       category="languages")
    _make_course(client, admin_tok, title="German I",
                 grade_id=ids["g9"], elective_group="language",
                 category="languages")
    # Grade 10 language electives — link French II to French I.
    r = client.post(
        "/api/courses",
        json={
            "title": "French II",
            "gradeId": ids["g10"],
            "category": "languages",
            "electiveGroup": "language",
            "succeedsCourseId": fr1["id"],
        },
        headers=_h(admin_tok),
    )
    assert r.status_code == 201, r.data
    # Place a student in 9-A + pick French I.
    r = _register(client, email="carry@t.local", role="student")
    sid = r.get_json()["user"]["id"]
    client.put(f"/api/users/{sid}/class", json={"classId": ids["class9a"]}, headers=_h(admin_tok))
    r = client.put(
        f"/api/users/{sid}/electives/language",
        json={"courseId": fr1["id"]},
        headers=_h(admin_tok),
    )
    assert r.status_code == 201

    # Promote to 10-A.
    r = client.post(
        f"/api/classes/{ids['class9a']}/promote",
        json={"toClassId": ids["class10a"]},
        headers=_h(admin_tok),
    )
    assert r.status_code == 200
    assert r.get_json()["carriedForwardElectives"] == 1

    # Student now enrolled in French II.
    tok = _login(client, email="carry@t.local", password="password12")
    enrolls = client.get("/api/enrollments/mine", headers=_h(tok)).get_json()
    active_titles = {e["course"]["title"] for e in enrolls if e["status"] == "active"}
    assert "French II" in active_titles


def test_promote_refuses_non_adjacent_grade(client):
    admin_tok = _login_admin(client)
    h = _h(admin_tok)
    r = client.post("/api/sections", json={"name": "High"}, headers=h)
    sec = r.get_json()["id"]
    r = client.post("/api/grades", json={"name": "Grade 9", "sectionId": sec, "orderIndex": 9},
                    headers=h)
    g9 = r.get_json()["id"]
    r = client.post("/api/grades", json={"name": "Grade 12", "sectionId": sec, "orderIndex": 12},
                    headers=h)
    g12 = r.get_json()["id"]
    r = client.post("/api/classes", json={"name": "9-A", "gradeId": g9}, headers=h)
    c9a = r.get_json()["id"]
    r = client.post("/api/classes", json={"name": "12-A", "gradeId": g12}, headers=h)
    c12a = r.get_json()["id"]

    r = client.post(
        f"/api/classes/{c9a}/promote",
        json={"toClassId": c12a},
        headers=_h(admin_tok),
    )
    assert r.status_code == 400


def test_graduate_class_marks_students_inactive(client):
    admin_tok = _login_admin(client)
    h = _h(admin_tok)
    r = client.post("/api/sections", json={"name": "High"}, headers=h)
    sec = r.get_json()["id"]
    r = client.post("/api/grades", json={"name": "Grade 12", "sectionId": sec, "orderIndex": 12},
                    headers=h)
    g12 = r.get_json()["id"]
    r = client.post("/api/classes", json={"name": "12-A", "gradeId": g12}, headers=h)
    c12a = r.get_json()["id"]

    r = _register(client, email="grad@t.local", role="student")
    sid = r.get_json()["user"]["id"]
    client.put(f"/api/users/{sid}/class", json={"classId": c12a}, headers=_h(admin_tok))

    r = client.post(f"/api/classes/{c12a}/graduate", json={}, headers=_h(admin_tok))
    assert r.status_code == 200
    assert r.get_json()["graduated"] == 1

    # Old session should be invalidated. New login should also refuse
    # because is_active=False.
    r = client.post(
        "/api/auth/login",
        json={"email": "grad@t.local", "password": "password12"},
    )
    assert r.status_code == 401
