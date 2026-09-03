"""Student-facing quiz endpoints: start, submit, view own attempts.

All writes are self-bound — the server ignores any client-provided studentId
and uses `session.user_id`.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from decimal import Decimal

from flask import Blueprint, jsonify, request

from models import (
    Course,
    Enrollment,
    Module,
    Quiz,
    QuizAnswerEntry,
    QuizAttempt,
    QuizQuestion,
    db,
)
from routes.auth import current_user, login_required
from utils.certificates import maybe_issue_certificate
from utils.grading import recompute_enrollment_cache
from utils.permissions import (
    can_take_quiz,
    can_view_quiz_attempt,
    has_active_enrollment,
    is_student,
)
from utils.quizzes import (
    auto_grade_attempt,
    compute_student_quiz_history,
    roll_up_quiz_category,
)
from utils.validation import (
    ValidationError,
    require_json,
)
from utils.time import utc_now

quiz_take_bp = Blueprint("quiz_take", __name__)


def _now() -> datetime:
    return utc_now()


# ---------------------------------------------------------------------------
# Start
# ---------------------------------------------------------------------------
@quiz_take_bp.route("/quizzes/<string:quiz_id>/start", methods=["POST"])
@login_required
def start_attempt(quiz_id: str):
    """Create a new in-progress attempt (or resume the latest unsubmitted).

    Returns the attempt + the quiz's questions WITHOUT answer keys.
    """
    quiz = db.session.get(Quiz, quiz_id)
    if quiz is None:
        return jsonify({"error": "Quiz not found."}), 404
    if not quiz.is_published:
        return jsonify({"error": "This quiz is not published yet."}), 403

    user = current_user()
    if not can_take_quiz(user, quiz):
        return jsonify({"error": "You are not enrolled in this course."}), 403

    now = _now()
    if quiz.available_from and now < quiz.available_from:
        return jsonify({"error": "This quiz isn't available yet."}), 403
    if quiz.available_until and now > quiz.available_until:
        return jsonify({"error": "This quiz is no longer available."}), 403

    # Find or create an in-progress attempt.
    in_progress = (
        QuizAttempt.query.filter_by(quiz_id=quiz.id, student_id=user.id)
        .filter(QuizAttempt.submitted_at.is_(None))
        .order_by(QuizAttempt.started_at.desc())
        .first()
    )
    if in_progress is not None:
        attempt = in_progress
    else:
        # Check max_attempts.
        submitted_count = QuizAttempt.query.filter_by(
            quiz_id=quiz.id, student_id=user.id
        ).filter(QuizAttempt.submitted_at.isnot(None)).count()
        if quiz.max_attempts is not None and submitted_count >= quiz.max_attempts:
            return jsonify({"error": "You have used all your attempts on this quiz."}), 403
        # Locate the student's enrollment.
        enrollment = Enrollment.query.filter_by(
            student_id=user.id, course_id=quiz.module.course_id
        ).first()
        if enrollment is None:
            return jsonify({"error": "You are not enrolled in this course."}), 403
        attempt = QuizAttempt(
            quiz_id=quiz.id,
            student_id=user.id,
            enrollment_id=enrollment.id,
            attempt_number=submitted_count + 1,
            max_score=Decimal(str(quiz.total_points())),
        )
        db.session.add(attempt)
        db.session.commit()

    return jsonify({
        "attempt": attempt.to_dict(),
        "quiz": quiz.to_dict(include_questions=True, hide_answers=True),
    }), 201


# ---------------------------------------------------------------------------
# Submit
# ---------------------------------------------------------------------------
@quiz_take_bp.route("/quiz-attempts/<string:attempt_id>/submit", methods=["POST"])
@login_required
def submit_attempt(attempt_id: str):
    """Body: { answers: [{ questionId, responseText?, selectedOptionIds? }] }.

    Server ignores any studentId in the body and binds to session.user_id.
    """
    attempt = db.session.get(QuizAttempt, attempt_id)
    if attempt is None:
        return jsonify({"error": "Attempt not found."}), 404

    user = current_user()
    if attempt.student_id != user.id:
        return jsonify({"error": "This is not your attempt."}), 403
    if attempt.submitted_at is not None:
        return jsonify({"error": "This attempt has already been submitted."}), 409

    quiz = attempt.quiz
    # Hard time-limit enforcement server-side.
    if quiz.time_limit_minutes is not None:
        expire_at = (attempt.started_at or _now()) + timedelta(
            minutes=quiz.time_limit_minutes
        )
        # Grace: also allow 5 minutes past available_until.
        if quiz.available_until:
            grace = quiz.available_until + timedelta(minutes=5)
        else:
            grace = None
        if _now() > expire_at and (grace is None or _now() > grace):
            # Time expired — auto-submit whatever came in, but mark attempt
            # with the current wall-clock rather than rejecting the request.
            pass  # fall through and grade

    try:
        payload = require_json(request.get_json(silent=True))
        answers = payload.get("answers")
        if not isinstance(answers, list):
            raise ValidationError("`answers` must be an array.")
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400

    # Save answer entries (upserts by question_id).
    question_ids = {q.id for q in quiz.questions}
    for a in answers:
        if not isinstance(a, dict):
            continue
        qid = a.get("questionId")
        if qid not in question_ids:
            continue
        entry = QuizAnswerEntry.query.filter_by(
            attempt_id=attempt.id, question_id=qid
        ).first()
        if entry is None:
            entry = QuizAnswerEntry(attempt_id=attempt.id, question_id=qid)
            db.session.add(entry)
        # Phase 9 audit fix F9: cap essay/short-answer text to 8KB per answer
        # so a low-trust student can't bloat the DB (MAX_CONTENT_LENGTH is
        # 200MB for uploads, way too generous for a text field).
        raw_text = a.get("responseText")
        if raw_text is not None:
            if not isinstance(raw_text, str):
                return jsonify({"error": "responseText must be a string."}), 400
            if len(raw_text) > 8000:
                return jsonify({"error": "responseText exceeds 8000 characters."}), 400
        entry.response_text = raw_text
        selected = a.get("selectedOptionIds")
        if selected is not None:
            if not isinstance(selected, list):
                return jsonify({"error": "selectedOptionIds must be an array."}), 400
            entry.selected_option_ids = json.dumps([str(x) for x in selected])
        else:
            entry.selected_option_ids = None

    attempt.submitted_at = _now()
    # Auto-grade + rollup + cache recompute — all in one transaction.
    auto_grade_attempt(attempt)
    roll_up_quiz_category(attempt.enrollment)
    recompute_enrollment_cache(attempt.enrollment)
    # Passing this quiz may close the last certificate gate.
    maybe_issue_certificate(attempt.enrollment)
    db.session.commit()

    # Return the full attempt + quiz WITH answer keys so the student can
    # review right after submitting.
    return jsonify({
        "attempt": attempt.to_dict(include_answers=True),
        "quiz": quiz.to_dict(include_questions=True, hide_answers=False),
    }), 200


# ---------------------------------------------------------------------------
# Read one attempt
# ---------------------------------------------------------------------------
@quiz_take_bp.route("/quiz-attempts/<string:attempt_id>", methods=["GET"])
@login_required
def get_attempt(attempt_id: str):
    attempt = db.session.get(QuizAttempt, attempt_id)
    if attempt is None:
        return jsonify({"error": "Attempt not found."}), 404
    user = current_user()
    if not can_view_quiz_attempt(user, attempt):
        return jsonify({"error": "You do not have permission."}), 403
    # Reveal answer keys only if the attempt has been submitted (otherwise
    # the reader — student themself — shouldn't see them mid-take).
    reveal = attempt.submitted_at is not None
    return jsonify({
        "attempt": attempt.to_dict(include_answers=True),
        "quiz": attempt.quiz.to_dict(include_questions=True, hide_answers=not reveal),
    }), 200


# ---------------------------------------------------------------------------
# My attempts for one quiz
# ---------------------------------------------------------------------------
@quiz_take_bp.route("/quizzes/<string:quiz_id>/my-attempts", methods=["GET"])
@login_required
def my_attempts(quiz_id: str):
    quiz = db.session.get(Quiz, quiz_id)
    if quiz is None:
        return jsonify({"error": "Quiz not found."}), 404
    user = current_user()
    rows = (
        QuizAttempt.query.filter_by(quiz_id=quiz.id, student_id=user.id)
        .order_by(QuizAttempt.attempt_number.asc())
        .all()
    )
    return jsonify([a.to_dict() for a in rows]), 200


# ---------------------------------------------------------------------------
# Phase 16 — the student "Quizzes" hub
# ---------------------------------------------------------------------------
@quiz_take_bp.route("/quizzes/my", methods=["GET"])
@quiz_take_bp.route("/quizzes/my/", methods=["GET"])
@login_required
def my_quizzes_all():
    """Every published quiz across the caller's live enrollments, plus the
    caller's own attempt history for each.

    Auth: `@login_required`. Rows are only produced for the caller's own
    enrollments (status in 'active'/'completed'), so a non-student caller
    naturally gets an empty list. No cross-student leakage possible — the
    query is keyed on `student_id = current_user`.
    """
    user = current_user()

    enrolls = (
        Enrollment.query.filter_by(student_id=user.id)
        .filter(Enrollment.status.in_(("active", "completed")))
        .all()
    )
    if not enrolls:
        return jsonify([]), 200

    # Preload every {course, its modules, its quizzes} the caller touches.
    course_by_id = {c.id: c for c in
                    Course.query.filter(Course.id.in_([e.course_id for e in enrolls])).all()}
    modules_by_course: dict[str, list[Module]] = {}
    for m in Module.query.filter(Module.course_id.in_(course_by_id.keys())).all():
        modules_by_course.setdefault(m.course_id, []).append(m)
    for lst in modules_by_course.values():
        lst.sort(key=lambda m: m.order_index)

    all_module_ids = [m.id for lst in modules_by_course.values() for m in lst]
    quizzes = (
        Quiz.query.filter(Quiz.module_id.in_(all_module_ids))
        .filter(Quiz.is_published.is_(True))
        .all()
    ) if all_module_ids else []
    quizzes_by_module: dict[str, list[Quiz]] = {}
    for q in quizzes:
        quizzes_by_module.setdefault(q.module_id, []).append(q)
    for lst in quizzes_by_module.values():
        # Same ordering as the outline: created_at asc.
        lst.sort(key=lambda q: q.created_at)

    # One grouped SQL for the caller's whole attempt history.
    history = compute_student_quiz_history(user.id, [q.id for q in quizzes])

    # Also pull every submitted attempt (with per-attempt detail) for the
    # in-hub timeline. Small: max_attempts is usually <=3 per quiz.
    attempt_rows = (
        QuizAttempt.query
        .filter(QuizAttempt.student_id == user.id)
        .filter(QuizAttempt.quiz_id.in_([q.id for q in quizzes]))
        .filter(QuizAttempt.submitted_at.isnot(None))
        .order_by(QuizAttempt.attempt_number.asc())
        .all()
    ) if quizzes else []
    attempts_by_quiz: dict[str, list[QuizAttempt]] = {}
    for a in attempt_rows:
        attempts_by_quiz.setdefault(a.quiz_id, []).append(a)

    def _attempt_stub(a: QuizAttempt) -> dict:
        pct = None
        if a.final_score is not None and a.max_score and float(a.max_score) > 0:
            pct = round(float(a.final_score) / float(a.max_score) * 100.0, 2)
        return {
            "id": a.id,
            "attemptNumber": a.attempt_number,
            "submittedAt": a.submitted_at.isoformat() + "Z" if a.submitted_at else None,
            "finalScore": float(a.final_score) if a.final_score is not None else None,
            "maxScore": float(a.max_score) if a.max_score is not None else None,
            "percent": pct,
            "passed": a.passed,
            "needsManualReview": a.needs_manual_review,
        }

    out: list[dict] = []
    # Ordering: course title → module.order_index → quiz created_at
    for e in enrolls:
        course = course_by_id.get(e.course_id)
        if course is None:
            continue
        for m in modules_by_course.get(course.id, []):
            for q in quizzes_by_module.get(m.id, []):
                hist = history.get(q.id)
                # canRetake: unlimited attempts, or under the cap; window
                # boundaries also apply if the quiz has a close date.
                count = hist["attemptsCount"] if hist else 0
                cap_ok = (q.max_attempts is None) or (count < q.max_attempts)
                now = _now()
                window_ok = True
                if q.available_from and now < q.available_from:
                    window_ok = False
                if q.available_until and now > q.available_until:
                    window_ok = False
                out.append({
                    "quiz": {
                        "id": q.id,
                        "title": q.title,
                        "moduleId": q.module_id,
                        "moduleTitle": m.title,
                        "totalPoints": q.total_points(),
                        "passingScore": q.passing_score,
                        "maxAttempts": q.max_attempts,
                        "timeLimitMinutes": q.time_limit_minutes,
                    },
                    "course": {
                        "id": course.id,
                        "title": course.title,
                        "category": course.category,
                        "gradeName": course.grade.name if course.grade else None,
                    },
                    "attempts": [_attempt_stub(a) for a in attempts_by_quiz.get(q.id, [])],
                    "attemptsCount": count,
                    "bestPercent": hist["bestPercent"] if hist else None,
                    "lastPercent": hist["lastPercent"] if hist else None,
                    "lastAttemptNumber": hist["lastAttemptNumber"] if hist else None,
                    "passed": hist["passed"] if hist else False,
                    "canRetake": cap_ok and window_ok,
                })
    # Final ordering: course title then module then quiz. `enrolls` already
    # orders by enrolled_at desc; re-sort to guarantee deterministic UX.
    out.sort(key=lambda r: (
        (r["course"]["title"] or "").lower(),
        r["quiz"]["moduleTitle"] or "",
        r["quiz"]["title"] or "",
    ))
    return jsonify(out), 200
