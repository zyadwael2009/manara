"""Phase 12 — attendance rollup into the Commitment grade category.

Every attendance write fires `roll_up_to_commitment(student, term_id)`
which recomputes the student's Commitment score on every active
enrollment. Same trust-core shape as `utils/quizzes.py:roll_up_quiz_category`
— idempotent, called inside the same transaction as the write, downstream
`recompute_enrollment_cache` + `maybe_issue_certificate` follow.

School-day model: a "school day" is any date the student has at least
one attendance mark for. Days with no mark aren't school days for that
student. This means new schools (no attendance history yet) don't
compute weirdly low Commitment scores — they just don't roll up.
"""
from __future__ import annotations

from datetime import date as _date
from decimal import Decimal
from typing import Optional

from models import (
    AttendanceMark,
    CourseRubric,
    Enrollment,
    GradeCategory,
    GradeEntry,
    User,
    db,
)


_COMMITMENT_SLUG = "commitment"
_ATTENDING_STATUSES = ("present", "excused")  # both count as "in-attendance"


def _school_days_for(
    student: User, since: Optional[_date] = None
) -> tuple[int, int]:
    """(school_days, present_or_excused_days). See module docstring."""
    q = AttendanceMark.query.filter_by(student_id=student.id)
    if since is not None:
        q = q.filter(AttendanceMark.date >= since)
    marks = q.all()
    school = len(marks)
    good = sum(1 for m in marks if m.status in _ATTENDING_STATUSES)
    return school, good


def roll_up_to_commitment(
    student: User, term_id: Optional[str] = None
) -> None:
    """Recompute Commitment for every active enrollment of `student`.

    Skips silently when the student has no attendance history (no rows
    to roll from) or when the course doesn't have a Commitment line in
    its rubric.
    """
    if student is None:
        return
    school_days, good_days = _school_days_for(student)
    if school_days == 0:
        return
    frac = good_days / school_days

    commitment_cat = GradeCategory.query.filter_by(slug=_COMMITMENT_SLUG).first()
    if commitment_cat is None:
        return

    if term_id is None:
        from utils.quizzes import _current_term_id
        term_id = _current_term_id()
    if term_id is None:
        return

    enrollments = (
        Enrollment.query.filter_by(student_id=student.id)
        .filter(Enrollment.status.in_(("active", "completed")))
        .all()
    )
    for e in enrollments:
        rubric = CourseRubric.query.filter_by(
            course_id=e.course_id, grade_category_id=commitment_cat.id,
        ).first()
        if rubric is None:
            continue
        max_score = int(rubric.max_score)
        score = round(frac * max_score, 2)

        entry = GradeEntry.query.filter_by(
            enrollment_id=e.id,
            grade_category_id=commitment_cat.id,
            term_id=term_id,
        ).first()
        if entry is None:
            entry = GradeEntry(
                enrollment_id=e.id,
                grade_category_id=commitment_cat.id,
                term_id=term_id,
                score=Decimal(str(score)),
            )
            db.session.add(entry)
        else:
            entry.score = Decimal(str(score))


# ---------------------------------------------------------------------------
# Phase 18 — per-student attendance summary projection
#
# Attendance is stored per (student, date) at the CLASS level (a student is
# in one homeroom class; a class marks the day for everyone in it). So the
# summary is one number per student, not per course. We still surface it on
# each of the student's course-detail responses because that's where they
# actually look ("how's my English 9 course going?" → they see attendance
# alongside progress + grade).
# ---------------------------------------------------------------------------
def compute_student_attendance_summary(student_id: str) -> dict:
    """Return `{present, absent, late, excused, total, percent}` — where
    `percent` is (present+excused)/total × 100, matching the
    `_ATTENDING_STATUSES` rule the Commitment rollup uses.

    Absent students (no marks yet) get `total=0, percent=None` — the
    caller decides how to render "no history yet".
    """
    rows = AttendanceMark.query.filter_by(student_id=student_id).all()
    total = len(rows)
    buckets = {"present": 0, "absent": 0, "late": 0, "excused": 0}
    for m in rows:
        if m.status in buckets:
            buckets[m.status] += 1
    good = buckets["present"] + buckets["excused"]
    percent = round(good / total * 100.0, 1) if total > 0 else None
    return {
        "present": buckets["present"],
        "absent": buckets["absent"],
        "late": buckets["late"],
        "excused": buckets["excused"],
        "total": total,
        "percent": percent,
    }
