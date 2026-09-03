"""SQLAlchemy models for the LMS.

All models live in this single file, matching the convention used across the
developer's other Flask projects (single `models.py`, no per-model modules).

Conventions repeated per model (no shared Base/Mixin):
  * `__tablename__` is plural snake_case.
  * `id = db.Column(db.String(36), primary_key=True, default=generate_uuid)`
  * `created_at` / `updated_at` on every table that meaningfully mutates.
  * `to_dict()` returns **camelCase** keys — the API layer never uses a
    serializer library.

Phase 2 scope: adds the school hierarchy (sections, grades, classes),
per-class teacher assignments (class_course_teachers), department leadership
(department_leaders), and enrollments derived from class placement. See the
project memory files for the full model:
  - lms-is-k12-school, school-hierarchy, curriculum-model,
    teacher-roles, grading-model, quizzes-model.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash

from utils.uuid_gen import generate_uuid
from utils.time import utc_now

db = SQLAlchemy()


# --- Enum-ish string sets (kept as plain constants; the DB stores strings) ---
USER_ROLES = ("student", "instructor", "admin", "parent")
PARENT_RELATIONSHIPS = ("father", "mother", "guardian")
COURSE_STATUSES = ("draft", "published")
LESSON_TYPES = ("video", "text", "pdf")

# Phase 2 additions ---------------------------------------------------------
ENROLLMENT_STATUSES = ("active", "dropped", "completed")
ENROLLED_VIA = ("auto_mandatory", "elective_choice", "manual")

# Common elective groups; free-form string so admins can add more without
# migrations. See curriculum-model memory.
COMMON_ELECTIVE_GROUPS = (
    "language",
    "science_track",
    "math_track",
    "humanities",
    "arts",
)

# Departments — match the categories field on courses. Free-form for the
# same reason.
COMMON_DEPARTMENTS = (
    "math",
    "science",
    "english",
    "social_studies",
    "languages",
    "arts",
    "pe",
    "computer_science",
    "general",
)


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


# =============================================================================
# Sections (admin-configurable school sections: Elementary / Middle / High)
# =============================================================================
class Section(db.Model):
    __tablename__ = "sections"

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    name = db.Column(db.String(80), nullable=False, unique=True)
    order_index = db.Column(db.Integer, nullable=False, default=0)

    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=utc_now, onupdate=utc_now
    )

    grades = db.relationship("Grade", backref="section", lazy="dynamic")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "orderIndex": self.order_index,
            "createdAt": _iso(self.created_at),
        }


# =============================================================================
# Grades (Grade 9, Grade 10, ...)
# =============================================================================
class Grade(db.Model):
    __tablename__ = "grades"

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    name = db.Column(db.String(80), nullable=False, unique=True)
    section_id = db.Column(db.String(36), db.ForeignKey("sections.id"), nullable=True, index=True)
    order_index = db.Column(db.Integer, nullable=False, default=0)

    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=utc_now, onupdate=utc_now
    )

    classes = db.relationship("SchoolClass", backref="grade", lazy="dynamic")
    courses = db.relationship("Course", backref="grade", lazy="dynamic")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "sectionId": self.section_id,
            "sectionName": self.section.name if self.section else None,
            "orderIndex": self.order_index,
            "createdAt": _iso(self.created_at),
        }


# =============================================================================
# Classes (Grade 9-A) — python name SchoolClass to avoid the `class` keyword
# =============================================================================
class SchoolClass(db.Model):
    __tablename__ = "classes"

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    grade_id = db.Column(db.String(36), db.ForeignKey("grades.id"), nullable=False, index=True)
    name = db.Column(db.String(80), nullable=False)
    homeroom_teacher_id = db.Column(
        db.String(36), db.ForeignKey("users.id"), nullable=True, unique=True, index=True
    )

    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=utc_now, onupdate=utc_now
    )

    __table_args__ = (
        db.UniqueConstraint("grade_id", "name", name="uq_class_grade_name"),
    )

    students = db.relationship(
        "User",
        primaryjoin="SchoolClass.id==User.class_id",
        foreign_keys="User.class_id",
        backref="school_class",
        lazy="dynamic",
    )
    homeroom_teacher = db.relationship(
        "User",
        foreign_keys=[homeroom_teacher_id],
    )
    class_course_teachers = db.relationship(
        "ClassCourseTeacher",
        backref="school_class",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )

    def to_dict(self, *, include_roster: bool = False) -> dict[str, Any]:
        data: dict[str, Any] = {
            "id": self.id,
            "gradeId": self.grade_id,
            "gradeName": self.grade.name if self.grade else None,
            "name": self.name,
            "homeroomTeacherId": self.homeroom_teacher_id,
            "homeroomTeacherName": self.homeroom_teacher.name if self.homeroom_teacher else None,
            "studentCount": self.students.count(),
            "createdAt": _iso(self.created_at),
        }
        if include_roster:
            data["students"] = [s.to_dict() for s in self.students]
        return data


# =============================================================================
# Users
# =============================================================================
class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(190), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="student")

    # NEW in Phase 2: a student belongs to at most one class. Only meaningful
    # when role='student'; validated in the endpoints that set it.
    class_id = db.Column(db.String(36), db.ForeignKey("classes.id"), nullable=True, index=True)

    token_version = db.Column(db.Integer, nullable=False, default=1)
    failed_login_count = db.Column(db.Integer, nullable=False, default=0)
    locked_until = db.Column(db.DateTime, nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    # NEW: Grade-12 graduation timestamp. Coexists with is_active=False on
    # graduated users; historical enrollments / grades / certificates persist.
    graduated_at = db.Column(db.DateTime, nullable=True)
    # Phase 23 — withdrawal (a student transfers / leaves the school).
    # Same soft-delete pattern as graduation: is_active=False + timestamp,
    # historical rows preserved so a re-enrollment or a transcript request
    # still works months later.
    withdrawn_at = db.Column(db.DateTime, nullable=True)
    # Phase 25 — per-user opaque token for the ICS calendar feed URL.
    # Calendar apps can't send headers/cookies; the token IS the auth
    # for `/api/calendar/<token>.ics`. Rotatable via a POST — see
    # `routes/calendar_feed.py`.
    calendar_token = db.Column(db.String(64), nullable=True, index=True, unique=True)

    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=utc_now, onupdate=utc_now
    )

    # --- Relationships ---
    # Parent linkages (unchanged from Phase 1; endpoints land in Phase 6).
    parent_links = db.relationship(
        "ParentStudentLink",
        backref="parent",
        lazy="dynamic",
        foreign_keys="ParentStudentLink.parent_id",
    )
    student_links = db.relationship(
        "ParentStudentLink",
        backref="student",
        lazy="dynamic",
        foreign_keys="ParentStudentLink.student_id",
    )

    # --- Password helpers ---
    def set_password(self, raw_password: str) -> None:
        self.password_hash = generate_password_hash(raw_password)

    def check_password(self, raw_password: str) -> bool:
        return check_password_hash(self.password_hash, raw_password)

    # --- Serialization ---
    def to_dict(self, *, include_class: bool = True) -> dict[str, Any]:
        data: dict[str, Any] = {
            "id": self.id,
            "name": self.name,
            "email": self.email,
            "role": self.role,
            "isActive": self.is_active,
            "createdAt": _iso(self.created_at),
        }
        if include_class and self.role == "student":
            sc = self.school_class
            data["classId"] = self.class_id
            data["className"] = sc.name if sc else None
            data["gradeId"] = sc.grade_id if sc else None
            data["gradeName"] = sc.grade.name if (sc and sc.grade) else None
        return data


# =============================================================================
# Parent <-> Student link (endpoints land in Phase 6)
# =============================================================================
class ParentStudentLink(db.Model):
    __tablename__ = "parent_student_links"

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    parent_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False, index=True)
    student_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False, index=True)
    relationship_type = db.Column(db.String(20), nullable=False, default="guardian")

    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)

    __table_args__ = (
        db.UniqueConstraint("parent_id", "student_id", name="uq_parent_student_pair"),
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "parentId": self.parent_id,
            "studentId": self.student_id,
            "relationship": self.relationship_type,
            "createdAt": _iso(self.created_at),
        }


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
# Class <-> Course teacher assignment (Phase 2)
# One row per (course, class) — records WHO teaches this course to this class.
# =============================================================================
class ClassCourseTeacher(db.Model):
    __tablename__ = "class_course_teachers"

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    course_id = db.Column(db.String(36), db.ForeignKey("courses.id"), nullable=False, index=True)
    class_id = db.Column(db.String(36), db.ForeignKey("classes.id"), nullable=False, index=True)
    teacher_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False, index=True)
    assigned_by_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=True)
    assigned_at = db.Column(db.DateTime, nullable=False, default=utc_now)

    __table_args__ = (
        db.UniqueConstraint("course_id", "class_id", name="uq_course_class_teacher"),
    )

    teacher = db.relationship("User", foreign_keys=[teacher_id])

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "courseId": self.course_id,
            "classId": self.class_id,
            "teacherId": self.teacher_id,
            "teacherName": self.teacher.name if self.teacher else None,
            "assignedAt": _iso(self.assigned_at),
        }


# =============================================================================
# Department leaders (Phase 2)
# One row per (department, section_id) — the leader who owns content editing
# rights for every course in that department within that section.
# =============================================================================
class DepartmentLeader(db.Model):
    __tablename__ = "department_leaders"

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    department = db.Column(db.String(80), nullable=False, index=True)  # matches courses.category
    section_id = db.Column(db.String(36), db.ForeignKey("sections.id"), nullable=False, index=True)
    teacher_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False, index=True)
    assigned_by_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=True)
    assigned_at = db.Column(db.DateTime, nullable=False, default=utc_now)

    __table_args__ = (
        db.UniqueConstraint("department", "section_id", name="uq_dept_section_leader"),
    )

    section = db.relationship("Section")
    teacher = db.relationship("User", foreign_keys=[teacher_id])

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "department": self.department,
            "sectionId": self.section_id,
            "sectionName": self.section.name if self.section else None,
            "teacherId": self.teacher_id,
            "teacherName": self.teacher.name if self.teacher else None,
            "assignedAt": _iso(self.assigned_at),
        }


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
            cert = Certificate.query.filter_by(enrollment_id=self.id).first()
        if cert is not None:
            data["certificate"] = {
                "id": cert.id,
                "certificateNumber": cert.certificate_number,
                "issuedAt": _iso(cert.issued_at),
                "revoked": cert.revoked,
            }
        return data


# =============================================================================
# Phase 3 — Progress + Grading
# =============================================================================

# Grade-entry status constants
GRADE_ENTRY_MAX = 100  # sanity ceiling; per-category max is course_rubric.max_score


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


class SchoolYear(db.Model):
    __tablename__ = "school_years"

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    name = db.Column(db.String(80), nullable=False, unique=True)
    start_date = db.Column(db.Date, nullable=True)
    end_date = db.Column(db.Date, nullable=True)
    is_current = db.Column(db.Boolean, nullable=False, default=False)

    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)
    updated_at = db.Column(db.DateTime, nullable=False, default=utc_now, onupdate=utc_now)

    terms = db.relationship("Term", backref="school_year", lazy="dynamic")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "startDate": self.start_date.isoformat() if self.start_date else None,
            "endDate": self.end_date.isoformat() if self.end_date else None,
            "isCurrent": self.is_current,
        }


class Term(db.Model):
    __tablename__ = "terms"

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    school_year_id = db.Column(db.String(36), db.ForeignKey("school_years.id"), nullable=False, index=True)
    name = db.Column(db.String(80), nullable=False)
    start_date = db.Column(db.Date, nullable=True)
    end_date = db.Column(db.Date, nullable=True)
    order_index = db.Column(db.Integer, nullable=False, default=0)
    is_locked = db.Column(db.Boolean, nullable=False, default=False)
    locked_at = db.Column(db.DateTime, nullable=True)

    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)
    updated_at = db.Column(db.DateTime, nullable=False, default=utc_now, onupdate=utc_now)

    __table_args__ = (
        db.UniqueConstraint("school_year_id", "name", name="uq_term_year_name"),
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "schoolYearId": self.school_year_id,
            "schoolYearName": self.school_year.name if self.school_year else None,
            "name": self.name,
            "startDate": self.start_date.isoformat() if self.start_date else None,
            "endDate": self.end_date.isoformat() if self.end_date else None,
            "orderIndex": self.order_index,
            "isLocked": self.is_locked,
            "lockedAt": _iso(self.locked_at),
        }


class GradeCategory(db.Model):
    """Global master list of grading categories (Commitment, Quizzes, …)."""
    __tablename__ = "grade_categories"

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    name = db.Column(db.String(80), nullable=False)
    slug = db.Column(db.String(80), nullable=False, unique=True)
    order_index = db.Column(db.Integer, nullable=False, default=0)
    is_system = db.Column(db.Boolean, nullable=False, default=False)

    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "slug": self.slug,
            "orderIndex": self.order_index,
            "isSystem": self.is_system,
        }


class CourseRubric(db.Model):
    """Per-course category × max_score. Sum per course must == 100."""
    __tablename__ = "course_rubrics"

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    course_id = db.Column(db.String(36), db.ForeignKey("courses.id"), nullable=False, index=True)
    grade_category_id = db.Column(db.String(36), db.ForeignKey("grade_categories.id"), nullable=False, index=True)
    max_score = db.Column(db.Integer, nullable=False)
    order_index = db.Column(db.Integer, nullable=False, default=0)

    __table_args__ = (
        db.UniqueConstraint("course_id", "grade_category_id", name="uq_rubric_course_category"),
    )

    grade_category = db.relationship("GradeCategory")

    def to_dict(self) -> dict[str, Any]:
        gc = self.grade_category
        return {
            "id": self.id,
            "courseId": self.course_id,
            "gradeCategoryId": self.grade_category_id,
            "gradeCategoryName": gc.name if gc else None,
            "gradeCategorySlug": gc.slug if gc else None,
            "maxScore": self.max_score,
            "orderIndex": self.order_index,
        }


class GradeEntry(db.Model):
    """Actual score for a (enrollment × category × term) triple."""
    __tablename__ = "grade_entries"

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    enrollment_id = db.Column(db.String(36), db.ForeignKey("enrollments.id"), nullable=False, index=True)
    grade_category_id = db.Column(db.String(36), db.ForeignKey("grade_categories.id"), nullable=False, index=True)
    term_id = db.Column(db.String(36), db.ForeignKey("terms.id"), nullable=False, index=True)
    score = db.Column(db.Numeric(6, 2), nullable=False)

    entered_by_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=True)
    entered_at = db.Column(db.DateTime, nullable=False, default=utc_now)
    updated_at = db.Column(db.DateTime, nullable=False, default=utc_now, onupdate=utc_now)

    __table_args__ = (
        db.UniqueConstraint(
            "enrollment_id", "grade_category_id", "term_id",
            name="uq_grade_entry_triple",
        ),
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "enrollmentId": self.enrollment_id,
            "gradeCategoryId": self.grade_category_id,
            "termId": self.term_id,
            "score": float(self.score),
            "enteredById": self.entered_by_id,
            "enteredAt": _iso(self.entered_at),
            "updatedAt": _iso(self.updated_at),
        }


class GradeEntryHistory(db.Model):
    """Audit row for every grade-entry mutation."""
    __tablename__ = "grade_entry_history"

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    grade_entry_id = db.Column(db.String(36), db.ForeignKey("grade_entries.id"), nullable=False, index=True)
    old_score = db.Column(db.Numeric(6, 2), nullable=True)  # null on first insert
    new_score = db.Column(db.Numeric(6, 2), nullable=False)
    reason = db.Column(db.String(500), nullable=True)
    changed_by_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=True)
    changed_at = db.Column(db.DateTime, nullable=False, default=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "gradeEntryId": self.grade_entry_id,
            "oldScore": float(self.old_score) if self.old_score is not None else None,
            "newScore": float(self.new_score),
            "reason": self.reason,
            "changedById": self.changed_by_id,
            "changedAt": _iso(self.changed_at),
        }


class GradingScaleBand(db.Model):
    """Admin-editable percentage-to-letter-grade-to-GPA mapping."""
    __tablename__ = "grading_scale_bands"

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    min_percent = db.Column(db.Integer, nullable=False)
    max_percent = db.Column(db.Integer, nullable=False)
    letter = db.Column(db.String(8), nullable=False, unique=True)
    gpa_value = db.Column(db.Numeric(4, 2), nullable=False)
    order_index = db.Column(db.Integer, nullable=False, default=0)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "minPercent": self.min_percent,
            "maxPercent": self.max_percent,
            "letter": self.letter,
            "gpaValue": float(self.gpa_value),
            "orderIndex": self.order_index,
        }


# =============================================================================
# Phase 4 — Quizzes
# =============================================================================

QUIZ_QUESTION_TYPES = ("mc_single", "mc_multi", "true_false", "short_answer", "essay")
QUIZ_SCORING_MODES = ("best", "latest", "average", "first")


class Quiz(db.Model):
    __tablename__ = "quizzes"

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    module_id = db.Column(db.String(36), db.ForeignKey("modules.id"), nullable=False, index=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False, default="")

    passing_score = db.Column(db.Integer, nullable=False, default=60)  # percent 0-100
    max_attempts = db.Column(db.Integer, nullable=True)  # null = unlimited
    scoring_mode = db.Column(db.String(20), nullable=False, default="best")

    time_limit_minutes = db.Column(db.Integer, nullable=True)
    available_from = db.Column(db.DateTime, nullable=True)
    available_until = db.Column(db.DateTime, nullable=True)

    is_published = db.Column(db.Boolean, nullable=False, default=False)
    # Phase 24 — when set, `start_attempt` picks this many random
    # QuestionBankItem rows from the course's bank instead of using the
    # quiz's own hand-written `questions`. Existing quizzes leave this
    # null and behave unchanged.
    pool_size = db.Column(db.Integer, nullable=True)
    created_by_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=utc_now, onupdate=utc_now
    )

    module = db.relationship("Module")
    questions = db.relationship(
        "QuizQuestion",
        backref="quiz",
        lazy="dynamic",
        cascade="all, delete-orphan",
        order_by="QuizQuestion.order_index",
    )
    attempts = db.relationship(
        "QuizAttempt", backref="quiz", lazy="dynamic", cascade="all, delete-orphan"
    )

    def total_points(self) -> int:
        return sum(q.points for q in self.questions)

    def to_dict(self, *, include_questions: bool = False, hide_answers: bool = True) -> dict[str, Any]:
        data: dict[str, Any] = {
            "id": self.id,
            "moduleId": self.module_id,
            "title": self.title,
            "description": self.description,
            "passingScore": self.passing_score,
            "maxAttempts": self.max_attempts,
            "scoringMode": self.scoring_mode,
            "timeLimitMinutes": self.time_limit_minutes,
            "availableFrom": _iso(self.available_from),
            "availableUntil": _iso(self.available_until),
            "isPublished": self.is_published,
            "totalPoints": self.total_points(),
            "createdAt": _iso(self.created_at),
        }
        if include_questions:
            data["questions"] = [
                q.to_dict(hide_answers=hide_answers)
                for q in self.questions.order_by(QuizQuestion.order_index).all()
            ]
        return data


class QuizQuestion(db.Model):
    __tablename__ = "quiz_questions"

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    quiz_id = db.Column(db.String(36), db.ForeignKey("quizzes.id"), nullable=False, index=True)
    order_index = db.Column(db.Integer, nullable=False, default=0)
    type = db.Column(db.String(20), nullable=False, default="mc_single")
    prompt = db.Column(db.Text, nullable=False)
    points = db.Column(db.Integer, nullable=False, default=1)
    required = db.Column(db.Boolean, nullable=False, default=True)

    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=utc_now, onupdate=utc_now
    )

    options = db.relationship(
        "QuizOption",
        backref="question",
        lazy="dynamic",
        cascade="all, delete-orphan",
        order_by="QuizOption.order_index",
    )
    acceptable_answers = db.relationship(
        "QuizAcceptableAnswer",
        backref="question",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )

    def to_dict(self, *, hide_answers: bool = True) -> dict[str, Any]:
        data: dict[str, Any] = {
            "id": self.id,
            "quizId": self.quiz_id,
            "orderIndex": self.order_index,
            "type": self.type,
            "prompt": self.prompt,
            "points": self.points,
            "required": self.required,
        }
        if self.type in ("mc_single", "mc_multi", "true_false"):
            data["options"] = [
                o.to_dict(hide_correct=hide_answers)
                for o in self.options.order_by(QuizOption.order_index).all()
            ]
        elif self.type == "short_answer":
            if not hide_answers:
                data["acceptableAnswers"] = [
                    {"text": a.text, "caseSensitive": a.case_sensitive}
                    for a in self.acceptable_answers.all()
                ]
        # essay: nothing extra
        return data


class QuizOption(db.Model):
    __tablename__ = "quiz_options"

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    question_id = db.Column(db.String(36), db.ForeignKey("quiz_questions.id"), nullable=False, index=True)
    order_index = db.Column(db.Integer, nullable=False, default=0)
    text = db.Column(db.Text, nullable=False)
    is_correct = db.Column(db.Boolean, nullable=False, default=False)

    def to_dict(self, *, hide_correct: bool = True) -> dict[str, Any]:
        data: dict[str, Any] = {
            "id": self.id,
            "questionId": self.question_id,
            "orderIndex": self.order_index,
            "text": self.text,
        }
        if not hide_correct:
            data["isCorrect"] = self.is_correct
        return data


class QuizAcceptableAnswer(db.Model):
    __tablename__ = "quiz_acceptable_answers"

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    question_id = db.Column(db.String(36), db.ForeignKey("quiz_questions.id"), nullable=False, index=True)
    text = db.Column(db.String(500), nullable=False)
    case_sensitive = db.Column(db.Boolean, nullable=False, default=False)


class QuizAttempt(db.Model):
    __tablename__ = "quiz_attempts"

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    quiz_id = db.Column(db.String(36), db.ForeignKey("quizzes.id"), nullable=False, index=True)
    student_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False, index=True)
    enrollment_id = db.Column(db.String(36), db.ForeignKey("enrollments.id"), nullable=False, index=True)

    started_at = db.Column(db.DateTime, nullable=False, default=utc_now)
    submitted_at = db.Column(db.DateTime, nullable=True)
    attempt_number = db.Column(db.Integer, nullable=False, default=1)

    auto_score = db.Column(db.Numeric(6, 2), nullable=True)
    manual_score = db.Column(db.Numeric(6, 2), nullable=True)
    final_score = db.Column(db.Numeric(6, 2), nullable=True)
    max_score = db.Column(db.Numeric(6, 2), nullable=False)

    passed = db.Column(db.Boolean, nullable=False, default=False)
    needs_manual_review = db.Column(db.Boolean, nullable=False, default=False)

    __table_args__ = (
        db.UniqueConstraint(
            "quiz_id", "student_id", "attempt_number", name="uq_attempt_triple"
        ),
    )

    student = db.relationship("User", foreign_keys=[student_id])
    enrollment = db.relationship("Enrollment", foreign_keys=[enrollment_id])
    answer_entries = db.relationship(
        "QuizAnswerEntry",
        backref="attempt",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )

    @property
    def in_progress(self) -> bool:
        return self.submitted_at is None

    def to_dict(self, *, include_answers: bool = False, hide_correct: bool = True) -> dict[str, Any]:
        data: dict[str, Any] = {
            "id": self.id,
            "quizId": self.quiz_id,
            "studentId": self.student_id,
            "startedAt": _iso(self.started_at),
            "submittedAt": _iso(self.submitted_at),
            "attemptNumber": self.attempt_number,
            "autoScore": float(self.auto_score) if self.auto_score is not None else None,
            "manualScore": float(self.manual_score) if self.manual_score is not None else None,
            "finalScore": float(self.final_score) if self.final_score is not None else None,
            "maxScore": float(self.max_score),
            "passed": self.passed,
            "needsManualReview": self.needs_manual_review,
        }
        if include_answers:
            data["answers"] = [
                e.to_dict() for e in self.answer_entries.all()
            ]
        return data


class QuizAnswerEntry(db.Model):
    __tablename__ = "quiz_answer_entries"

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    attempt_id = db.Column(db.String(36), db.ForeignKey("quiz_attempts.id"), nullable=False, index=True)
    question_id = db.Column(db.String(36), db.ForeignKey("quiz_questions.id"), nullable=False, index=True)

    response_text = db.Column(db.Text, nullable=True)
    selected_option_ids = db.Column(db.Text, nullable=True)  # JSON array

    per_question_score = db.Column(db.Numeric(6, 2), nullable=True)
    is_manually_graded = db.Column(db.Boolean, nullable=False, default=False)
    manual_feedback = db.Column(db.Text, nullable=True)

    __table_args__ = (
        db.UniqueConstraint("attempt_id", "question_id", name="uq_answer_per_question"),
    )

    def to_dict(self) -> dict[str, Any]:
        import json as _json
        selected: list = []
        if self.selected_option_ids:
            try:
                selected = _json.loads(self.selected_option_ids)
            except Exception:
                selected = []
        return {
            "id": self.id,
            "attemptId": self.attempt_id,
            "questionId": self.question_id,
            "responseText": self.response_text,
            "selectedOptionIds": selected,
            "perQuestionScore": float(self.per_question_score) if self.per_question_score is not None else None,
            "isManuallyGraded": self.is_manually_graded,
            "manualFeedback": self.manual_feedback,
        }


class AttemptScoreOverride(db.Model):
    __tablename__ = "attempt_score_overrides"

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    attempt_id = db.Column(db.String(36), db.ForeignKey("quiz_attempts.id"), nullable=False, index=True)
    old_final_score = db.Column(db.Numeric(6, 2), nullable=True)
    new_final_score = db.Column(db.Numeric(6, 2), nullable=False)
    reason = db.Column(db.String(500), nullable=True)
    overridden_by_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=True)
    overridden_at = db.Column(db.DateTime, nullable=False, default=utc_now)


# =============================================================================
# Phase 5 — Certificates
# =============================================================================
class Certificate(db.Model):
    __tablename__ = "certificates"

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    certificate_number = db.Column(db.String(40), nullable=False, unique=True, index=True)
    enrollment_id = db.Column(
        db.String(36), db.ForeignKey("enrollments.id"),
        nullable=False, unique=True, index=True,
    )

    issued_at = db.Column(db.DateTime, nullable=False, default=utc_now)
    revoked = db.Column(db.Boolean, nullable=False, default=False)
    revoked_at = db.Column(db.DateTime, nullable=True)
    revoked_reason = db.Column(db.String(500), nullable=True)
    revoked_by_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=True)

    enrollment = db.relationship("Enrollment", foreign_keys=[enrollment_id])

    def to_dict(self, *, include_names: bool = False) -> dict[str, Any]:
        data: dict[str, Any] = {
            "id": self.id,
            "certificateNumber": self.certificate_number,
            "enrollmentId": self.enrollment_id,
            "issuedAt": _iso(self.issued_at),
            "revoked": self.revoked,
            "revokedAt": _iso(self.revoked_at),
            "revokedReason": self.revoked_reason,
        }
        if include_names and self.enrollment is not None:
            e = self.enrollment
            student = e.student
            course = e.course
            data["studentName"] = student.name if student else None
            data["studentId"] = student.id if student else None
            data["courseTitle"] = course.title if course else None
            data["courseId"] = course.id if course else None
        return data

    def public_to_dict(self) -> dict[str, Any]:
        """Restricted shape returned by the public /verify endpoint."""
        e = self.enrollment
        student = e.student if e else None
        course = e.course if e else None
        return {
            "certificateNumber": self.certificate_number,
            "studentName": student.name if student else None,
            "courseTitle": course.title if course else None,
            "issuedAt": _iso(self.issued_at),
            "revoked": self.revoked,
            "revokedAt": _iso(self.revoked_at),
            "revokedReason": self.revoked_reason if self.revoked else None,
        }


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


# =============================================================================
# Phase 14 — Assignments
#
# Module-scoped (like quizzes). Rolls up into the "assignments" grade
# category via utils.assignments.roll_up_assignment_category — same shape
# as utils.quizzes.roll_up_quiz_category. Trust-core write path fires
# maybe_issue_certificate on every grade write.
# =============================================================================
class Assignment(db.Model):
    __tablename__ = "assignments"

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    module_id = db.Column(
        db.String(36), db.ForeignKey("modules.id"), nullable=False, index=True,
    )
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False, default="")

    due_at = db.Column(db.DateTime, nullable=True)
    max_points = db.Column(db.Integer, nullable=False, default=100)
    allow_text = db.Column(db.Boolean, nullable=False, default=True)
    allow_file = db.Column(db.Boolean, nullable=False, default=True)
    is_published = db.Column(db.Boolean, nullable=False, default=False)

    # Phase 27 — group-assignment mode. When `is_group=True`, students form or
    # join an AssignmentGroup for this assignment before submitting; every
    # group member gets a shared submission and a shared grade fan-out.
    # `max_group_size` is a soft cap (NULL = no cap). The grading path
    # copies the score across every member's submission and rolls up each
    # member's enrollment independently — see grade_submission().
    is_group = db.Column(db.Boolean, nullable=False, default=False)
    max_group_size = db.Column(db.Integer, nullable=True)

    created_by_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=utc_now, onupdate=utc_now,
    )

    module = db.relationship("Module", foreign_keys=[module_id])
    submissions = db.relationship(
        "AssignmentSubmission",
        backref="assignment",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )

    def to_dict(
        self,
        *,
        include_my_submission_for: str | None = None,
        # Phase 33 fix #12 — batch escape hatch. When present,
        # skip the per-row `AssignmentSubmission.query.filter_by`
        # and read from the caller-provided
        # `{assignment_id: AssignmentSubmission}` map. Explicit None
        # value in the map is respected as "already checked, no
        # submission" so an absent entry defaults to the old lookup
        # for back-compat.
        submission_by_assignment: dict | None = None,
    ) -> dict[str, Any]:
        data: dict[str, Any] = {
            "id": self.id,
            "moduleId": self.module_id,
            "title": self.title,
            "description": self.description,
            "dueAt": _iso(self.due_at),
            "maxPoints": self.max_points,
            "allowText": self.allow_text,
            "allowFile": self.allow_file,
            "isPublished": self.is_published,
            "isGroup": self.is_group,
            "maxGroupSize": self.max_group_size,
            "createdAt": _iso(self.created_at),
            "updatedAt": _iso(self.updated_at),
        }
        if include_my_submission_for is not None:
            if submission_by_assignment is not None:
                my = submission_by_assignment.get(self.id)
            else:
                my = AssignmentSubmission.query.filter_by(
                    assignment_id=self.id,
                    student_id=include_my_submission_for,
                ).first()
            data["mySubmission"] = my.to_dict() if my else None
        return data


class AssignmentSubmission(db.Model):
    __tablename__ = "assignment_submissions"

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    assignment_id = db.Column(
        db.String(36), db.ForeignKey("assignments.id"), nullable=False, index=True,
    )
    student_id = db.Column(
        db.String(36), db.ForeignKey("users.id"), nullable=False, index=True,
    )
    enrollment_id = db.Column(
        db.String(36), db.ForeignKey("enrollments.id"), nullable=False, index=True,
    )
    submitted_at = db.Column(db.DateTime, nullable=False, default=utc_now)
    is_late = db.Column(db.Boolean, nullable=False, default=False)

    response_text = db.Column(db.Text, nullable=True)
    file_url = db.Column(db.String(1000), nullable=True)
    file_kind = db.Column(db.String(20), nullable=True)

    graded_score = db.Column(db.Numeric(6, 2), nullable=True)
    graded_max = db.Column(db.Numeric(6, 2), nullable=True)
    graded_feedback = db.Column(db.Text, nullable=True)
    graded_by_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=True)
    graded_at = db.Column(db.DateTime, nullable=True)

    # Phase 27 — group-mode. When a group-assignment submission is
    # created, we stamp `group_id` here so the grade fan-out in
    # `routes/assignments.py::grade_submission` can find every peer
    # submission with one SELECT (`WHERE group_id = ...`).
    # Solo assignments leave this NULL.
    group_id = db.Column(
        db.String(36),
        db.ForeignKey("assignment_groups.id"),
        nullable=True,
        index=True,
    )

    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=utc_now, onupdate=utc_now,
    )

    __table_args__ = (
        db.UniqueConstraint(
            "assignment_id", "student_id",
            name="uq_submission_assignment_student",
        ),
    )

    student = db.relationship("User", foreign_keys=[student_id])

    def to_dict(self, *, include_student_name: bool = False) -> dict[str, Any]:
        data: dict[str, Any] = {
            "id": self.id,
            "assignmentId": self.assignment_id,
            "studentId": self.student_id,
            "enrollmentId": self.enrollment_id,
            "submittedAt": _iso(self.submitted_at),
            "isLate": self.is_late,
            "responseText": self.response_text,
            "fileUrl": self.file_url,
            "fileKind": self.file_kind,
            "gradedScore": float(self.graded_score) if self.graded_score is not None else None,
            "gradedMax": float(self.graded_max) if self.graded_max is not None else None,
            "gradedFeedback": self.graded_feedback,
            "gradedById": self.graded_by_id,
            "gradedAt": _iso(self.graded_at),
            "groupId": self.group_id,
        }
        if include_student_name:
            s = self.student
            data["studentName"] = s.name if s else None
            data["studentEmail"] = s.email if s else None
        return data


# =============================================================================
# Phase 27 — Assignment groups (group-mode assignments)
#
# When Assignment.is_group is True, students form/join an AssignmentGroup
# scoped to that assignment before submitting. Every group member ends up
# with an AssignmentSubmission row that shares the same content + grade —
# the fan-out lives in `routes/assignments.py::grade_submission` so an
# admin can grade one submission and every group-mate's enrollment is
# rolled up in the same commit.
#
# Membership is stored per (group, student) with a unique constraint that
# also prevents a student from joining two groups for the same assignment
# (enforced at the route layer since we don't have Assignment.id on the
# member row itself — cheap to check in POST /join).
# =============================================================================
class AssignmentGroup(db.Model):
    __tablename__ = "assignment_groups"

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    assignment_id = db.Column(
        db.String(36), db.ForeignKey("assignments.id"), nullable=False, index=True,
    )
    name = db.Column(db.String(80), nullable=False)
    created_by_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)

    members = db.relationship(
        "AssignmentGroupMember",
        backref="group",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )

    def to_dict(self, *, include_members: bool = True) -> dict[str, Any]:
        data: dict[str, Any] = {
            "id": self.id,
            "assignmentId": self.assignment_id,
            "name": self.name,
            "createdById": self.created_by_id,
            "createdAt": _iso(self.created_at),
        }
        if include_members:
            members = list(self.members.all())
            data["members"] = [m.to_dict() for m in members]
            data["memberCount"] = len(members)
        return data


class AssignmentGroupMember(db.Model):
    __tablename__ = "assignment_group_members"

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    group_id = db.Column(
        db.String(36), db.ForeignKey("assignment_groups.id"), nullable=False, index=True,
    )
    student_id = db.Column(
        db.String(36), db.ForeignKey("users.id"), nullable=False, index=True,
    )
    joined_at = db.Column(db.DateTime, nullable=False, default=utc_now)

    __table_args__ = (
        db.UniqueConstraint(
            "group_id", "student_id", name="uq_group_member_group_student",
        ),
    )

    student = db.relationship("User", foreign_keys=[student_id])

    def to_dict(self) -> dict[str, Any]:
        s = self.student
        return {
            "id": self.id,
            "groupId": self.group_id,
            "studentId": self.student_id,
            "studentName": s.name if s else None,
            "joinedAt": _iso(self.joined_at),
        }


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


class Announcement(db.Model):
    __tablename__ = "announcements"

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    audience = db.Column(db.String(20), nullable=False)  # ANNOUNCEMENT_AUDIENCES
    class_id = db.Column(
        db.String(36), db.ForeignKey("classes.id"), nullable=True, index=True,
    )
    course_id = db.Column(
        db.String(36), db.ForeignKey("courses.id"), nullable=True, index=True,
    )
    author_id = db.Column(
        db.String(36), db.ForeignKey("users.id"), nullable=False, index=True,
    )
    title = db.Column(db.String(200), nullable=False)
    body = db.Column(db.Text, nullable=False, default="")
    expires_at = db.Column(db.DateTime, nullable=True)

    created_at = db.Column(db.DateTime, nullable=False, default=utc_now, index=True)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=utc_now, onupdate=utc_now,
    )

    author = db.relationship("User", foreign_keys=[author_id])
    school_class = db.relationship("SchoolClass", foreign_keys=[class_id])
    course = db.relationship("Course", foreign_keys=[course_id])

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "audience": self.audience,
            "classId": self.class_id,
            "className": self.school_class.name if self.school_class else None,
            "courseId": self.course_id,
            "courseTitle": self.course.title if self.course else None,
            "authorId": self.author_id,
            "authorName": self.author.name if self.author else None,
            "title": self.title,
            "body": self.body,
            "createdAt": _iso(self.created_at),
            "updatedAt": _iso(self.updated_at),
            "expiresAt": _iso(self.expires_at),
        }


# =============================================================================
# Phase 21 — Communication & engagement
#
# All four tables are additive and read-only from a trust-core point of view.
# The `enqueue()` helper in `utils/notifications.py` writes into
# `notifications`; the DM + comments + homework blueprints own their own
# tables. Nothing here touches enrollment, grade, or certificate state.
# =============================================================================
NOTIFICATION_KINDS = (
    "grade_updated",
    "assignment_graded",
    "certificate_issued",
    "announcement",
    "attendance_marked",
    "message",
    "comment_reply",
)


class Notification(db.Model):
    """One row per delivered event to one user's inbox.

    Idempotency (see `utils.notifications.enqueue`): a same-day duplicate
    on `(user_id, kind, ref_type, ref_id)` is suppressed so a rerun of
    a rollup pipeline doesn't spam the bell.
    """
    __tablename__ = "notifications"

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    user_id = db.Column(
        db.String(36), db.ForeignKey("users.id"), nullable=False, index=True,
    )
    kind = db.Column(db.String(40), nullable=False)  # NOTIFICATION_KINDS
    title = db.Column(db.String(200), nullable=False)
    body = db.Column(db.Text, nullable=False, default="")
    ref_type = db.Column(db.String(40), nullable=True)  # "course" | "quiz" | ...
    ref_id = db.Column(db.String(36), nullable=True)
    read_at = db.Column(db.DateTime, nullable=True, index=True)
    created_at = db.Column(
        db.DateTime, nullable=False, default=utc_now, index=True,
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "userId": self.user_id,
            "kind": self.kind,
            "title": self.title,
            "body": self.body,
            "refType": self.ref_type,
            "refId": self.ref_id,
            "readAt": _iso(self.read_at),
            "createdAt": _iso(self.created_at),
        }


class MessageThread(db.Model):
    """One thread pairs one parent with one teacher on a subject.

    Same (parent, teacher, subject) triple → same thread — the compose
    flow either creates one or replies into the existing one so the
    inbox stays tidy.
    """
    __tablename__ = "message_threads"

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    parent_id = db.Column(
        db.String(36), db.ForeignKey("users.id"), nullable=False, index=True,
    )
    teacher_id = db.Column(
        db.String(36), db.ForeignKey("users.id"), nullable=False, index=True,
    )
    subject = db.Column(db.String(200), nullable=False, default="")
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)
    last_message_at = db.Column(
        db.DateTime, nullable=False, default=utc_now, index=True,
    )

    parent = db.relationship("User", foreign_keys=[parent_id])
    teacher = db.relationship("User", foreign_keys=[teacher_id])
    messages = db.relationship(
        "Message", backref="thread", lazy="dynamic",
        cascade="all, delete-orphan",
    )

    def to_dict(self, *, viewer_id: str | None = None) -> dict[str, Any]:
        last = (
            self.messages.order_by(Message.created_at.desc()).first()
        )
        return {
            "id": self.id,
            "parentId": self.parent_id,
            "parentName": self.parent.name if self.parent else None,
            "teacherId": self.teacher_id,
            "teacherName": self.teacher.name if self.teacher else None,
            "subject": self.subject,
            "createdAt": _iso(self.created_at),
            "lastMessageAt": _iso(self.last_message_at),
            "lastMessagePreview": (last.body[:120] if last else ""),
            "hasUnreadForViewer": (
                viewer_id is not None
                and last is not None
                and last.author_id != viewer_id
                and last.read_by_other_at is None
            ),
        }


class Message(db.Model):
    __tablename__ = "messages"

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    thread_id = db.Column(
        db.String(36), db.ForeignKey("message_threads.id"), nullable=False, index=True,
    )
    author_id = db.Column(
        db.String(36), db.ForeignKey("users.id"), nullable=False, index=True,
    )
    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)
    read_by_other_at = db.Column(db.DateTime, nullable=True)

    author = db.relationship("User", foreign_keys=[author_id])

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "threadId": self.thread_id,
            "authorId": self.author_id,
            "authorName": self.author.name if self.author else None,
            "body": self.body,
            "createdAt": _iso(self.created_at),
            "readByOtherAt": _iso(self.read_by_other_at),
        }


class LessonComment(db.Model):
    """Question + one-deep answers thread under one lesson.

    `parent_comment_id` is null for a top-level question; set to the
    question's id for an answer. Author + admin can delete their own.
    """
    __tablename__ = "lesson_comments"

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    lesson_id = db.Column(
        db.String(36), db.ForeignKey("lessons.id"), nullable=False, index=True,
    )
    author_id = db.Column(
        db.String(36), db.ForeignKey("users.id"), nullable=False, index=True,
    )
    parent_comment_id = db.Column(
        db.String(36), db.ForeignKey("lesson_comments.id"), nullable=True, index=True,
    )
    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(
        db.DateTime, nullable=False, default=utc_now, index=True,
    )

    author = db.relationship("User", foreign_keys=[author_id])

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "lessonId": self.lesson_id,
            "authorId": self.author_id,
            "authorName": self.author.name if self.author else None,
            "authorRole": self.author.role if self.author else None,
            "parentCommentId": self.parent_comment_id,
            "body": self.body,
            "createdAt": _iso(self.created_at),
        }


class HomeworkPost(db.Model):
    """One post per class per school day, upserted by the homeroom teacher."""
    __tablename__ = "homework_posts"

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    class_id = db.Column(
        db.String(36), db.ForeignKey("classes.id"), nullable=False, index=True,
    )
    author_id = db.Column(
        db.String(36), db.ForeignKey("users.id"), nullable=False, index=True,
    )
    date = db.Column(db.Date, nullable=False, index=True)
    title = db.Column(db.String(200), nullable=False, default="")
    body = db.Column(db.Text, nullable=False, default="")
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=utc_now, onupdate=utc_now,
    )

    __table_args__ = (
        db.UniqueConstraint("class_id", "date", name="uq_homework_class_date"),
    )

    author = db.relationship("User", foreign_keys=[author_id])
    school_class = db.relationship("SchoolClass", foreign_keys=[class_id])

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "classId": self.class_id,
            "className": self.school_class.name if self.school_class else None,
            "authorId": self.author_id,
            "authorName": self.author.name if self.author else None,
            "date": self.date.isoformat() if self.date else None,
            "title": self.title,
            "body": self.body,
            "createdAt": _iso(self.created_at),
            "updatedAt": _iso(self.updated_at),
        }


# =============================================================================
# Phase 22 — grade history points
#
# Appended inside `utils.grading.recompute_enrollment_cache` whenever the
# cached percent moves > 0.1 or a full day has passed since the last point.
# Purely additive; a corrupt / missing series never breaks reads (the
# report card's sparkline just doesn't render).
# =============================================================================
class GradeHistoryPoint(db.Model):
    __tablename__ = "grade_history_points"

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    enrollment_id = db.Column(
        db.String(36), db.ForeignKey("enrollments.id"),
        nullable=False, index=True,
    )
    term_id = db.Column(
        db.String(36), db.ForeignKey("terms.id"), nullable=True, index=True,
    )
    cached_percent = db.Column(db.Numeric(5, 2), nullable=False)
    cached_letter = db.Column(db.String(8), nullable=True)
    recorded_at = db.Column(
        db.DateTime, nullable=False, default=utc_now, index=True,
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "enrollmentId": self.enrollment_id,
            "termId": self.term_id,
            "cachedPercent": float(self.cached_percent),
            "cachedLetter": self.cached_letter,
            "recordedAt": _iso(self.recorded_at),
        }


# =============================================================================
# Phase 23 — withdrawal log
#
# Audit trail for the "student left the school" admin action. Enrollments /
# grades / attendance / certificates are all preserved (soft-drop on
# enrollments; user.is_active=False + user.withdrawn_at set on the user
# row); this log records who did it, when, and why.
# =============================================================================
class WithdrawalLog(db.Model):
    __tablename__ = "withdrawal_log"

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    student_id = db.Column(
        db.String(36), db.ForeignKey("users.id"), nullable=False, index=True,
    )
    admin_id = db.Column(
        db.String(36), db.ForeignKey("users.id"), nullable=False,
    )
    reason = db.Column(db.String(500), nullable=True)
    effective_date = db.Column(db.Date, nullable=True)
    prior_class_id = db.Column(
        db.String(36), db.ForeignKey("classes.id"), nullable=True,
    )
    withdrawn_at = db.Column(
        db.DateTime, nullable=False, default=utc_now,
    )

    student = db.relationship("User", foreign_keys=[student_id])
    admin = db.relationship("User", foreign_keys=[admin_id])
    prior_class = db.relationship("SchoolClass", foreign_keys=[prior_class_id])

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "studentId": self.student_id,
            "studentName": self.student.name if self.student else None,
            "adminId": self.admin_id,
            "adminName": self.admin.name if self.admin else None,
            "reason": self.reason,
            "effectiveDate": (
                self.effective_date.isoformat() if self.effective_date else None
            ),
            "priorClassId": self.prior_class_id,
            "priorClassName": self.prior_class.name if self.prior_class else None,
            "withdrawnAt": _iso(self.withdrawn_at),
        }


# =============================================================================
# Phase 24 — Streaks / badges / question bank
# =============================================================================
class StudentStreak(db.Model):
    """Per-student daily-open streak. Ticked once per session-start.

    A "day" is a UTC calendar date. Consecutive days grow the streak;
    a gap of >1 day resets to 1.
    """
    __tablename__ = "student_streaks"

    user_id = db.Column(
        db.String(36), db.ForeignKey("users.id"),
        primary_key=True,
    )
    current_streak = db.Column(db.Integer, nullable=False, default=0)
    longest_streak = db.Column(db.Integer, nullable=False, default=0)
    last_activity_date = db.Column(db.Date, nullable=True)

    def to_dict(self) -> dict[str, Any]:
        return {
            "userId": self.user_id,
            "currentStreak": self.current_streak,
            "longestStreak": self.longest_streak,
            "lastActivityDate": (
                self.last_activity_date.isoformat()
                if self.last_activity_date else None
            ),
        }


class QuestionBankItem(db.Model):
    """A reusable question authored at course scope. When a Quiz sets
    `pool_size=N`, its `start_attempt` picks N random items from this
    bank instead of using its own hand-written questions.
    """
    __tablename__ = "question_bank_items"

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    course_id = db.Column(
        db.String(36), db.ForeignKey("courses.id"), nullable=False, index=True,
    )
    type = db.Column(db.String(20), nullable=False, default="mc_single")
    prompt = db.Column(db.Text, nullable=False)
    points = db.Column(db.Integer, nullable=False, default=1)
    created_by_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)

    options = db.relationship(
        "QuestionBankOption", backref="bank_item", lazy="dynamic",
        cascade="all, delete-orphan", order_by="QuestionBankOption.order_index",
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "courseId": self.course_id,
            "type": self.type,
            "prompt": self.prompt,
            "points": self.points,
            "options": [o.to_dict() for o in self.options.all()],
            "createdAt": _iso(self.created_at),
        }


class QuestionBankOption(db.Model):
    __tablename__ = "question_bank_options"

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    bank_item_id = db.Column(
        db.String(36), db.ForeignKey("question_bank_items.id"),
        nullable=False, index=True,
    )
    order_index = db.Column(db.Integer, nullable=False, default=0)
    text = db.Column(db.String(500), nullable=False)
    is_correct = db.Column(db.Boolean, nullable=False, default=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "bankItemId": self.bank_item_id,
            "orderIndex": self.order_index,
            "text": self.text,
            "isCorrect": self.is_correct,
        }


# =============================================================================
# Phase 28 — Web Push subscriptions
#
# One row per (user, browser session). Endpoint + p256dh + auth are the
# opaque strings the browser Push API returns; the backend signs a VAPID
# JWT and POSTs to `endpoint` to deliver a notification. `platform` is
# forward-looking — always 'web' this phase, kept as a column so a
# future mobile FCM sub can plug in without a migration.
#
# Trust-core: touches no grade or enrollment state. Best-effort delivery
# only; stale endpoints (410 from the push service) are auto-pruned.
# =============================================================================
class PushSubscription(db.Model):
    __tablename__ = "push_subscriptions"

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    user_id = db.Column(
        db.String(36), db.ForeignKey("users.id"), nullable=False, index=True,
    )
    endpoint = db.Column(db.String(1000), nullable=False)
    p256dh = db.Column(db.String(200), nullable=False)
    auth = db.Column(db.String(80), nullable=False)
    user_agent = db.Column(db.String(400), nullable=True)
    platform = db.Column(db.String(20), nullable=False, default="web")
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)
    last_seen_at = db.Column(db.DateTime, nullable=False, default=utc_now)

    __table_args__ = (
        db.UniqueConstraint(
            "user_id", "endpoint", name="uq_push_user_endpoint",
        ),
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "userId": self.user_id,
            "endpoint": self.endpoint,
            "platform": self.platform,
            "userAgent": self.user_agent,
            "createdAt": _iso(self.created_at),
            "lastSeenAt": _iso(self.last_seen_at),
        }


# =============================================================================
# Phase 28 — Fee tracking + payments
#
# `FeeItem` = one line item owed by a student (tuition, activity fee,
# uniform, trip). Admin creates + updates; student + linked parents
# read only their own.
# `FeePayment` = one payment against a fee item. A fee can have multiple
# payments (partial payment support) — the balance is
# `amount - sum(payments.amount)`. Admin logs payments; students +
# parents read them (no write).
#
# Trust-core: fees do NOT gate grading, certificates, or enrollment.
# The read path never joins across those tables; the write path stays
# admin-only. Receipts render via `utils/pdf.py::render_fees_pdf`.
# =============================================================================
class FeeItem(db.Model):
    __tablename__ = "fee_items"

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    student_id = db.Column(
        db.String(36), db.ForeignKey("users.id"), nullable=False, index=True,
    )
    label = db.Column(db.String(200), nullable=False)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    currency = db.Column(db.String(8), nullable=False, default="USD")
    due_date = db.Column(db.Date, nullable=True)
    notes = db.Column(db.String(500), nullable=True)
    created_by_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=utc_now, onupdate=utc_now,
    )

    payments = db.relationship(
        "FeePayment", backref="fee_item", lazy="dynamic",
        cascade="all, delete-orphan",
    )

    def paid_amount(self) -> Decimal:
        total = Decimal("0")
        for p in self.payments.all():
            total += p.amount or Decimal("0")
        return total

    def balance(self) -> Decimal:
        return (self.amount or Decimal("0")) - self.paid_amount()

    def to_dict(self, *, include_payments: bool = True) -> dict[str, Any]:
        data: dict[str, Any] = {
            "id": self.id,
            "studentId": self.student_id,
            "label": self.label,
            "amount": float(self.amount) if self.amount is not None else 0.0,
            "currency": self.currency,
            "dueDate": self.due_date.isoformat() if self.due_date else None,
            "notes": self.notes,
            "createdAt": _iso(self.created_at),
            "updatedAt": _iso(self.updated_at),
            "paidAmount": float(self.paid_amount()),
            "balance": float(self.balance()),
        }
        if include_payments:
            data["payments"] = [p.to_dict() for p in self.payments.all()]
        return data


class FeePayment(db.Model):
    __tablename__ = "fee_payments"

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    fee_item_id = db.Column(
        db.String(36), db.ForeignKey("fee_items.id"), nullable=False, index=True,
    )
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    paid_at = db.Column(db.DateTime, nullable=False, default=utc_now)
    method = db.Column(db.String(40), nullable=True)  # cash / card / bank / etc.
    note = db.Column(db.String(500), nullable=True)
    logged_by_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "feeItemId": self.fee_item_id,
            "amount": float(self.amount) if self.amount is not None else 0.0,
            "paidAt": _iso(self.paid_at),
            "method": self.method,
            "note": self.note,
            "loggedById": self.logged_by_id,
            "createdAt": _iso(self.created_at),
        }


# =============================================================================
# Phase 32 · T1 — Notification preferences
#
# One row per (user, kind). Absence of a row means "enabled" (the
# default) so a freshly-registered user gets the bell for everything
# without a seed step. `utils/notifications.enqueue` reads this table
# and skips the write when the user has opted out — the trust-core
# grade/attendance/assignment write pipelines never care.
#
# `kind` is the same string used everywhere `enqueue()` is called
# today: "grade_posted", "assignment_graded", "fee_created",
# "fee_payment", "fee_overdue", "announcement", "message", "quiz_due",
# "attendance_absent", "streak_reminder", "cert_issued". Unknown kinds
# are always allowed (fail-open) so a new notification type ships
# without a per-user opt-in flag day.
# =============================================================================
# Kinds a user can opt out of. Kept as a plain tuple (not a Column
# constraint) because the enqueue writer must fail-open on unknown
# kinds — we never want to lose a new notification type behind a
# stale allow-list.
NOTIFICATION_KINDS = (
    "grade_posted", "assignment_graded",
    "fee_created", "fee_payment", "fee_overdue",
    "announcement", "message", "quiz_due",
    "attendance_absent", "streak_reminder", "cert_issued",
)


class NotificationPreference(db.Model):
    __tablename__ = "notification_preferences"

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    user_id = db.Column(
        db.String(36), db.ForeignKey("users.id"),
        nullable=False, index=True,
    )
    kind = db.Column(db.String(40), nullable=False)
    enabled = db.Column(db.Boolean, nullable=False, default=True)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=utc_now,
        onupdate=utc_now,
    )

    __table_args__ = (
        db.UniqueConstraint("user_id", "kind", name="uq_notif_pref_user_kind"),
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "userId": self.user_id,
            "kind": self.kind,
            "enabled": self.enabled,
            "updatedAt": _iso(self.updated_at),
        }


# =============================================================================
# Phase 32 · T2 — Digital diploma
#
# One row per (student, class_of_year). Issued automatically when a
# student is bulk-graduated (see `routes/students.py::bulk_graduate...`).
# Similar shape to `Certificate` but scoped to the whole graduation,
# not a single course:
#   * `diploma_number` is a public verify-able id (like the certificate).
#   * `honors` is a soft attribute ("valedictorian", "salutatorian",
#     "cum laude"...) admins can set post-issuance; nullable.
#   * `revoked` mirrors `Certificate.revoked` — admins can revoke
#     with a reason, and `/api/verify-diploma/<num>` reflects the state.
#
# Trust-core: no writes to grades, enrollments, or certificates. Issue
# reads the student's enrollments + certs at graduation time to fill
# in `total_certificates` / `average_percent` snapshots (denormalised
# on this row so the PDF is deterministic even if later cert-revokes
# change the underlying totals).
# =============================================================================
DIPLOMA_HONORS = (
    "valedictorian", "salutatorian",
    "summa_cum_laude", "magna_cum_laude", "cum_laude",
)


class Diploma(db.Model):
    __tablename__ = "diplomas"

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    diploma_number = db.Column(
        db.String(40), nullable=False, unique=True, index=True,
    )
    student_id = db.Column(
        db.String(36), db.ForeignKey("users.id"),
        nullable=False, index=True,
    )
    grade_id = db.Column(
        db.String(36), db.ForeignKey("grades.id"), nullable=True,
    )
    class_of_year = db.Column(db.Integer, nullable=False)
    issued_at = db.Column(db.DateTime, nullable=False, default=utc_now)
    honors = db.Column(db.String(40), nullable=True)
    # Denormalised snapshot at issuance — the PDF is deterministic even
    # if certificates are later revoked or grades edited.
    total_certificates = db.Column(db.Integer, nullable=False, default=0)
    average_percent = db.Column(db.Numeric(5, 2), nullable=True)
    revoked = db.Column(db.Boolean, nullable=False, default=False)
    revoked_at = db.Column(db.DateTime, nullable=True)
    revoked_reason = db.Column(db.String(500), nullable=True)
    revoked_by_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=True)

    __table_args__ = (
        db.UniqueConstraint(
            "student_id", "class_of_year",
            name="uq_diploma_student_year",
        ),
    )

    def to_dict(self, *, include_student: bool = False) -> dict[str, Any]:
        data: dict[str, Any] = {
            "id": self.id,
            "diplomaNumber": self.diploma_number,
            "studentId": self.student_id,
            "gradeId": self.grade_id,
            "classOfYear": self.class_of_year,
            "issuedAt": _iso(self.issued_at),
            "honors": self.honors,
            "totalCertificates": self.total_certificates,
            "averagePercent": (
                float(self.average_percent)
                if self.average_percent is not None else None
            ),
            "revoked": self.revoked,
            "revokedAt": _iso(self.revoked_at),
            "revokedReason": self.revoked_reason,
        }
        if include_student:
            s = db.session.get(User, self.student_id)
            data["studentName"] = s.name if s else None
            data["studentEmail"] = s.email if s else None
        return data


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
