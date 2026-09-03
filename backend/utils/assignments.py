"""Phase 14 — assignments grade-category rollup.

Same shape as `utils/quizzes.py:roll_up_quiz_category`. Called from
every write path that could shift a student's "Assignments" total:
`PUT /submissions/<id>/grade` and `POST /assignments/<id>/unpublish`.
Idempotent; upserts a single GradeEntry per (enrollment, term).
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from models import (
    Assignment,
    AssignmentSubmission,
    CourseRubric,
    Enrollment,
    GradeCategory,
    GradeEntry,
    db,
)
from utils.time import utc_now


_ASSIGNMENTS_SLUG = "assignments"


def roll_up_assignment_category(
    enrollment: Enrollment, term_id: Optional[str] = None
) -> None:
    """Recompute the student's Assignments grade_entry for this course × term.

    Formula:
        rollup_score = (Σ graded_score across student's submissions)
                     / (Σ max_points across every PUBLISHED assignment in course)
                     × rubric[Assignments].max_score

    Ungraded submissions contribute 0 to the numerator. Assignments with
    no submission from this student contribute 0 to the numerator too —
    the student is "missing an assignment", not "excused from it".
    """
    course = enrollment.course
    if course is None:
        return
    cat = GradeCategory.query.filter_by(slug=_ASSIGNMENTS_SLUG).first()
    if cat is None:
        return
    rubric = CourseRubric.query.filter_by(
        course_id=course.id, grade_category_id=cat.id,
    ).first()
    if rubric is None:
        return
    if term_id is None:
        from utils.quizzes import _current_term_id
        term_id = _current_term_id()
    if term_id is None:
        return

    # Denominator: sum of max_points across every published assignment in
    # every module of the course.
    # Phase 33 fix #13 — was O(assignments) queries: one Assignment
    # query per module + one AssignmentSubmission query per assignment.
    # Called from every submit + every grade write, so a course with
    # 8 modules × 10 assignments was 90+ SELECTs per rollup. Now two
    # queries: one joined Assignment fetch + one batched submission
    # fetch for the student across the assignment ids.
    published = _published_assignments_in_course(course)
    if not published:
        return
    possible = float(sum(a.max_points for a in published))
    if possible <= 0:
        return

    # Numerator: this student's graded scores across those assignments.
    assignment_ids = [a.id for a in published]
    submissions = AssignmentSubmission.query.filter(
        AssignmentSubmission.assignment_id.in_(assignment_ids),
        AssignmentSubmission.student_id == enrollment.student_id,
    ).all()
    earned = 0.0
    for sub in submissions:
        if sub.graded_score is None:
            continue
        earned += float(sub.graded_score)

    category_max = int(rubric.max_score)
    rolled = round((earned / possible) * category_max, 2)

    entry = GradeEntry.query.filter_by(
        enrollment_id=enrollment.id,
        grade_category_id=cat.id,
        term_id=term_id,
    ).first()
    if entry is None:
        entry = GradeEntry(
            enrollment_id=enrollment.id,
            grade_category_id=cat.id,
            term_id=term_id,
            score=Decimal(str(rolled)),
        )
        db.session.add(entry)
    else:
        entry.score = Decimal(str(rolled))
        entry.updated_at = utc_now()


def _published_assignments_in_course(course) -> list[Assignment]:
    """Every published assignment across every module of `course`.

    Phase 33 fix #13 — was O(modules) queries; now one JOIN.
    """
    from models import Module as _Module
    return (
        Assignment.query
        .join(_Module, _Module.id == Assignment.module_id)
        .filter(_Module.course_id == course.id)
        .filter(Assignment.is_published.is_(True))
        .all()
    )
