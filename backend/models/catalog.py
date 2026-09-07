"""Curriculum content: courses, their modules and lessons, and the checkpoints embedded in lesson video."""
from __future__ import annotations

from models.base import (
    db,
    generate_uuid,
    utc_now,
    _iso,
    Decimal,
    Any,
)

# =============================================================================
# Courses (curriculum entries — belong to exactly one grade)
# =============================================================================
class Course(db.Model):
    __tablename__ = "courses"

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False, default="")

    # NEW in Phase 2: courses belong to a grade (== curriculum). Required.
    # Nullable in the DB for the Phase 1 -> Phase 2 migration path, but every
    # NEW course requires it (validated in the endpoint).
    grade_id = db.Column(db.String(36), db.ForeignKey("grades.id"), nullable=True, index=True)

    # NEW in Phase 2: elective group tag. NULL = mandatory. Two courses with
    # the same (grade_id, elective_group) are mutually-exclusive alternatives.
    elective_group = db.Column(db.String(80), nullable=True, index=True)

    # Retained from Phase 1 but demoted to a "primary author" hint — the
    # authoritative "who teaches this" is `class_course_teachers`. Kept
    # nullable and no longer used for authorization.
    instructor_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=True, index=True)

    # NEW: prerequisite link — the course this one succeeds (e.g. French II
    # succeeds French I). Used by promotion's elective carry-forward.
    succeeds_course_id = db.Column(
        db.String(36), db.ForeignKey("courses.id"), nullable=True, index=True
    )

    # Phase 5: minimum cumulative percentage a student must reach in this
    # course to receive a certificate. NULL = fall back to 60% at gate-check
    # time. Admin can raise per course.
    min_certificate_percent = db.Column(db.Integer, nullable=True)

    # Kept from Phase 1; UI hides these but schema stays for future.
    price = db.Column(db.Numeric(10, 2), nullable=False, default=Decimal("0"))
    category = db.Column(db.String(80), nullable=False, default="general", index=True)
    thumbnail_url = db.Column(db.String(500), nullable=True)
    status = db.Column(db.String(20), nullable=False, default="draft", index=True)

    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=utc_now, onupdate=utc_now
    )

    instructor = db.relationship("User", foreign_keys=[instructor_id])
    modules = db.relationship(
        "Module",
        backref="course",
        lazy="dynamic",
        cascade="all, delete-orphan",
        order_by="Module.order_index",
    )
    class_course_teachers = db.relationship(
        "ClassCourseTeacher",
        backref="course",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )
    enrollments = db.relationship(
        "Enrollment",
        backref="course",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )

    def to_dict(
        self,
        *,
        include_modules: bool = False,
        hide_content: bool = True,
        my_enrollment: "Enrollment | None" = None,
        student_id: "str | None" = None,
    ) -> dict[str, Any]:
        """`student_id` (Phase 16) triggers per-quiz last/best/attempts
        decoration on every module quiz summary — one grouped query for
        the whole course. Only meaningful when `include_modules=True`.

        Also (Phase 18) attaches `myAttendance` — a per-student
        summary shared across all courses (attendance is class-level,
        not per-course, but surfacing it in each course context is
        useful where students actually look).
        """
        instr = self.instructor
        data: dict[str, Any] = {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "gradeId": self.grade_id,
            "gradeName": self.grade.name if self.grade else None,
            "electiveGroup": self.elective_group,
            "succeedsCourseId": self.succeeds_course_id,
            "minCertificatePercent": self.min_certificate_percent,
            "instructorId": self.instructor_id,
            "instructorName": instr.name if instr else None,
            "price": float(self.price) if self.price is not None else 0.0,
            "isFree": (self.price is None) or (Decimal(self.price) == 0),
            "category": self.category,
            "thumbnailUrl": self.thumbnail_url,
            "status": self.status,
            "createdAt": _iso(self.created_at),
            "updatedAt": _iso(self.updated_at),
            "myEnrollment": my_enrollment.to_dict() if my_enrollment else None,
        }
        if student_id is not None:
            # Phase 18 — attach the caller's overall attendance summary.
            from utils.attendance import compute_student_attendance_summary
            data["myAttendance"] = compute_student_attendance_summary(student_id)
        if include_modules:
            modules = self.modules.order_by(Module.order_index).all()
            history = None
            if student_id is not None:
                # Local import to keep utils.quizzes import out of the module
                # top level (models.py is imported by utils.quizzes itself).
                from utils.quizzes import compute_student_quiz_history
                from models.quizzes import Quiz
                quiz_ids = [
                    q.id for m in modules
                    for q in Quiz.query.filter_by(module_id=m.id).all()
                ]
                history = compute_student_quiz_history(student_id, quiz_ids)
            data["modules"] = [
                m.to_dict(
                    include_lessons=True,
                    hide_content=hide_content,
                    my_quiz_history=history,
                )
                for m in modules
            ]
        return data


class Module(db.Model):
    __tablename__ = "modules"

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    course_id = db.Column(db.String(36), db.ForeignKey("courses.id"), nullable=False, index=True)
    title = db.Column(db.String(200), nullable=False)
    order_index = db.Column(db.Integer, nullable=False, default=0)

    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=utc_now, onupdate=utc_now
    )

    lessons = db.relationship(
        "Lesson",
        backref="module",
        lazy="dynamic",
        cascade="all, delete-orphan",
        order_by="Lesson.order_index",
    )

    def to_dict(
        self,
        *,
        include_lessons: bool = False,
        hide_content: bool = True,
        my_quiz_history: "dict[str, dict] | None" = None,
    ) -> dict[str, Any]:
        """`my_quiz_history` is an optional {quiz_id: {attemptsCount, bestPercent,
        lastPercent, lastAttemptNumber, passed}} map — see
        `utils.quizzes.compute_student_quiz_history`. When supplied, each
        quiz summary is decorated with the caller's last/best/attempts.
        """
        data: dict[str, Any] = {
            "id": self.id,
            "courseId": self.course_id,
            "title": self.title,
            "orderIndex": self.order_index,
        }
        if include_lessons:
            data["lessons"] = [
                l.to_dict(hide_content=hide_content)
                for l in self.lessons.order_by(Lesson.order_index).all()
            ]
            # Phase 4: also carry the module's quiz summaries so the client
            # can render them alongside lessons in the outline. Phase 16
            # decorates each summary with the caller's own last/best mark
            # when a history map is provided (course-detail student view).
            from models.quizzes import Quiz
            quiz_summaries = []
            for q in Quiz.query.filter_by(module_id=self.id).order_by(Quiz.created_at.asc()).all():
                s = {
                    "id": q.id,
                    "moduleId": q.module_id,
                    "title": q.title,
                    "isPublished": q.is_published,
                    "totalPoints": q.total_points(),
                    "passingScore": q.passing_score,
                    "timeLimitMinutes": q.time_limit_minutes,
                }
                if my_quiz_history is not None:
                    hist = my_quiz_history.get(q.id)
                    s["myAttemptsCount"] = hist["attemptsCount"] if hist else 0
                    s["myBestPercent"] = hist["bestPercent"] if hist else None
                    s["myLastPercent"] = hist["lastPercent"] if hist else None
                    s["myPassed"] = hist["passed"] if hist else False
                quiz_summaries.append(s)
            data["quizzes"] = quiz_summaries
        return data


class Lesson(db.Model):
    __tablename__ = "lessons"

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    module_id = db.Column(db.String(36), db.ForeignKey("modules.id"), nullable=False, index=True)
    title = db.Column(db.String(200), nullable=False)
    type = db.Column(db.String(20), nullable=False, default="text")
    content_url = db.Column(db.String(1000), nullable=True)
    content_text = db.Column(db.Text, nullable=True)
    duration_minutes = db.Column(db.Integer, nullable=True)
    order_index = db.Column(db.Integer, nullable=False, default=0)

    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=utc_now, onupdate=utc_now
    )

    def to_dict(self, *, hide_content: bool = True) -> dict[str, Any]:
        data: dict[str, Any] = {
            "id": self.id,
            "moduleId": self.module_id,
            "title": self.title,
            "type": self.type,
            "durationMinutes": self.duration_minutes,
            "orderIndex": self.order_index,
            "previewLocked": bool(hide_content),
        }
        if not hide_content:
            data["contentUrl"] = self.content_url
            data["contentText"] = self.content_text
        return data


# =============================================================================
# Phase 27 — Video-inline checkpoints
#
# One row = one pause-point on a video lesson. Rendered client-side by
# `_VideoBody` in `lesson_viewer_screen.dart` — the player pauses at
# `position_seconds`, shows the MC prompt, and only resumes on a correct
# answer. There's no attempts table because the checkpoint is purely
# engagement — a wrong answer just retries in-place. Grade impact: none;
# lesson `progress` is only marked when every checkpoint answered.
#
# `options_json` shape (validated at the route layer):
#     [{"id": "opt-1", "text": "Newton"}, {"id": "opt-2", "text": "Einstein"}]
# `correct_option_id` references one of those `id` fields.
# =============================================================================
class VideoCheckpoint(db.Model):
    __tablename__ = "video_checkpoints"

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    lesson_id = db.Column(
        db.String(36), db.ForeignKey("lessons.id"), nullable=False, index=True,
    )
    position_seconds = db.Column(db.Integer, nullable=False)
    prompt = db.Column(db.String(500), nullable=False)
    correct_option_id = db.Column(db.String(40), nullable=True)
    options_json = db.Column(db.Text, nullable=False, default="[]")
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)

    __table_args__ = (
        db.Index("ix_checkpoint_lesson_position", "lesson_id", "position_seconds"),
    )

    def to_dict(self, *, hide_answer: bool = False) -> dict[str, Any]:
        import json as _json
        try:
            opts = _json.loads(self.options_json or "[]")
        except Exception:
            opts = []
        data: dict[str, Any] = {
            "id": self.id,
            "lessonId": self.lesson_id,
            "positionSeconds": self.position_seconds,
            "prompt": self.prompt,
            "options": opts,
            "createdAt": _iso(self.created_at),
        }
        # Only owners see the correct answer server-side; students judge
        # correctness client-side against their own choice, and the server
        # never records attempts.
        if not hide_answer:
            data["correctOptionId"] = self.correct_option_id
        return data


# =============================================================================
# Phase 19 — Announcements
#
# One row = one broadcast from an admin / homeroom teacher / course teacher.
# `audience` is the fan-out shape:
#   * "school"  — every student + every parent see it (class_id, course_id null)
#   * "class"   — every student in `class_id` + their parents (course_id null)
#   * "course"  — every student enrolled in `course_id` + their parents
#                 (optionally scoped to `class_id` for a single-section post)
#
# Writes gated in `routes/announcements.py` — admin can post any audience,
# homeroom teacher can only post `class` for classes they homeroom, and a
# course teacher can only post `course` for a (class_id, course_id) pair
# they teach via ClassCourseTeacher. Deletes: author OR admin.
# =============================================================================
ANNOUNCEMENT_AUDIENCES = ("school", "class", "course")
