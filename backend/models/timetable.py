"""The weekly class timetable and per-date overrides."""
from __future__ import annotations

from models.base import (
    db,
    generate_uuid,
    utc_now,
    Any,
)

# =============================================================================
# Phase 13 — Timetables
#
# `timetable_periods` = the base weekly schedule (Mon-Fri repeating).
# `timetable_overrides` = date-based exceptions (canceled or custom).
# Teacher is NOT stored on a period — derived from ClassCourseTeacher.
# Writes are admin-only; reads via `can_view_class_roster` (Phase 9).
# =============================================================================
TIMETABLE_OVERRIDE_KINDS = ("canceled", "custom")


class TimetablePeriod(db.Model):
    __tablename__ = "timetable_periods"

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    class_id = db.Column(
        db.String(36), db.ForeignKey("classes.id"), nullable=False, index=True,
    )
    course_id = db.Column(
        db.String(36), db.ForeignKey("courses.id"), nullable=False, index=True,
    )
    day_of_week = db.Column(db.Integer, nullable=False)  # 0=Mon .. 6=Sun
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    room = db.Column(db.String(40), nullable=True)
    order_index = db.Column(db.Integer, nullable=False, default=0)
    # Phase 27 — optional Zoom / Meet URL for this recurring period. When
    # set, the student's Now/Next + Timetable + Today strip render a
    # "Join" button during the period's live window; the URL opens in a
    # new tab. Nullable so most periods stay simple.
    meeting_url = db.Column(db.String(1000), nullable=True)

    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=utc_now, onupdate=utc_now,
    )

    __table_args__ = (
        db.UniqueConstraint(
            "class_id", "day_of_week", "start_time",
            name="uq_period_class_day_start",
        ),
    )

    course = db.relationship("Course", foreign_keys=[course_id])
    school_class = db.relationship("SchoolClass", foreign_keys=[class_id])

    def to_dict(self, *, include_teacher: bool = True) -> dict[str, Any]:
        data: dict[str, Any] = {
            "id": self.id,
            "classId": self.class_id,
            "courseId": self.course_id,
            "dayOfWeek": self.day_of_week,
            "startTime": self.start_time.strftime("%H:%M") if self.start_time else None,
            "endTime": self.end_time.strftime("%H:%M") if self.end_time else None,
            "room": self.room,
            "orderIndex": self.order_index,
            "meetingUrl": self.meeting_url,
        }
        c = self.course
        if c is not None:
            data["course"] = {
                "id": c.id,
                "title": c.title,
                "category": c.category,
            }
        if include_teacher:
            from models.people import User
            from models.school import ClassCourseTeacher

            # Teacher = ClassCourseTeacher(class_id, course_id).
            cct = ClassCourseTeacher.query.filter_by(
                class_id=self.class_id, course_id=self.course_id,
            ).first()
            teacher = None
            if cct is not None:
                teacher = db.session.get(User, cct.teacher_id)
            data["teacherName"] = teacher.name if teacher else None
            data["teacherId"] = teacher.id if teacher else None
        return data


class TimetableOverride(db.Model):
    __tablename__ = "timetable_overrides"

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    class_id = db.Column(
        db.String(36), db.ForeignKey("classes.id"), nullable=False, index=True,
    )
    date = db.Column(db.Date, nullable=False, index=True)
    kind = db.Column(db.String(10), nullable=False)  # canceled | custom
    period_id = db.Column(
        db.String(36), db.ForeignKey("timetable_periods.id"), nullable=True,
    )
    course_id = db.Column(
        db.String(36), db.ForeignKey("courses.id"), nullable=True,
    )
    start_time = db.Column(db.Time, nullable=True)
    end_time = db.Column(db.Time, nullable=True)
    room = db.Column(db.String(40), nullable=True)
    note = db.Column(db.String(200), nullable=True)

    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)

    period = db.relationship("TimetablePeriod", foreign_keys=[period_id])
    course = db.relationship("Course", foreign_keys=[course_id])

    def to_dict(self) -> dict[str, Any]:
        c = self.course
        return {
            "id": self.id,
            "classId": self.class_id,
            "date": self.date.isoformat() if self.date else None,
            "kind": self.kind,
            "periodId": self.period_id,
            "courseId": self.course_id,
            "courseTitle": c.title if c else None,
            "startTime": self.start_time.strftime("%H:%M") if self.start_time else None,
            "endTime": self.end_time.strftime("%H:%M") if self.end_time else None,
            "room": self.room,
            "note": self.note,
        }
