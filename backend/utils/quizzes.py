"""Quiz auto-grader + grade-category rollup.

The auto-grader compares a student's answers against each question's correct
answers per its type. Essay questions are skipped (marked for manual review).

The rollup computes the student's cumulative Quizzes-category score for the
term across every quiz in the course, and writes it into `grade_entries` so
Phase 3's grading cache picks it up.
"""
from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from typing import Optional

from models import (
    CourseRubric,
    Enrollment,
    GradeCategory,
    GradeEntry,
    QuizAnswerEntry,
    QuizAttempt,
    QuizQuestion,
    QuizOption,
    Quiz,
    SchoolYear,
    Term,
    db,
)
from utils.time import utc_now


# ---------------------------------------------------------------------------
# Auto-grader
# ---------------------------------------------------------------------------
def auto_grade_attempt(attempt: QuizAttempt) -> None:
    """Set per-question scores + auto_score + final_score + passed +
    needs_manual_review on the given attempt. Does NOT commit.
    """
    quiz = attempt.quiz
    questions = list(quiz.questions.order_by(QuizQuestion.order_index).all())
    entries_by_q = {e.question_id: e for e in attempt.answer_entries.all()}

    auto_earned = Decimal("0")
    has_essay = False
    for q in questions:
        entry = entries_by_q.get(q.id)
        if entry is None:
            # Missing answer → 0 points, but record an entry so the results
            # screen shows it explicitly.
            entry = QuizAnswerEntry(attempt_id=attempt.id, question_id=q.id)
            db.session.add(entry)
        earned = _grade_question(q, entry)
        if q.type == "essay":
            has_essay = True
            # essay contributes nothing to auto_score; per_question_score stays None
            entry.per_question_score = None
        else:
            entry.per_question_score = Decimal(str(earned))
            auto_earned += Decimal(str(earned))

    attempt.auto_score = auto_earned
    # final_score = auto_score for now; manual override sets it directly.
    attempt.final_score = auto_earned
    attempt.needs_manual_review = has_essay
    attempt.passed = _passed(attempt)


def _grade_question(q: QuizQuestion, entry: QuizAnswerEntry) -> int:
    """Return raw earned points for this question (0 or q.points)."""
    if q.type in ("mc_single", "mc_multi", "true_false"):
        selected_ids = _parse_selected(entry.selected_option_ids)
        correct_ids = {
            o.id for o in q.options.filter_by(is_correct=True).all()
        }
        if set(selected_ids) == correct_ids and len(correct_ids) > 0:
            return q.points
        return 0
    if q.type == "short_answer":
        response = (entry.response_text or "").strip()
        if not response:
            return 0
        for a in q.acceptable_answers.all():
            if a.case_sensitive:
                if response == a.text.strip():
                    return q.points
            else:
                if response.lower() == a.text.strip().lower():
                    return q.points
        return 0
    # essay: not auto-graded
    return 0


def _parse_selected(raw: Optional[str]) -> list[str]:
    if not raw:
        return []
    try:
        v = json.loads(raw)
        if isinstance(v, list):
            return [str(x) for x in v]
    except Exception:
        pass
    return []


def _passed(attempt: QuizAttempt) -> bool:
    """Pass = final_score / max_score × 100 >= quiz.passing_score.

    If needs_manual_review is True, pass is provisional (essay questions
    still need scoring). We compute against current final_score as-is.
    """
    if attempt.max_score is None or attempt.max_score == 0:
        return False
    if attempt.final_score is None:
        return False
    pct = float(attempt.final_score) / float(attempt.max_score) * 100.0
    return pct >= (attempt.quiz.passing_score if attempt.quiz else 0)


# ---------------------------------------------------------------------------
# Rollup into the Quizzes grade category
# ---------------------------------------------------------------------------
_QUIZZES_SLUG = "quizzes"


def _current_term_id() -> Optional[str]:
    year = SchoolYear.query.filter_by(is_current=True).first()
    if year is None:
        return None
    t = Term.query.filter_by(school_year_id=year.id).order_by(Term.order_index.asc()).first()
    return t.id if t else None


def _best_score_by_mode(attempts: list[QuizAttempt], mode: str) -> Optional[float]:
    """Return the effective earned score for a single quiz across attempts,
    per the quiz's `scoring_mode`."""
    finalized = [a for a in attempts if a.submitted_at is not None and a.final_score is not None]
    if not finalized:
        return None
    if mode == "best":
        return float(max(a.final_score for a in finalized))
    if mode == "latest":
        latest = sorted(finalized, key=lambda a: a.submitted_at or datetime.min)[-1]
        return float(latest.final_score)
    if mode == "first":
        first = sorted(finalized, key=lambda a: a.submitted_at or datetime.min)[0]
        return float(first.final_score)
    if mode == "average":
        return sum(float(a.final_score) for a in finalized) / len(finalized)
    return float(max(a.final_score for a in finalized))  # fallback: best


def roll_up_quiz_category(enrollment: Enrollment, term_id: Optional[str] = None) -> None:
    """Recompute the student's Quizzes grade_entry for this course × term.

    Formula:
        rollup_score = (sum of student's chosen-scoring-mode scores across
                        every published quiz in this course)
                     / (sum of quiz max_score across those quizzes)
                     × rubric[Quizzes].max_score
    """
    course = enrollment.course
    if course is None:
        return
    # Find the Quizzes rubric row for this course, if any.
    quiz_category = GradeCategory.query.filter_by(slug=_QUIZZES_SLUG).first()
    if quiz_category is None:
        return
    rubric = CourseRubric.query.filter_by(
        course_id=course.id, grade_category_id=quiz_category.id
    ).first()
    if rubric is None:
        return
    if term_id is None:
        term_id = _current_term_id()
    if term_id is None:
        return

    # Iterate every published quiz in every module of the course.
    quizzes: list[Quiz] = []
    for module in course.modules:
        for q in Quiz.query.filter_by(module_id=module.id, is_published=True).all():
            quizzes.append(q)
    if not quizzes:
        return

    earned = 0.0
    possible = 0.0
    for q in quizzes:
        # Every quiz counts toward possible, even if student hasn't tried
        # it yet — this way the running average reflects the student's
        # actual performance against everything published so far.
        possible += float(q.total_points() or 0)
        attempts = (
            QuizAttempt.query.filter_by(quiz_id=q.id, student_id=enrollment.student_id).all()
        )
        best = _best_score_by_mode(attempts, q.scoring_mode)
        if best is not None:
            earned += best

    if possible <= 0:
        return

    category_max = int(rubric.max_score)
    rolled = round((earned / possible) * category_max, 2)

    # Upsert the grade_entries row.
    entry = GradeEntry.query.filter_by(
        enrollment_id=enrollment.id,
        grade_category_id=quiz_category.id,
        term_id=term_id,
    ).first()
    if entry is None:
        entry = GradeEntry(
            enrollment_id=enrollment.id,
            grade_category_id=quiz_category.id,
            term_id=term_id,
            score=Decimal(str(rolled)),
        )
        db.session.add(entry)
    else:
        entry.score = Decimal(str(rolled))
        entry.updated_at = utc_now()


# ---------------------------------------------------------------------------
# Per-student quiz history projection
#
# Used by two read paths:
#   * `Course.to_dict(..., student=)`         — decorates every quiz summary
#                                               inside the course-detail
#                                               response with the caller's
#                                               last/best/attempts.
#   * `GET /api/quizzes/my`                   — top-level "my quizzes" hub.
#
# Read-only — never writes. One grouped-per-quiz SELECT for the whole set,
# so a course with N quizzes still costs one query, not N.
# ---------------------------------------------------------------------------
def compute_student_quiz_history(
    student_id: str, quiz_ids: list[str]
) -> dict[str, dict]:
    """Return {quiz_id: {attemptsCount, bestPercent, lastPercent,
    lastAttemptNumber, passed}} for the caller's SUBMITTED attempts on the
    given quizzes.

    Quizzes the student has never attempted are simply absent from the
    result — the caller decides how to render "no attempts yet".
    """
    if not quiz_ids:
        return {}
    rows = (
        QuizAttempt.query
        .filter(QuizAttempt.student_id == student_id)
        .filter(QuizAttempt.quiz_id.in_(quiz_ids))
        .filter(QuizAttempt.submitted_at.isnot(None))
        .filter(QuizAttempt.final_score.isnot(None))
        .filter(QuizAttempt.max_score.isnot(None))
        .all()
    )
    # Group in Python — SQLite doesn't cleanly do "score of the row with
    # max(submitted_at)" without a subquery; the attempt list per student
    # per quiz is small (max_attempts is typically <= 3).
    by_quiz: dict[str, list[QuizAttempt]] = {}
    for a in rows:
        by_quiz.setdefault(a.quiz_id, []).append(a)
    out: dict[str, dict] = {}
    for qid, attempts in by_quiz.items():
        best = max(
            (float(a.final_score) / float(a.max_score) * 100.0)
            for a in attempts
            if a.max_score and float(a.max_score) > 0
        )
        # "last" = last-submitted attempt, tie-broken by attempt_number.
        latest = max(
            attempts,
            key=lambda a: (a.submitted_at or datetime.min, a.attempt_number),
        )
        last_pct = (
            (float(latest.final_score) / float(latest.max_score) * 100.0)
            if latest.max_score and float(latest.max_score) > 0
            else None
        )
        out[qid] = {
            "attemptsCount": len(attempts),
            "bestPercent": round(best, 2),
            "lastPercent": round(last_pct, 2) if last_pct is not None else None,
            "lastAttemptNumber": latest.attempt_number,
            "passed": any(a.passed for a in attempts),
        }
    return out
