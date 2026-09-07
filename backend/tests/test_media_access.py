"""Who can read an uploaded file.

`/media/<path>` used to be a bare `send_from_directory` with no auth of any
kind: a fresh client with no session got a 200 on a student's submitted
essay. The only thing standing between an outsider and the file was the UUID
in the URL — and those URLs travel through API responses, browser history and
`Referer` headers, and never expire.

The rules under test live in `utils/media.py`: admin or uploader always; then
whatever permission governs the row that *references* the file.
"""
from __future__ import annotations

import io

from tests.conftest import register_user as _register


def _h(tok):
    return {"X-Session-Token": tok}


def _login_admin(client):
    return client.post(
        "/api/auth/login", json={"email": "admin@t.local", "password": "adminpass1"},
    ).get_json()["sessionToken"]


def _upload(client, tok, *, kind="pdf", content=b"%PDF-1.4 body"):
    ext = {"pdf": "pdf", "image": "png", "video": "mp4"}[kind]
    mime = {"pdf": "application/pdf", "image": "image/png", "video": "video/mp4"}[kind]
    r = client.post(
        "/api/uploads",
        data={"kind": kind, "file": (io.BytesIO(content), f"f.{ext}", mime)},
        headers=_h(tok),
        content_type="multipart/form-data",
    )
    assert r.status_code == 201, r.data
    return r.get_json()["url"]


# =============================================================================
# The bare minimum
# =============================================================================
def test_anonymous_reader_is_refused(client):
    admin_tok = _login_admin(client)
    url = _upload(client, admin_tok)
    # Logging in also set a session cookie on this client; drop it so the
    # request really is anonymous.
    client.delete_cookie("lms_session")
    assert client.get(url).status_code == 401


def test_uploader_can_read_their_own_file(client):
    tok = _register(client, email="s@t.local", role="student").get_json()["sessionToken"]
    url = _upload(client, tok)
    r = client.get(url, headers=_h(tok))
    assert r.status_code == 200
    assert r.data.startswith(b"%PDF")


def test_admin_can_read_anything(client):
    tok = _register(client, email="s@t.local", role="student").get_json()["sessionToken"]
    url = _upload(client, tok)
    assert client.get(url, headers=_h(_login_admin(client))).status_code == 200


def test_unrelated_signed_in_user_is_refused(client):
    owner = _register(client, email="s@t.local", role="student").get_json()["sessionToken"]
    url = _upload(client, owner)

    nosy = _register(client, email="nosy@t.local", role="student").get_json()["sessionToken"]
    # 404 rather than 403: a caller who may not read the file should not be
    # able to use this endpoint to confirm the file exists.
    assert client.get(url, headers=_h(nosy)).status_code == 404


def test_unknown_path_is_a_404_not_a_500(client):
    admin_tok = _login_admin(client)
    assert client.get("/media/pdfs/nope.pdf", headers=_h(admin_tok)).status_code == 404


def test_path_traversal_is_refused(client):
    admin_tok = _login_admin(client)
    for attempt in ("/media/../config.py", "/media/../../models.py"):
        assert client.get(attempt, headers=_h(admin_tok)).status_code == 404


# =============================================================================
# Reference-derived permission
# =============================================================================
def test_lesson_media_is_readable_by_an_enrolled_student(client):
    """Attaching a file to a lesson is what makes it readable by the class —
    the permission comes from the lesson, not from the file."""
    admin_tok = _login_admin(client)
    h = _h(admin_tok)

    section = client.post("/api/sections", json={"name": "Upper"}, headers=h).get_json()
    grade = client.post(
        "/api/grades", json={"name": "G9", "sectionId": section["id"]}, headers=h,
    ).get_json()
    klass = client.post(
        "/api/classes", json={"name": "9-A", "gradeId": grade["id"]}, headers=h,
    ).get_json()
    course = client.post(
        "/api/courses",
        json={"title": "Math", "gradeId": grade["id"], "category": "math"},
        headers=h,
    ).get_json()
    module = client.post(
        f"/api/courses/{course['id']}/modules", json={"title": "M1"}, headers=h,
    ).get_json()

    url = _upload(client, admin_tok)
    client.post(
        f"/api/modules/{module['id']}/lessons",
        json={"title": "L1", "type": "pdf", "contentUrl": url},
        headers=h,
    )
    client.post(f"/api/courses/{course['id']}/publish", headers=h)

    student = _register(client, email="amira@t.local", role="student").get_json()
    client.put(
        f"/api/users/{student['user']['id']}/class",
        json={"classId": klass["id"]},
        headers=h,
    )

    enrolled = _h(student["sessionToken"])
    assert client.get(url, headers=enrolled).status_code == 200

    outsider = _register(client, email="other@t.local", role="student").get_json()
    assert client.get(url, headers=_h(outsider["sessionToken"])).status_code == 404
