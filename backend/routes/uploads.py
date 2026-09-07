"""File uploads for lesson media and assignment attachments.

Storage: local filesystem under backend/instance/uploads/<kind>/{uuid}.<ext>.
Served via the authenticated `/media/<path>` route in `routes/media.py`.

Auth: any signed-in user, with the allowed *kinds* narrowed by role.
Students may attach a PDF or an image to an assignment submission — the
submit screen has always called this endpoint, but the role gate here was
`instructor, admin`, so every student attachment 403'd. Video upload stays
staff-only: nothing in the student flow needs it and a 200 MB write is not
something to hand an unvetted account.

Every accepted upload is recorded in `uploaded_files` so `/media` can answer
"may this caller read this file?" — see `utils/media.py`.
"""
from __future__ import annotations

import os
import uuid as _uuid
from pathlib import Path

from flask import Blueprint, current_app, jsonify, request

from routes.auth import current_user, login_required
from utils.media import register_upload

uploads_bp = Blueprint("uploads", __name__)


# kind -> (subfolder, allowed MIME types, allowed extensions, max bytes)
_KIND_RULES = {
    "video": (
        "videos",
        {"video/mp4", "video/webm"},
        {".mp4", ".webm"},
        200 * 1024 * 1024,
    ),
    "pdf": (
        "pdfs",
        {"application/pdf"},
        {".pdf"},
        25 * 1024 * 1024,
    ),
    "image": (
        "images",
        {"image/jpeg", "image/png", "image/webp"},
        {".jpg", ".jpeg", ".png", ".webp"},
        10 * 1024 * 1024,
    ),
}

# Which kinds each role may upload. The global `MAX_CONTENT_LENGTH` of 200 MB
# only ever applied to video anyway; capping pdf/image per-kind keeps a
# student from filling the disk one "essay" at a time.
_KINDS_BY_ROLE = {
    "admin": {"video", "pdf", "image"},
    "instructor": {"video", "pdf", "image"},
    "student": {"pdf", "image"},
    "parent": set(),
}

# Per-user upload burst limit. The disk is the shared resource here, and on
# the PythonAnywhere free tier it is 512 MB total.
_RATE_LIMIT = 30
_RATE_WINDOW = 300  # seconds


def _uploads_root() -> Path:
    root = Path(current_app.instance_path) / "uploads"
    root.mkdir(parents=True, exist_ok=True)
    return root


@uploads_bp.route("", methods=["POST"])
@uploads_bp.route("/", methods=["POST"])
@login_required
def upload():
    user = current_user()

    if not current_app.config.get("TESTING"):
        from utils.rate_limit import check_rate

        ok, retry_after = check_rate(
            "upload", user.id, limit=_RATE_LIMIT, window=_RATE_WINDOW,
        )
        if not ok:
            resp = jsonify({"error": "Too many uploads. Try again shortly."})
            resp.status_code = 429
            resp.headers["Retry-After"] = str(retry_after)
            return resp

    kind = (request.form.get("kind") or "").strip().lower()
    if kind not in _KIND_RULES:
        return (
            jsonify(
                {"error": f"kind must be one of {sorted(_KIND_RULES.keys())}."}
            ),
            400,
        )

    allowed_kinds = _KINDS_BY_ROLE.get(user.role, set())
    if kind not in allowed_kinds:
        return (
            jsonify(
                {"error": f"Your account is not allowed to upload '{kind}' files."}
            ),
            403,
        )

    if "file" not in request.files:
        return jsonify({"error": "Missing 'file' in multipart body."}), 400
    f = request.files["file"]
    if not f or not f.filename:
        return jsonify({"error": "Empty file."}), 400

    subfolder, allowed_mimes, allowed_exts, max_bytes = _KIND_RULES[kind]
    ext = os.path.splitext(f.filename)[1].lower()
    if ext not in allowed_exts:
        return (
            jsonify(
                {"error": f"Extension '{ext}' is not allowed for kind '{kind}'."}
            ),
            400,
        )
    # Browsers sometimes send an empty content_type; only reject if
    # explicitly wrong.
    if f.content_type and f.content_type not in allowed_mimes:
        return (
            jsonify(
                {
                    "error": f"Content-Type '{f.content_type}' not allowed for '{kind}'."
                }
            ),
            400,
        )

    # Cheap pre-check on the declared length so an oversized body is refused
    # before it is written to disk. The authoritative check is after the save,
    # since Content-Length is client-supplied.
    declared = request.content_length
    if declared is not None and declared > max_bytes:
        return _too_large(kind, max_bytes)

    dest_dir = _uploads_root() / subfolder
    dest_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{_uuid.uuid4()}{ext}"
    dest = dest_dir / filename
    f.save(str(dest))
    size = dest.stat().st_size

    if size > max_bytes:
        dest.unlink(missing_ok=True)
        return _too_large(kind, max_bytes)

    stored_path = f"{subfolder}/{filename}"
    register_upload(
        stored_path=stored_path,
        kind=kind,
        owner_id=user.id,
        size_bytes=size,
        content_type=f.content_type,
    )

    return (
        jsonify(
            {
                "url": f"/media/{stored_path}",
                "kind": kind,
                "filename": filename,
                "sizeBytes": size,
                "contentType": f.content_type or "",
            }
        ),
        201,
    )


def _too_large(kind: str, max_bytes: int):
    mb = max_bytes // (1024 * 1024)
    return (
        jsonify({"error": f"File too large. Max {mb} MB for kind '{kind}'."}),
        413,
    )
