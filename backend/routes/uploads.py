"""File uploads for lesson media.

Storage: local filesystem under backend/instance/uploads/<kind>/{uuid}.<ext>.
Served via a separate /media/<path> route registered in app.py.

Auth: instructor or admin (any teacher can upload — content edit rights
gate whether they can actually attach the URL to a lesson, but uploading
itself is broad).
"""
from __future__ import annotations

import os
import uuid as _uuid
from pathlib import Path

from flask import Blueprint, current_app, jsonify, request

from routes.auth import require_role

uploads_bp = Blueprint("uploads", __name__)


# kind -> (subfolder, allowed MIME types, allowed extensions)
_KIND_RULES = {
    "video": (
        "videos",
        {"video/mp4", "video/webm"},
        {".mp4", ".webm"},
    ),
    "pdf": (
        "pdfs",
        {"application/pdf"},
        {".pdf"},
    ),
    "image": (
        "images",
        {"image/jpeg", "image/png", "image/webp"},
        {".jpg", ".jpeg", ".png", ".webp"},
    ),
}


def _uploads_root() -> Path:
    root = Path(current_app.instance_path) / "uploads"
    root.mkdir(parents=True, exist_ok=True)
    return root


@uploads_bp.route("", methods=["POST"])
@uploads_bp.route("/", methods=["POST"])
@require_role("instructor", "admin")
def upload():
    kind = (request.form.get("kind") or "").strip().lower()
    if kind not in _KIND_RULES:
        return (
            jsonify(
                {"error": f"kind must be one of {sorted(_KIND_RULES.keys())}."}
            ),
            400,
        )
    if "file" not in request.files:
        return jsonify({"error": "Missing 'file' in multipart body."}), 400
    f = request.files["file"]
    if not f or not f.filename:
        return jsonify({"error": "Empty file."}), 400

    subfolder, allowed_mimes, allowed_exts = _KIND_RULES[kind]
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

    dest_dir = _uploads_root() / subfolder
    dest_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{_uuid.uuid4()}{ext}"
    dest = dest_dir / filename
    f.save(str(dest))
    size = dest.stat().st_size

    return (
        jsonify(
            {
                "url": f"/media/{subfolder}/{filename}",
                "kind": kind,
                "filename": filename,
                "sizeBytes": size,
                "contentType": f.content_type or "",
            }
        ),
        201,
    )
