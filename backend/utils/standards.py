"""Phase 32 · T3 — per-standard mastery rollup for students.

Mastery is derived, not stored: whenever a student's mastery view is
requested we walk the standards' tags → find quiz attempts and
assignment submissions on the tagged content → compute an average
score → bucket into a mastery band. Nothing is written.

Bands (matches the grading-scale terminology teachers already use):
  * mastered     — avg ≥ 85
  * meeting      — 70..84.99
  * progressing  — 50..69.99
  * beginning    — < 50
  * not-assessed — no attempts on tagged content yet
"""
from __future__ import annotations

from typing import Any


def _band(pct: float | None) -> str:
    if pct is None:
        return "not-assessed"
    if pct >= 85:
        return "mastered"
    if pct >= 70:
        return "meeting"
    if pct >= 50:
        return "progressing"
    return "beginning"


def compute_student_mastery(student_id: str) -> list[dict[str, Any]]:
    """Return `[{standardId, code, name, subject, masteryPercent,
    band, sampleSize}, ...]` for every standard the student has been
    exposed to (via tagged quizzes/assignments in their courses).

    Standards with zero tagged content-in-my-enrollment yield an
    entry with `band: "not-assessed"` and `sampleSize: 0` so the
    client can render the full curriculum, not just what's been
    graded.
    """
    from models import (
        AssignmentSubmission,
        Enrollment,
        Module,
        QuizAttempt,
        Standard,
        StandardTag,
        db,
    )

    # Restrict to content in courses the student is (or was) enrolled in.
    enrollments = Enrollment.query.filter_by(student_id=student_id).all()
    course_ids = {e.course_id for e in enrollments if e.course_id}
    module_ids = {
        m.id for m in Module.query.filter(
            Module.course_id.in_(course_ids)
        ).all()
    } if course_ids else set()

    # Collect (kind, ids) that live under the student's courses.
    from models import Assignment, Quiz
    quiz_ids: set[str] = set()
    assignment_ids: set[str] = set()
    if module_ids:
        for q in Quiz.query.filter(Quiz.module_id.in_(module_ids)).all():
            quiz_ids.add(q.id)
        for a in Assignment.query.filter(
            Assignment.module_id.in_(module_ids)
        ).all():
            assignment_ids.add(a.id)

    # All standards; then filter their tags to the student's content.
    standards = Standard.query.order_by(Standard.code.asc()).all()
    out: list[dict[str, Any]] = []
    for st in standards:
        tags = StandardTag.query.filter_by(standard_id=st.id).all()
        pcts: list[float] = []
        for t in tags:
            if t.taggable_type == "quiz" and t.taggable_id in quiz_ids:
                attempts = QuizAttempt.query.filter_by(
                    quiz_id=t.taggable_id, student_id=student_id,
                    status="submitted",
                ).all()
                # Take the best attempt per quiz — same policy the
                # gradebook uses for "current" score.
                best = None
                for att in attempts:
                    pct = float(att.percent) if att.percent is not None else None
                    if pct is None:
                        continue
                    best = pct if (best is None or pct > best) else best
                if best is not None:
                    pcts.append(best)
            elif t.taggable_type == "assignment" and t.taggable_id in assignment_ids:
                sub = AssignmentSubmission.query.filter_by(
                    assignment_id=t.taggable_id, student_id=student_id,
                ).first()
                if sub is None:
                    continue
                if sub.graded_score is None or sub.graded_max is None:
                    continue
                if float(sub.graded_max) <= 0:
                    continue
                pcts.append(
                    100.0 * float(sub.graded_score) / float(sub.graded_max)
                )
            # Lessons don't contribute a score — a lesson tag records
            # coverage only, not mastery.
        avg = (sum(pcts) / len(pcts)) if pcts else None
        out.append({
            "standardId": st.id,
            "code": st.code,
            "name": st.name,
            "subject": st.subject,
            "masteryPercent": round(avg, 2) if avg is not None else None,
            "band": _band(avg),
            "sampleSize": len(pcts),
        })
    return out
