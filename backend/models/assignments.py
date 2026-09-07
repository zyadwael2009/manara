"""Assignments, submissions, and group-mode membership."""
from __future__ import annotations

from models.base import (
    db,
    generate_uuid,
    utc_now,
    _iso,
    Any,
)

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
