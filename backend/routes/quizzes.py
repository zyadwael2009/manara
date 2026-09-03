"""Quiz author CRUD — teachers with edit-content rights build quizzes.

Structural edits (adding/removing questions, changing which option is
correct) after any attempt exists are REFUSED with 409 — the teacher must
duplicate the quiz and supersede. Cosmetic edits (prompt/option text,
description) are always allowed.
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request
from sqlalchemy import func

from models import (
    Course,
    Enrollment,
    Module,
    Quiz,
    QuizAcceptableAnswer,
    QuizAttempt,
    QuizOption,
    QuizQuestion,
    QUIZ_QUESTION_TYPES,
    QUIZ_SCORING_MODES,
    db,
)
from routes.auth import current_user, login_required
from utils.permissions import (
    can_edit_course_content,
    has_active_enrollment,
    is_admin,
    is_instructor,
    teaches_course_in_any_class,
)
from utils.validation import (
    ValidationError,
    as_int,
    as_str,
    one_of,
    require_fields,
    require_json,
)

quizzes_bp = Blueprint("quizzes", __name__)


def _quiz_authorship_check(quiz: Quiz) -> tuple | None:
    """Return (jsonify, code) if caller can't edit. None if allowed."""
    user = current_user()
    if not can_edit_course_content(user, quiz.module.course):
        return jsonify({"error": "You do not have permission to edit this quiz."}), 403
    return None


def _attempts_exist(quiz_id: str) -> bool:
    return db.session.query(
        db.session.query(QuizAttempt.id).filter_by(quiz_id=quiz_id).exists()
    ).scalar()


# =============================================================================
# Quiz CRUD
# =============================================================================
@quizzes_bp.route("/modules/<string:module_id>/quizzes", methods=["POST"])
@login_required
def create_quiz(module_id: str):
    module = db.session.get(Module, module_id)
    if module is None:
        return jsonify({"error": "Module not found."}), 404
    if not can_edit_course_content(current_user(), module.course):
        return jsonify({"error": "You do not have permission."}), 403
    try:
        payload = require_json(request.get_json(silent=True))
        require_fields(payload, ("title",))
        title = as_str(payload["title"], "title", max_len=200)
        description = as_str(payload.get("description", ""), "description", max_len=10_000)
        passing = as_int(payload.get("passingScore"), "passingScore", default=60)
        max_attempts = payload.get("maxAttempts")
        if max_attempts is not None:
            max_attempts = as_int(max_attempts, "maxAttempts")
        scoring_mode = one_of(
            payload.get("scoringMode", "best"), QUIZ_SCORING_MODES, "scoringMode"
        )
        time_limit = payload.get("timeLimitMinutes")
        if time_limit is not None and time_limit != "":
            time_limit = as_int(time_limit, "timeLimitMinutes")
        else:
            time_limit = None
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400
    if passing < 0 or passing > 100:
        return jsonify({"error": "passingScore must be between 0 and 100."}), 400

    q = Quiz(
        module_id=module.id,
        title=title,
        description=description,
        passing_score=passing,
        max_attempts=max_attempts,
        scoring_mode=scoring_mode,
        time_limit_minutes=time_limit,
        is_published=False,
        created_by_id=current_user().id,
    )
    db.session.add(q)
    db.session.commit()
    return jsonify(q.to_dict()), 201


@quizzes_bp.route("/quizzes/<string:quiz_id>", methods=["GET"])
@login_required
def get_quiz(quiz_id: str):
    quiz = db.session.get(Quiz, quiz_id)
    if quiz is None:
        return jsonify({"error": "Quiz not found."}), 404
    user = current_user()
    course = quiz.module.course
    # Authors see with answer keys; students see without.
    is_author = can_edit_course_content(user, course) or is_admin(user) or teaches_course_in_any_class(user, course)
    if not (is_author or has_active_enrollment(user, course)):
        return jsonify({"error": "You do not have permission."}), 403
    data = quiz.to_dict(include_questions=True, hide_answers=not is_author)
    return jsonify(data), 200


@quizzes_bp.route("/quizzes/<string:quiz_id>", methods=["PUT", "PATCH"])
@login_required
def update_quiz(quiz_id: str):
    quiz = db.session.get(Quiz, quiz_id)
    if quiz is None:
        return jsonify({"error": "Quiz not found."}), 404
    err = _quiz_authorship_check(quiz)
    if err:
        return err
    try:
        payload = require_json(request.get_json(silent=True))
        if "title" in payload:
            quiz.title = as_str(payload["title"], "title", max_len=200)
        if "description" in payload:
            quiz.description = as_str(payload["description"], "description", max_len=10_000)
        if "passingScore" in payload:
            p = as_int(payload["passingScore"], "passingScore")
            if p < 0 or p > 100:
                return jsonify({"error": "passingScore must be 0-100."}), 400
            quiz.passing_score = p
        if "maxAttempts" in payload:
            v = payload["maxAttempts"]
            quiz.max_attempts = None if v in (None, "") else as_int(v, "maxAttempts")
        if "scoringMode" in payload:
            quiz.scoring_mode = one_of(
                payload["scoringMode"], QUIZ_SCORING_MODES, "scoringMode"
            )
        if "timeLimitMinutes" in payload:
            v = payload["timeLimitMinutes"]
            quiz.time_limit_minutes = None if v in (None, "") else as_int(v, "timeLimitMinutes")
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400
    db.session.commit()
    return jsonify(quiz.to_dict()), 200


@quizzes_bp.route("/quizzes/<string:quiz_id>", methods=["DELETE"])
@login_required
def delete_quiz(quiz_id: str):
    quiz = db.session.get(Quiz, quiz_id)
    if quiz is None:
        return jsonify({"error": "Quiz not found."}), 404
    err = _quiz_authorship_check(quiz)
    if err:
        return err
    if _attempts_exist(quiz.id):
        return jsonify({"error": "Cannot delete a quiz that has student attempts. Unpublish instead."}), 409
    db.session.delete(quiz)
    db.session.commit()
    return jsonify({"message": "Quiz deleted."}), 200


@quizzes_bp.route("/quizzes/<string:quiz_id>/publish", methods=["POST"])
@login_required
def publish_quiz(quiz_id: str):
    quiz = db.session.get(Quiz, quiz_id)
    if quiz is None:
        return jsonify({"error": "Quiz not found."}), 404
    err = _quiz_authorship_check(quiz)
    if err:
        return err
    if quiz.questions.count() == 0:
        return jsonify({"error": "Add at least one question before publishing."}), 400
    quiz.is_published = True
    db.session.commit()
    return jsonify(quiz.to_dict()), 200


@quizzes_bp.route("/quizzes/<string:quiz_id>/unpublish", methods=["POST"])
@login_required
def unpublish_quiz(quiz_id: str):
    quiz = db.session.get(Quiz, quiz_id)
    if quiz is None:
        return jsonify({"error": "Quiz not found."}), 404
    err = _quiz_authorship_check(quiz)
    if err:
        return err
    quiz.is_published = False
    # Phase 9 audit fix F5: unpublishing removes a gate criterion from
    # is_eligible(); every enrolled student whose gate was blocked ONLY by
    # this quiz should now get their certificate.
    from utils.certificates import maybe_issue_certificate
    course = quiz.module.course
    if course is not None:
        for e in Enrollment.query.filter_by(course_id=course.id).filter(
            Enrollment.status.in_(("active", "completed"))
        ).all():
            maybe_issue_certificate(e)
    db.session.commit()
    return jsonify(quiz.to_dict()), 200


# =============================================================================
# Question CRUD
# =============================================================================
@quizzes_bp.route("/quizzes/<string:quiz_id>/questions", methods=["POST"])
@login_required
def create_question(quiz_id: str):
    quiz = db.session.get(Quiz, quiz_id)
    if quiz is None:
        return jsonify({"error": "Quiz not found."}), 404
    err = _quiz_authorship_check(quiz)
    if err:
        return err
    if _attempts_exist(quiz.id):
        return jsonify({"error": "This quiz has student attempts. Duplicate it before restructuring."}), 409

    try:
        payload = require_json(request.get_json(silent=True))
        require_fields(payload, ("type", "prompt"))
        qtype = one_of(payload["type"], QUIZ_QUESTION_TYPES, "type")
        prompt = as_str(payload["prompt"], "prompt", max_len=5000)
        points = as_int(payload.get("points"), "points", default=1)
        required = bool(payload.get("required", True))
        order_index = as_int(payload.get("orderIndex"), "orderIndex", default=-1)
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400
    if points <= 0:
        return jsonify({"error": "points must be positive."}), 400

    if order_index < 0:
        last = db.session.query(func.max(QuizQuestion.order_index)).filter_by(quiz_id=quiz.id).scalar()
        order_index = 0 if last is None else last + 1

    q = QuizQuestion(
        quiz_id=quiz.id,
        order_index=order_index,
        type=qtype,
        prompt=prompt,
        points=points,
        required=required,
    )
    db.session.add(q)
    db.session.flush()

    # For true_false, auto-create the True/False options with is_correct
    # empty; teacher fills in.
    if qtype == "true_false":
        db.session.add(QuizOption(question_id=q.id, order_index=0, text="True"))
        db.session.add(QuizOption(question_id=q.id, order_index=1, text="False"))

    db.session.commit()
    return jsonify(q.to_dict(hide_answers=False)), 201


@quizzes_bp.route("/quiz-questions/<string:qq_id>", methods=["PUT", "PATCH"])
@login_required
def update_question(qq_id: str):
    q = db.session.get(QuizQuestion, qq_id)
    if q is None:
        return jsonify({"error": "Question not found."}), 404
    err = _quiz_authorship_check(q.quiz)
    if err:
        return err
    has_attempts = _attempts_exist(q.quiz_id)
    try:
        payload = require_json(request.get_json(silent=True))
        if "type" in payload:
            if has_attempts and payload["type"] != q.type:
                return jsonify({"error": "Cannot change question type after attempts exist."}), 409
            q.type = one_of(payload["type"], QUIZ_QUESTION_TYPES, "type")
        if "prompt" in payload:
            q.prompt = as_str(payload["prompt"], "prompt", max_len=5000)
        if "points" in payload:
            if has_attempts:
                return jsonify({"error": "Cannot change points after attempts exist. Duplicate the quiz."}), 409
            q.points = as_int(payload["points"], "points")
        if "orderIndex" in payload:
            q.order_index = as_int(payload["orderIndex"], "orderIndex")
        if "required" in payload:
            q.required = bool(payload["required"])
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400
    db.session.commit()
    return jsonify(q.to_dict(hide_answers=False)), 200


@quizzes_bp.route("/quiz-questions/<string:qq_id>", methods=["DELETE"])
@login_required
def delete_question(qq_id: str):
    q = db.session.get(QuizQuestion, qq_id)
    if q is None:
        return jsonify({"error": "Question not found."}), 404
    err = _quiz_authorship_check(q.quiz)
    if err:
        return err
    if _attempts_exist(q.quiz_id):
        return jsonify({"error": "Cannot delete a question after attempts exist."}), 409
    db.session.delete(q)
    db.session.commit()
    return jsonify({"message": "Deleted."}), 200


# =============================================================================
# Option CRUD (for MC/TF questions)
# =============================================================================
@quizzes_bp.route("/quiz-questions/<string:qq_id>/options", methods=["POST"])
@login_required
def create_option(qq_id: str):
    q = db.session.get(QuizQuestion, qq_id)
    if q is None:
        return jsonify({"error": "Question not found."}), 404
    err = _quiz_authorship_check(q.quiz)
    if err:
        return err
    if _attempts_exist(q.quiz_id):
        return jsonify({"error": "Cannot add options after attempts exist."}), 409

    try:
        payload = require_json(request.get_json(silent=True))
        require_fields(payload, ("text",))
        text = as_str(payload["text"], "text", max_len=1000)
        is_correct = bool(payload.get("isCorrect", False))
        order_index = as_int(payload.get("orderIndex"), "orderIndex", default=-1)
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400
    if order_index < 0:
        last = db.session.query(func.max(QuizOption.order_index)).filter_by(question_id=q.id).scalar()
        order_index = 0 if last is None else last + 1

    o = QuizOption(question_id=q.id, order_index=order_index, text=text, is_correct=is_correct)
    db.session.add(o)
    db.session.commit()
    return jsonify(o.to_dict(hide_correct=False)), 201


@quizzes_bp.route("/quiz-options/<string:opt_id>", methods=["PUT", "PATCH"])
@login_required
def update_option(opt_id: str):
    o = db.session.get(QuizOption, opt_id)
    if o is None:
        return jsonify({"error": "Option not found."}), 404
    err = _quiz_authorship_check(o.question.quiz)
    if err:
        return err
    has_attempts = _attempts_exist(o.question.quiz_id)
    try:
        payload = require_json(request.get_json(silent=True))
        if "text" in payload:
            o.text = as_str(payload["text"], "text", max_len=1000)
        if "isCorrect" in payload:
            new_val = bool(payload["isCorrect"])
            if has_attempts and new_val != o.is_correct:
                return jsonify({"error": "Cannot change correctness after attempts exist. Duplicate the quiz."}), 409
            o.is_correct = new_val
        if "orderIndex" in payload:
            o.order_index = as_int(payload["orderIndex"], "orderIndex")
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400
    db.session.commit()
    return jsonify(o.to_dict(hide_correct=False)), 200


@quizzes_bp.route("/quiz-options/<string:opt_id>", methods=["DELETE"])
@login_required
def delete_option(opt_id: str):
    o = db.session.get(QuizOption, opt_id)
    if o is None:
        return jsonify({"error": "Option not found."}), 404
    err = _quiz_authorship_check(o.question.quiz)
    if err:
        return err
    if _attempts_exist(o.question.quiz_id):
        return jsonify({"error": "Cannot delete options after attempts exist."}), 409
    db.session.delete(o)
    db.session.commit()
    return jsonify({"message": "Deleted."}), 200


# =============================================================================
# Acceptable answers (for short_answer)
# =============================================================================
@quizzes_bp.route("/quiz-questions/<string:qq_id>/acceptable-answers", methods=["POST"])
@login_required
def add_acceptable_answer(qq_id: str):
    q = db.session.get(QuizQuestion, qq_id)
    if q is None:
        return jsonify({"error": "Question not found."}), 404
    if q.type != "short_answer":
        return jsonify({"error": "Acceptable answers only apply to short_answer questions."}), 400
    err = _quiz_authorship_check(q.quiz)
    if err:
        return err
    if _attempts_exist(q.quiz_id):
        return jsonify({"error": "Cannot change accepted answers after attempts exist."}), 409
    try:
        payload = require_json(request.get_json(silent=True))
        require_fields(payload, ("text",))
        text = as_str(payload["text"], "text", max_len=500)
        case_sensitive = bool(payload.get("caseSensitive", False))
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400
    a = QuizAcceptableAnswer(question_id=q.id, text=text, case_sensitive=case_sensitive)
    db.session.add(a)
    db.session.commit()
    return jsonify({"id": a.id, "text": a.text, "caseSensitive": a.case_sensitive}), 201
