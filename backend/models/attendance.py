"""Daily attendance marks."""
from __future__ import annotations

from models.base import (
    db,
    generate_uuid,
    utc_now,
    _iso,
    Any,
)

# =============================================================================
# Phase 12 — Attendance
#
# One row per (student, date). Class is captured at write-time so a mid-year
# class change doesn't retro-rewrite history. Homeroom teacher + admin can
# write (`utils/permissions.py:can_mark_attendance`). Read scope follows
# `can_view_student_records`.
# =============================================================================
ATTENDANCE_STATUSES = ("present", "absent", "late", "excused")


class AttendanceMark(db.Model):
    __tablename__ = "attendance_marks"

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    student_id = db.Column(
        db.String(36), db.ForeignKey("users.id"), nullable=False, index=True,
    )
    class_id = db.Column(
        db.String(36), db.ForeignKey("classes.id"), nullable=False, index=True,
    )
    date = db.Column(db.Date, nullable=False, index=True)
    status = db.Column(db.String(10), nullable=False)  # ATTENDANCE_STATUSES
    reason = db.Column(db.String(200), nullable=True)
    marked_by_id = db.Column(
        db.String(36), db.ForeignKey("users.id"), nullable=True,
    )

    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=utc_now, onupdate=utc_now,
    )

    __table_args__ = (
        db.UniqueConstraint("student_id", "date", name="uq_attendance_student_date"),
    )

    student = db.relationship("User", foreign_keys=[student_id])
    marker = db.relationship("User", foreign_keys=[marked_by_id])

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "studentId": self.student_id,
            "classId": self.class_id,
            "date": self.date.isoformat() if self.date else None,
            "status": self.status,
            "reason": self.reason,
            "markedById": self.marked_by_id,
            "createdAt": _iso(self.created_at),
            "updatedAt": _iso(self.updated_at),
        }
