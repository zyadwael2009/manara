"""Curriculum standards and the content tagged against them."""
from __future__ import annotations

from models.base import (
    db,
    generate_uuid,
    utc_now,
    _iso,
    Any,
)

# =============================================================================
# Phase 32 · T3 — Standards alignment
#
# `Standard` = one row in a curriculum standards library (e.g.
# "MATH.6.EE.1: Write expressions with whole-number exponents").
# `StandardTag` binds a standard to a lesson, quiz, or assignment via
# a polymorphic (`taggable_type`, `taggable_id`) pair — same shape as
# Rails' polymorphic association because it lets one tag surface on
# whichever content the teacher aligned it to without three separate
# join tables.
#
# Mastery rollup (in `utils/standards.py`) reads a student's quiz +
# assignment scores where the underlying quiz/assignment is tagged
# with a standard, and returns a per-standard mastery percent + a
# "beginning / progressing / meeting / mastered" band.
#
# Trust-core: tags are content metadata; the mastery rollup reads
# existing grade tables and never writes them.
# =============================================================================
STANDARD_TAGGABLE_TYPES = ("lesson", "quiz", "assignment")


class Standard(db.Model):
    __tablename__ = "standards"

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    code = db.Column(db.String(80), nullable=False, unique=True, index=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False, default="")
    # Optional subject grouping — matches `Course.category` values so
    # the standards library can be filtered "Math", "Science", etc.
    subject = db.Column(db.String(80), nullable=True, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "code": self.code,
            "name": self.name,
            "description": self.description,
            "subject": self.subject,
            "createdAt": _iso(self.created_at),
        }


class StandardTag(db.Model):
    __tablename__ = "standard_tags"

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    standard_id = db.Column(
        db.String(36), db.ForeignKey("standards.id"),
        nullable=False, index=True,
    )
    taggable_type = db.Column(db.String(20), nullable=False)  # lesson|quiz|assignment
    taggable_id = db.Column(db.String(36), nullable=False, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)

    __table_args__ = (
        db.UniqueConstraint(
            "standard_id", "taggable_type", "taggable_id",
            name="uq_standard_tag_triple",
        ),
        db.Index(
            "ix_standard_tag_target",
            "taggable_type", "taggable_id",
        ),
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "standardId": self.standard_id,
            "taggableType": self.taggable_type,
            "taggableId": self.taggable_id,
            "createdAt": _iso(self.created_at),
        }
