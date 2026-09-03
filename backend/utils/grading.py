"""Grade aggregation engine — the ONE place that turns raw grade_entries
into percentages, letter grades, GPAs, and per-term cumulatives.

Everything else reads the cached values from `enrollments.cached_*`.
This module is called from grade-entry writes and rubric changes to
recompute the cache transactionally.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from models import (
    CourseRubric,
    Enrollment,
    GradeEntry,
    GradingScaleBand,
    Term,
    db,
)
from utils.time import utc_now


# ---------------------------------------------------------------------------
# Letter-grade + GPA lookup
# ---------------------------------------------------------------------------
def band_for_percent(pct: float) -> Optional[GradingScaleBand]:
    """Find the grading-scale band that contains `pct`."""
    if pct is None:
        return None
    # Rounded to integer for the band lookup — bands are integer bounds.
    p = int(round(pct))
    return GradingScaleBand.query.filter(
        GradingScaleBand.min_percent <= p,
        GradingScaleBand.max_percent >= p,
    ).first()


# ---------------------------------------------------------------------------
# Per-enrollment percentage (running average of graded categories)
# ---------------------------------------------------------------------------
def compute_enrollment_percentage(enrollment: Enrollment, term_id: Optional[str] = None) -> Optional[float]:
    """Return the student's running percentage for this enrollment.

    Formula per plan: sum(score) / sum(rubric.max_score for categories that
    have an entry) × 100. Ungraded categories are excluded (running average).

    If `term_id` is given, only that term's entries count. Otherwise, every
    term's entries are folded (used for year rollups).

    Returns None if there are zero graded categories (report card shows '—').
    """
    course_id = enrollment.course_id
    # Fetch rubric rows for this course.
    rubric_rows = CourseRubric.query.filter_by(course_id=course_id).all()
    if not rubric_rows:
        return None
    max_by_cat = {r.grade_category_id: int(r.max_score) for r in rubric_rows}

    q = GradeEntry.query.filter_by(enrollment_id=enrollment.id)
    if term_id is not None:
        q = q.filter(GradeEntry.term_id == term_id)
    entries = q.all()
    if not entries:
        return None

    earned = Decimal("0")
    possible = Decimal("0")
    for e in entries:
        max_score = max_by_cat.get(e.grade_category_id)
        if max_score is None:
            continue  # entry against a category no longer in the rubric
        earned += Decimal(str(e.score))
        possible += Decimal(str(max_score))
    if possible == 0:
        return None
    return float((earned / possible * Decimal("100")).quantize(Decimal("0.01")))


# ---------------------------------------------------------------------------
# Cache write — call after any grade-entry / rubric change
# ---------------------------------------------------------------------------
def recompute_enrollment_cache(enrollment: Enrollment, term_id: Optional[str] = None) -> None:
    """Recompute cached_percent / cached_letter / cached_gpa and persist.

    Uses the current-term entries only. Reads never re-aggregate — they
    trust these cache values.
    """
    if term_id is None:
        # Default to the current term of the current school year, if any.
        from models import SchoolYear
        year = SchoolYear.query.filter_by(is_current=True).first()
        if year is not None:
            current_term = (
                Term.query.filter_by(school_year_id=year.id)
                .order_by(Term.order_index.asc())
                .first()
            )
            term_id = current_term.id if current_term else None

    old_letter = enrollment.cached_letter
    pct = compute_enrollment_percentage(enrollment, term_id=term_id) if term_id else None
    if pct is None:
        enrollment.cached_percent = None
        enrollment.cached_letter = None
        enrollment.cached_gpa = None
    else:
        band = band_for_percent(pct)
        enrollment.cached_percent = Decimal(str(pct))
        enrollment.cached_letter = band.letter if band else None
        enrollment.cached_gpa = band.gpa_value if band else None
    enrollment.cached_computed_at = utc_now()

    # Phase 21 — bell notification when the letter grade actually changes.
    # Skips the "no change" spam that every rollup would otherwise trigger.
    new_letter = enrollment.cached_letter
    if new_letter is not None and new_letter != old_letter:
        from utils.notifications import enqueue
        course_title = enrollment.course.title if enrollment.course else "Your course"
        enqueue(
            enrollment.student_id,
            kind="grade_updated",
            title=f"Grade updated: {course_title}",
            body=f"Now {new_letter}"
                 + (f" ({float(enrollment.cached_percent):.1f}%)"
                    if enrollment.cached_percent is not None else ""),
            ref_type="course",
            ref_id=enrollment.course_id,
        )

    # Phase 22 — append a grade-history point. Local imports so tests that
    # reset `sys.modules` between fixtures always see the current app's db.
    if enrollment.cached_percent is not None:
        from models import GradeHistoryPoint, db as _db
        from decimal import Decimal as _Dec
        last = (
            GradeHistoryPoint.query.filter_by(enrollment_id=enrollment.id)
            .order_by(GradeHistoryPoint.recorded_at.desc())
            .first()
        )
        now = utc_now()
        write_point = True
        if last is not None:
            delta = abs(float(enrollment.cached_percent) - float(last.cached_percent))
            hours_since = (now - last.recorded_at).total_seconds() / 3600.0
            # Phase 25 hard-audit fix: the throttle used to only skip
            # tiny (< 0.1) SAME-day writes, so a rubric grading spree
            # would create dozens of points per student per subject in
            # minutes. Real "one point per day" cap: skip ANY point
            # when the last one is < 24h old (unless the delta is huge,
            # which we still want to capture as a "big grade move" for
            # the trend line).
            same_day = hours_since < 24
            big_delta = delta >= 10.0
            if same_day and not big_delta:
                write_point = False
        if write_point:
            _db.session.add(GradeHistoryPoint(
                enrollment_id=enrollment.id,
                term_id=term_id,
                cached_percent=_Dec(str(enrollment.cached_percent)),
                cached_letter=enrollment.cached_letter,
                recorded_at=now,
            ))


def recompute_course_cache(course_id: str, term_id: Optional[str] = None) -> int:
    """Recompute cache for every enrollment in a course. Returns count updated."""
    n = 0
    for e in Enrollment.query.filter_by(course_id=course_id).all():
        recompute_enrollment_cache(e, term_id=term_id)
        n += 1
    return n


# ---------------------------------------------------------------------------
# Report-card cumulative (across all subjects for one student in one term)
# ---------------------------------------------------------------------------
def student_report_card(student_id: str, term_id: Optional[str] = None) -> dict:
    """Return the full report card for one student in a term.

    Shape:
    {
      termId, subjects: [
        { courseId, courseTitle, entries: {categoryId: score}, rubric: [...],
          percent, letter, gpaValue }
      ],
      cumulative: { percent, letter, gpaValue }
    }

    Cumulative percent = average of subject percents (skipping None).
    Cumulative GPA = average of subject gpa_values (skipping None).
    """
    from models import Course, GradeCategory
    enrollments = (
        Enrollment.query.filter_by(student_id=student_id)
        .filter(Enrollment.status.in_(("active", "completed")))
        .all()
    )
    subjects = []
    percents: list[float] = []
    gpas: list[float] = []
    for e in enrollments:
        course = db.session.get(Course, e.course_id)
        if course is None:
            continue
        rubric_rows = (
            CourseRubric.query.filter_by(course_id=course.id)
            .order_by(CourseRubric.order_index.asc())
            .all()
        )
        rubric_dicts = [r.to_dict() for r in rubric_rows]

        q = GradeEntry.query.filter_by(enrollment_id=e.id)
        if term_id is not None:
            q = q.filter(GradeEntry.term_id == term_id)
        entries = q.all()
        entry_by_cat = {en.grade_category_id: float(en.score) for en in entries}

        pct = compute_enrollment_percentage(e, term_id=term_id)
        band = band_for_percent(pct) if pct is not None else None
        subj = {
            "courseId": course.id,
            "courseTitle": course.title,
            "category": course.category,
            "rubric": rubric_dicts,
            "entries": entry_by_cat,
            "percent": pct,
            "letter": band.letter if band else None,
            "gpaValue": float(band.gpa_value) if band else None,
        }
        subjects.append(subj)
        if pct is not None:
            percents.append(pct)
        if band is not None:
            gpas.append(float(band.gpa_value))

    cumulative = None
    if percents:
        cum_pct = sum(percents) / len(percents)
        cum_band = band_for_percent(cum_pct)
        cumulative = {
            "percent": round(cum_pct, 2),
            "letter": cum_band.letter if cum_band else None,
            "gpaValue": round(sum(gpas) / len(gpas), 2) if gpas else None,
        }
    return {
        "termId": term_id,
        "subjects": subjects,
        "cumulative": cumulative,
    }


# ---------------------------------------------------------------------------
# Rubric-sum invariant
# ---------------------------------------------------------------------------
def validate_rubric_sum(course_id: str, items: list[dict]) -> Optional[str]:
    """Return None if the sum is 100, else an error string."""
    total = sum(int(i.get("maxScore") or 0) for i in items)
    if total != 100:
        return f"Rubric sum must equal 100; got {total}."
    return None


# ---------------------------------------------------------------------------
# Progress recalculation
# ---------------------------------------------------------------------------
def recompute_progress_percent(enrollment: Enrollment) -> None:
    """Recount completed lessons / total lessons for this enrollment's course.
    Writes enrollments.progress_percent. Called from lesson_progress writes.
    """
    from models import Course, Lesson, LessonProgress, Module
    course = db.session.get(Course, enrollment.course_id)
    if course is None:
        enrollment.progress_percent = 0
        return
    module_ids = [m.id for m in course.modules]
    if not module_ids:
        enrollment.progress_percent = 0
        return
    total = Lesson.query.filter(Lesson.module_id.in_(module_ids)).count()
    if total == 0:
        enrollment.progress_percent = 0
        return
    done = LessonProgress.query.filter_by(
        enrollment_id=enrollment.id, completed=True
    ).count()
    enrollment.progress_percent = int(round(done / total * 100))
    if enrollment.progress_percent >= 100 and enrollment.completed_at is None:
        enrollment.completed_at = utc_now()
        enrollment.status = "completed"
