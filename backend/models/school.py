"""The school's shape: sections, grades, classes, and the two ways a teacher is attached to them."""
from __future__ import annotations

from models.base import (
    db,
    generate_uuid,
    utc_now,
    _iso,
    Any,
)

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
    # `use_alter` breaks the classes <-> users FK cycle (users.class_id points
    # back here). Without it SQLAlchemy can't topologically sort the tables and
    # emits `SAWarning: Can't sort tables for DROP` on every teardown; on a
    # backend that creates constraints inline it would fail outright. Naming
    # the constraint is required for `use_alter` to emit valid DDL.
    homeroom_teacher_id = db.Column(
        db.String(36),
        db.ForeignKey(
            "users.id", use_alter=True, name="fk_classes_homeroom_teacher_id"
        ),
        nullable=True,
        unique=True,
        index=True,
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
