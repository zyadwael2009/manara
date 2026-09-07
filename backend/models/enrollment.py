"""A student's link to a course, and their progress through its lessons."""
from __future__ import annotations

from models.base import (
    db,
    generate_uuid,
    utc_now,
    _iso,
    Any,
)

# =============================================================================
# Enrollments (Phase 2) — student ↔ course. Derived from class placement for
# mandatory courses, explicit admin pick for electives, manual escape hatch.
# =============================================================================
class Enrollment(db.Model):
    __tablename__ = "enrollments"

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    student_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False, index=True)
    course_id = db.Column(db.String(36), db.ForeignKey("courses.id"), nullable=False, index=True)

    status = db.Column(db.String(20), nullable=False, default="active")
    enrolled_via = db.Column(db.String(30), nullable=False, default="auto_mandatory")
    enrolled_by_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=True)

    progress_percent = db.Column(db.Integer, nullable=False, default=0)

    # Phase 3: cached grade rollups. Recomputed transactionally when grade
    # entries or the course's rubric change. Read paths never re-aggregate.
    cached_percent = db.Column(db.Numeric(5, 2), nullable=True)
    cached_letter = db.Column(db.String(8), nullable=True)
    cached_gpa = db.Column(db.Numeric(4, 2), nullable=True)
    cached_computed_at = db.Column(db.DateTime, nullable=True)

    enrolled_at = db.Column(db.DateTime, nullable=False, default=utc_now)
    completed_at = db.Column(db.DateTime, nullable=True)

    __table_args__ = (
        db.UniqueConstraint("student_id", "course_id", name="uq_student_course"),
    )

    student = db.relationship("User", foreign_keys=[student_id])

    @property
    def is_active(self) -> bool:
        return self.status in ("active", "completed")

    def to_dict(
        self,
        *,
        include_course: bool = False,
        # Phase 33 fix #5 — N+1 killer. Callers that serialise a
        # batch of enrollments pre-load
        #   {enrollment_id: Certificate}
        # via a single `Certificate.query.filter(enrollment_id.in_(ids))`
        # and pass it in here; the per-row `Certificate.query.filter_by`
        # is skipped whenever the map is provided (even if the row is
        # absent from it — an explicit None means "already checked,
        # no cert"). Backwards-compatible: single-row callers pass
        # nothing and get the old lookup.
        cert_by_enrollment: dict | None = None,
    ) -> dict[str, Any]:
        data: dict[str, Any] = {
            "id": self.id,
            "studentId": self.student_id,
            "courseId": self.course_id,
            "status": self.status,
            "enrolledVia": self.enrolled_via,
            "progressPercent": self.progress_percent,
            "cachedPercent": float(self.cached_percent) if self.cached_percent is not None else None,
            "cachedLetter": self.cached_letter,
            "cachedGpa": float(self.cached_gpa) if self.cached_gpa is not None else None,
            "enrolledAt": _iso(self.enrolled_at),
            "completedAt": _iso(self.completed_at),
        }
        if include_course and self.course:
            c = self.course
            data["course"] = {
                "id": c.id,
                "title": c.title,
                "gradeId": c.grade_id,
                "category": c.category,
                "electiveGroup": c.elective_group,
                "thumbnailUrl": c.thumbnail_url,
                "status": c.status,
            }
        # Phase 5: attach cert summary if one exists for this enrollment.
        if cert_by_enrollment is not None:
            cert = cert_by_enrollment.get(self.id)
        else:
            from models.credentials import Certificate
            cert = Certificate.query.filter_by(enrollment_id=self.id).first()
        if cert is not None:
            data["certificate"] = {
                "id": cert.id,
                "certificateNumber": cert.certificate_number,
                "issuedAt": _iso(cert.issued_at),
                "revoked": cert.revoked,
            }
        return data


class LessonProgress(db.Model):
    """Per-student per-lesson completion + resume position."""
    __tablename__ = "lesson_progress"

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    enrollment_id = db.Column(db.String(36), db.ForeignKey("enrollments.id"), nullable=False, index=True)
    lesson_id = db.Column(db.String(36), db.ForeignKey("lessons.id"), nullable=False, index=True)

    completed = db.Column(db.Boolean, nullable=False, default=False)
    completed_at = db.Column(db.DateTime, nullable=True)
    last_position_seconds = db.Column(db.Integer, nullable=False, default=0)
    last_visited_at = db.Column(db.DateTime, nullable=True)

    __table_args__ = (
        db.UniqueConstraint("enrollment_id", "lesson_id", name="uq_lesson_progress_pair"),
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "enrollmentId": self.enrollment_id,
            "lessonId": self.lesson_id,
            "completed": self.completed,
            "completedAt": _iso(self.completed_at),
            "lastPositionSeconds": self.last_position_seconds,
            "lastVisitedAt": _iso(self.last_visited_at),
        }
