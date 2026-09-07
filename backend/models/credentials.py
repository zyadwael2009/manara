"""Awards a student can be issued: course certificates and the end-of-school diploma."""
from __future__ import annotations

from models.base import (
    db,
    generate_uuid,
    utc_now,
    _iso,
    Any,
)

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
            from models.people import User
            s = db.session.get(User, self.student_id)
            data["studentName"] = s.name if s else None
            data["studentEmail"] = s.email if s else None
        return data
