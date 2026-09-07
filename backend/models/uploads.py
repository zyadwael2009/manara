"""The ownership record behind the /media path."""
from __future__ import annotations

from models.base import (
    db,
    generate_uuid,
    utc_now,
    _iso,
    Any,
)

# =============================================================================
# Uploaded files — the ownership record behind `/media/<path>`
# =============================================================================
class UploadedFile(db.Model):
    """One row per file accepted by `POST /api/uploads`.

    `/media/<path>` used to be a bare `send_from_directory` with no auth at
    all: anyone holding (or guessing) a URL could read a student's submitted
    essay. UUID filenames are obscurity, not access control — the URLs travel
    through API responses, browser history and `Referer` headers, and they
    never stop working when a teacher leaves or a student unenrolls.

    This table records who uploaded what so `routes/media.py` can answer
    "may this caller read this file?" — see `utils/media.py::can_read_upload`.
    """

    __tablename__ = "uploaded_files"

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    # Path relative to `instance/uploads/`, e.g. "pdfs/<uuid>.pdf". This is
    # what `/media/<path:filename>` receives, so it's the natural join key.
    stored_path = db.Column(db.String(500), nullable=False, unique=True, index=True)
    kind = db.Column(db.String(20), nullable=False)  # video | pdf | image
    owner_id = db.Column(
        db.String(36), db.ForeignKey("users.id"), nullable=True, index=True,
    )
    size_bytes = db.Column(db.Integer, nullable=False, default=0)
    content_type = db.Column(db.String(120), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)

    owner = db.relationship("User", foreign_keys=[owner_id])

    @property
    def url(self) -> str:
        return f"/media/{self.stored_path}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "url": self.url,
            "kind": self.kind,
            "ownerId": self.owner_id,
            "sizeBytes": self.size_bytes,
            "contentType": self.content_type,
            "createdAt": _iso(self.created_at),
        }
