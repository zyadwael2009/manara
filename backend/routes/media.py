"""Authenticated serving of uploaded files.

Replaces the bare `send_from_directory` route that used to live in `app.py`,
which answered 200 to any caller — signed in or not — that held a `/media/`
URL. See `utils/media.py` for the authorization rules.

The 403 body is deliberately identical to the 404 body: a caller who is not
allowed to read a file should not be able to use this endpoint to learn
whether that file exists.
"""
from __future__ import annotations

from pathlib import Path

from flask import Blueprint, current_app, jsonify, send_from_directory

from routes.auth import current_user, login_required
from utils.media import can_read_upload

media_bp = Blueprint("media", __name__)

_NOT_FOUND = ({"error": "Not found."}, 404)


@media_bp.route("/media/<path:filename>", methods=["GET"])
@login_required
def serve_media(filename: str):
    uploads_root = Path(current_app.instance_path) / "uploads"

    # `send_from_directory` already refuses to escape the root, but resolving
    # first means a traversal attempt 404s the same way a missing file does
    # rather than raising inside the permission check.
    candidate = (uploads_root / filename).resolve()
    try:
        candidate.relative_to(uploads_root.resolve())
    except ValueError:
        return jsonify(_NOT_FOUND[0]), _NOT_FOUND[1]

    if not can_read_upload(current_user(), filename):
        return jsonify(_NOT_FOUND[0]), _NOT_FOUND[1]

    return send_from_directory(str(uploads_root), filename)
