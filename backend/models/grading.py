"""School years and terms, the per-course rubric, grade entries and their history, and the letter/GPA scale."""
from __future__ import annotations

from models.base import (
    db,
    generate_uuid,
    utc_now,
    _iso,
    Any,
)

# =============================================================================
# Phase 3 — Progress + Grading
# =============================================================================

# Grade-entry status constants
GRADE_ENTRY_MAX = 100  # sanity ceiling; per-category max is course_rubric.max_score


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
