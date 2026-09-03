"""Phase 24 — course-scoped question bank + read/write endpoints.

A quiz with `pool_size=N` picks N random items from the bank at
`start_attempt` time (see `routes/quiz_take.py`); this blueprint owns
the bank's own CRUD.
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from models import (
    Course,
    QuestionBankItem,
    QuestionBankOption,
    Quiz,
    QuizOption,
    QuizQuestion,
    db,
)
from routes.auth import current_user, login_required
from utils.permissions import can_edit_course_content, is_admin
from utils.validation import (
    ValidationError,
    as_int,
    as_str,
    one_of,
    require_fields,
    require_json,
)

question_bank_bp = Blueprint("question_bank", __name__)

_QUESTION_TYPES = ("mc_single", "mc_multi", "true_false", "short_answer", "essay")


@question_bank_bp.route("/courses/<string:course_id>/question-bank", methods=["GET"])
@login_required
def list_bank(course_id: str):
    course = db.session.get(Course, course_id)
    if course is None:
        return jsonify({"error": "Course not found."}), 404
    user = current_user()
    if not (is_admin(user) or can_edit_course_content(user, course)):
        return jsonify({"error": "You do not have permission."}), 403
    q = (
        QuestionBankItem.query.filter_by(course_id=course.id)
        .order_by(QuestionBankItem.created_at.asc())
    )
    # Phase 30 · T5 — optional pagination. Back-compat bare-array
    # shape kept when no `page` arg is supplied.
    if request.args.get("page") or request.args.get("pageSize"):
        from utils.pagination import paginate
        return jsonify(paginate(q, render_item=lambda r: r.to_dict())), 200
    return jsonify([r.to_dict() for r in q.all()]), 200


@question_bank_bp.route("/courses/<string:course_id>/question-bank", methods=["POST"])
@login_required
def create_bank_item(course_id: str):
    course = db.session.get(Course, course_id)
    if course is None:
        return jsonify({"error": "Course not found."}), 404
    user = current_user()
    if not (is_admin(user) or can_edit_course_content(user, course)):
        return jsonify({"error": "You do not have permission."}), 403
    try:
        payload = require_json(request.get_json(silent=True))
        require_fields(payload, ("type", "prompt"))
        qtype = one_of(payload["type"], _QUESTION_TYPES, "type")
        prompt = as_str(payload["prompt"], "prompt", max_len=2000)
        points = as_int(payload.get("points", 1), "points")
        if points < 0 or points > 100:
            raise ValidationError("points must be 0-100.")
        options = payload.get("options", []) or []
        if not isinstance(options, list):
            raise ValidationError("options must be a list.")
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400

    item = QuestionBankItem(
        course_id=course.id, type=qtype, prompt=prompt.strip(), points=points,
        created_by_id=user.id,
    )
    db.session.add(item)
    db.session.flush()

    for i, opt in enumerate(options):
        if not isinstance(opt, dict):
            continue
        try:
            text = as_str(opt.get("text"), "text", max_len=500)
        except ValidationError as e:
            return jsonify({"error": str(e)}), 400
        is_correct = bool(opt.get("isCorrect", False))
        db.session.add(QuestionBankOption(
            bank_item_id=item.id, order_index=i, text=text.strip(),
            is_correct=is_correct,
        ))

    db.session.commit()
    return jsonify(item.to_dict()), 201


@question_bank_bp.route("/quizzes/<string:qid>/adopt-bank-items", methods=["POST"])
@login_required
def adopt_bank_items(qid: str):
    """Copy N bank items into this quiz as regular `QuizQuestion` rows
    (with their options). Enables reuse without touching the take/submit
    grading path.

    Body: `{itemIds: [...]}`. Silent no-op on unknown ids. Refused if the
    quiz has attempts (mirrors existing "no edits after submissions" rule).
    """
    quiz = db.session.get(Quiz, qid)
    if quiz is None:
        return jsonify({"error": "Quiz not found."}), 404
    course = quiz.module.course if quiz.module else None
    user = current_user()
    if not (is_admin(user) or (course and can_edit_course_content(user, course))):
        return jsonify({"error": "You do not have permission."}), 403
    if quiz.attempts.first() is not None:
        return jsonify({
            "error": "This quiz already has attempts; adopting more items is disabled.",
        }), 409
    try:
        payload = require_json(request.get_json(silent=True))
        require_fields(payload, ("itemIds",))
        ids = payload["itemIds"]
        if not isinstance(ids, list):
            raise ValidationError("itemIds must be a list.")
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400
    # Only pull items from the SAME course to avoid cross-course leakage.
    #
    # Phase 25 hard-audit fix H-6: the previous filter had a Python
    # operator-precedence bug — `A == B if C else False` binds as
    # `A == (B if C else False)`, so with `course` None every row was
    # compared to the literal False and silently matched nothing.
    # A missing course now returns 400 explicitly.
    if course is None:
        return jsonify({"error": "Quiz is not attached to a course."}), 400
    items = QuestionBankItem.query.filter(
        QuestionBankItem.id.in_(ids),
        QuestionBankItem.course_id == course.id,
    ).all()
    starting_order = (
        db.session.query(db.func.max(QuizQuestion.order_index))
        .filter_by(quiz_id=quiz.id).scalar() or -1
    ) + 1
    added: list[dict] = []
    for i, item in enumerate(items):
        q = QuizQuestion(
            quiz_id=quiz.id,
            order_index=starting_order + i,
            type=item.type,
            prompt=item.prompt,
            points=item.points,
        )
        db.session.add(q)
        db.session.flush()
        for opt in item.options.order_by(QuestionBankOption.order_index).all():
            db.session.add(QuizOption(
                question_id=q.id, order_index=opt.order_index,
                text=opt.text, is_correct=opt.is_correct,
            ))
        added.append(q.to_dict(hide_answers=False))
    db.session.commit()
    return jsonify({"adopted": len(added), "questions": added}), 200


@question_bank_bp.route("/bank-items/<string:iid>", methods=["DELETE"])
@login_required
def delete_bank_item(iid: str):
    item = db.session.get(QuestionBankItem, iid)
    if item is None:
        return jsonify({"error": "Bank item not found."}), 404
    course = db.session.get(Course, item.course_id)
    user = current_user()
    if not (is_admin(user) or can_edit_course_content(user, course)):
        return jsonify({"error": "You do not have permission."}), 403
    db.session.delete(item)
    db.session.commit()
    return "", 204
