"""Teacher/admin: list attempts on a quiz + manual score override."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from flask import Blueprint, jsonify, request

from models import (
    AttemptScoreOverride,
    Course,
    Quiz,
    QuizAnswerEntry,
    QuizAttempt,
    db,
)
from routes.auth import current_user, login_required
from utils.certificates import maybe_issue_certificate
from utils.grading import recompute_enrollment_cache
from utils.permissions import (
    can_edit_course_content,
    can_override_quiz_score,
    classes_user_teaches_for_course,
    is_admin,
    teaches_course_in_any_class,
)
from utils.quizzes import roll_up_quiz_category
from utils.validation import (
    ValidationError,
    as_str,
    require_json,
)
from utils.time import utc_now

quiz_admin_bp = Blueprint("quiz_admin", __name__)


@quiz_admin_bp.route("/quizzes/<string:quiz_id>/attempts", methods=["GET"])
@login_required
def list_attempts(quiz_id: str):
    quiz = db.session.get(Quiz, quiz_id)
    if quiz is None:
        return jsonify({"error": "Quiz not found."}), 404
    user = current_user()
    course = quiz.module.course
    if not (is_admin(user) or can_edit_course_content(user, course) or teaches_course_in_any_class(user, course)):
        return jsonify({"error": "You do not have permission."}), 403
    rows = (
        QuizAttempt.query.filter_by(quiz_id=quiz.id)
        .order_by(QuizAttempt.submitted_at.desc().nullslast())
        .all()
    )
    # Phase 9 audit fix F2: non-admins only see attempts from students in
    # classes they themselves teach this course in. `can_edit_course_content`
    # deliberately NOT used as an exemption — its vacancy-fallback branch
    # would re-open the cross-class leak the fix is closing.
    if not is_admin(user):
        allowed_class_ids = classes_user_teaches_for_course(user, course)
        rows = [
            a for a in rows
            if a.student is not None and a.student.class_id in allowed_class_ids
        ]
    out = []
    for a in rows:
        s = a.student
        d = a.to_dict()
        d["studentName"] = s.name if s else None
        d["studentEmail"] = s.email if s else None
        out.append(d)
    return jsonify(out), 200


@quiz_admin_bp.route("/quizzes/<string:quiz_id>/attempts/stats", methods=["GET"])
@login_required
def quiz_attempt_stats(quiz_id: str):
    """Phase 19 — one-glance class-average band for the teacher's quiz-attempts
    screen. Same auth + roster-scoping as `list_attempts`; adding stats to the
    list response itself would break the existing caller shape, so this is a
    sibling endpoint.

    Returns: `{count, submittedCount, avgPercent, minPercent, maxPercent,
              passRate}`. All percent values are 0..100, or null if there are
    no submitted attempts to compute over.
    """
    quiz = db.session.get(Quiz, quiz_id)
    if quiz is None:
        return jsonify({"error": "Quiz not found."}), 404
    user = current_user()
    course = quiz.module.course
    if not (is_admin(user) or can_edit_course_content(user, course) or teaches_course_in_any_class(user, course)):
        return jsonify({"error": "You do not have permission."}), 403

    rows = QuizAttempt.query.filter_by(quiz_id=quiz.id).all()
    if not is_admin(user):
        allowed_class_ids = classes_user_teaches_for_course(user, course)
        rows = [
            a for a in rows
            if a.student is not None and a.student.class_id in allowed_class_ids
        ]

    submitted = [
        a for a in rows
        if a.submitted_at is not None
        and a.final_score is not None
        and a.max_score is not None
        and float(a.max_score) > 0
    ]
    percents = [float(a.final_score) / float(a.max_score) * 100.0 for a in submitted]

    def _round(v: float | None) -> float | None:
        return round(v, 2) if v is not None else None

    if percents:
        avg = sum(percents) / len(percents)
        pmin = min(percents)
        pmax = max(percents)
        passed = sum(1 for a in submitted if a.passed)
        pass_rate = passed / len(submitted) * 100.0
    else:
        avg = None
        pmin = None
        pmax = None
        pass_rate = None

    return jsonify({
        "count": len(rows),
        "submittedCount": len(submitted),
        "avgPercent": _round(avg),
        "minPercent": _round(pmin),
        "maxPercent": _round(pmax),
        "passRate": _round(pass_rate),
    }), 200


@quiz_admin_bp.route("/quiz-attempts/<string:attempt_id>/override", methods=["POST"])
@login_required
def override_score(attempt_id: str):
    """Body: {
       finalScore,
       reason?,
       perQuestionScores?: [{questionId, score, feedback?}]
     }
    """
    attempt = db.session.get(QuizAttempt, attempt_id)
    if attempt is None:
        return jsonify({"error": "Attempt not found."}), 404
    if attempt.submitted_at is None:
        return jsonify({"error": "Cannot override an in-progress attempt."}), 400

    user = current_user()
    if not can_override_quiz_score(user, attempt):
        return jsonify({"error": "You do not have permission."}), 403

    try:
        payload = require_json(request.get_json(silent=True))
        if "finalScore" not in payload:
            raise ValidationError("finalScore is required.")
        try:
            new_final = float(payload["finalScore"])
        except (TypeError, ValueError):
            raise ValidationError("finalScore must be a number.") from None
        reason = as_str(payload.get("reason") or "", "reason", max_len=500) or None
        per_q = payload.get("perQuestionScores")
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400

    if new_final < 0 or (attempt.max_score is not None and Decimal(str(new_final)) > attempt.max_score):
        return jsonify({"error": "finalScore out of range."}), 400

    # Optional per-question overrides.
    if per_q is not None:
        if not isinstance(per_q, list):
            return jsonify({"error": "perQuestionScores must be an array."}), 400
        for it in per_q:
            if not isinstance(it, dict):
                continue
            qid = it.get("questionId")
            entry = QuizAnswerEntry.query.filter_by(
                attempt_id=attempt.id, question_id=qid
            ).first()
            if entry is None:
                entry = QuizAnswerEntry(attempt_id=attempt.id, question_id=qid)
                db.session.add(entry)
            try:
                sc = float(it.get("score"))
            except (TypeError, ValueError):
                continue
            entry.per_question_score = Decimal(str(sc))
            entry.is_manually_graded = True
            fb = it.get("feedback")
            if fb is not None:
                entry.manual_feedback = as_str(fb, "feedback", max_len=2000)

    old_final = attempt.final_score
    attempt.manual_score = Decimal(str(new_final))
    attempt.final_score = Decimal(str(new_final))
    # Passing check.
    if attempt.max_score and attempt.max_score > 0:
        pct = float(attempt.final_score) / float(attempt.max_score) * 100.0
        attempt.passed = pct >= attempt.quiz.passing_score
    # Clear needs_manual_review if every essay in this attempt now has a
    # manually graded entry.
    still_needs = False
    for q in attempt.quiz.questions:
        if q.type == "essay":
            e = QuizAnswerEntry.query.filter_by(attempt_id=attempt.id, question_id=q.id).first()
            if e is None or not e.is_manually_graded:
                still_needs = True
                break
    attempt.needs_manual_review = still_needs

    db.session.add(
        AttemptScoreOverride(
            attempt_id=attempt.id,
            old_final_score=old_final,
            new_final_score=attempt.final_score,
            reason=reason,
            overridden_by_id=user.id,
            overridden_at=utc_now(),
        )
    )

    # Recompute the quizzes-category rollup + enrollment cache + cert gate.
    if attempt.enrollment:
        roll_up_quiz_category(attempt.enrollment)
        recompute_enrollment_cache(attempt.enrollment)
        maybe_issue_certificate(attempt.enrollment)

    db.session.commit()
    return jsonify(attempt.to_dict(include_answers=True)), 200
