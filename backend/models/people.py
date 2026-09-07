"""Accounts, the parent-student link, and the withdrawal audit log."""
from __future__ import annotations

from models.base import (
    db,
    generate_uuid,
    utc_now,
    _iso,
    password_hash_kwargs,
    Any,
    check_password_hash,
    generate_password_hash,
)

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
    # Set whenever someone OTHER than the account holder chose the password —
    # the CSV bulk import and the admin password reset. The client is expected
    # to route the user straight to the change-password screen on their next
    # sign-in; cleared by `POST /api/auth/password`.
    must_change_password = db.Column(db.Boolean, nullable=False, default=False)
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
        self.password_hash = generate_password_hash(raw_password, **password_hash_kwargs())

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
            "mustChangePassword": bool(self.must_change_password),
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
