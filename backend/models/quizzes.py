"""Quizzes, their questions and options, student attempts, and the reusable question bank."""
from __future__ import annotations

from models.base import (
    db,
    generate_uuid,
    utc_now,
    _iso,
    Any,
)

# =============================================================================
# Phase 4 — Quizzes
# =============================================================================

QUIZ_QUESTION_TYPES = ("mc_single", "mc_multi", "true_false", "short_answer", "essay")
QUIZ_SCORING_MODES = ("best", "latest", "average", "first")


class Quiz(db.Model):
    __tablename__ = "quizzes"

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    module_id = db.Column(db.String(36), db.ForeignKey("modules.id"), nullable=False, index=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False, default="")

    passing_score = db.Column(db.Integer, nullable=False, default=60)  # percent 0-100
    max_attempts = db.Column(db.Integer, nullable=True)  # null = unlimited
    scoring_mode = db.Column(db.String(20), nullable=False, default="best")

    time_limit_minutes = db.Column(db.Integer, nullable=True)
    available_from = db.Column(db.DateTime, nullable=True)
    available_until = db.Column(db.DateTime, nullable=True)

    is_published = db.Column(db.Boolean, nullable=False, default=False)
    # Phase 24 — when set, `start_attempt` picks this many random
    # QuestionBankItem rows from the course's bank instead of using the
    # quiz's own hand-written `questions`. Existing quizzes leave this
    # null and behave unchanged.
    pool_size = db.Column(db.Integer, nullable=True)
    created_by_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=utc_now, onupdate=utc_now
    )

    module = db.relationship("Module")
    questions = db.relationship(
        "QuizQuestion",
        backref="quiz",
        lazy="dynamic",
        cascade="all, delete-orphan",
        order_by="QuizQuestion.order_index",
    )
    attempts = db.relationship(
        "QuizAttempt", backref="quiz", lazy="dynamic", cascade="all, delete-orphan"
    )

    def total_points(self) -> int:
        return sum(q.points for q in self.questions)

    def to_dict(self, *, include_questions: bool = False, hide_answers: bool = True) -> dict[str, Any]:
        data: dict[str, Any] = {
            "id": self.id,
            "moduleId": self.module_id,
            "title": self.title,
            "description": self.description,
            "passingScore": self.passing_score,
            "maxAttempts": self.max_attempts,
            "scoringMode": self.scoring_mode,
            "timeLimitMinutes": self.time_limit_minutes,
            "availableFrom": _iso(self.available_from),
            "availableUntil": _iso(self.available_until),
            "isPublished": self.is_published,
            "totalPoints": self.total_points(),
            "createdAt": _iso(self.created_at),
        }
        if include_questions:
            data["questions"] = [
                q.to_dict(hide_answers=hide_answers)
                for q in self.questions.order_by(QuizQuestion.order_index).all()
            ]
        return data


class QuizQuestion(db.Model):
    __tablename__ = "quiz_questions"

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    quiz_id = db.Column(db.String(36), db.ForeignKey("quizzes.id"), nullable=False, index=True)
    order_index = db.Column(db.Integer, nullable=False, default=0)
    type = db.Column(db.String(20), nullable=False, default="mc_single")
    prompt = db.Column(db.Text, nullable=False)
    points = db.Column(db.Integer, nullable=False, default=1)
    required = db.Column(db.Boolean, nullable=False, default=True)

    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=utc_now, onupdate=utc_now
    )

    options = db.relationship(
        "QuizOption",
        backref="question",
        lazy="dynamic",
        cascade="all, delete-orphan",
        order_by="QuizOption.order_index",
    )
    acceptable_answers = db.relationship(
        "QuizAcceptableAnswer",
        backref="question",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )

    def to_dict(self, *, hide_answers: bool = True) -> dict[str, Any]:
        data: dict[str, Any] = {
            "id": self.id,
            "quizId": self.quiz_id,
            "orderIndex": self.order_index,
            "type": self.type,
            "prompt": self.prompt,
            "points": self.points,
            "required": self.required,
        }
        if self.type in ("mc_single", "mc_multi", "true_false"):
            data["options"] = [
                o.to_dict(hide_correct=hide_answers)
                for o in self.options.order_by(QuizOption.order_index).all()
            ]
        elif self.type == "short_answer":
            if not hide_answers:
                data["acceptableAnswers"] = [
                    {"text": a.text, "caseSensitive": a.case_sensitive}
                    for a in self.acceptable_answers.all()
                ]
        # essay: nothing extra
        return data


class QuizOption(db.Model):
    __tablename__ = "quiz_options"

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    question_id = db.Column(db.String(36), db.ForeignKey("quiz_questions.id"), nullable=False, index=True)
    order_index = db.Column(db.Integer, nullable=False, default=0)
    text = db.Column(db.Text, nullable=False)
    is_correct = db.Column(db.Boolean, nullable=False, default=False)

    def to_dict(self, *, hide_correct: bool = True) -> dict[str, Any]:
        data: dict[str, Any] = {
            "id": self.id,
            "questionId": self.question_id,
            "orderIndex": self.order_index,
            "text": self.text,
        }
        if not hide_correct:
            data["isCorrect"] = self.is_correct
        return data


class QuizAcceptableAnswer(db.Model):
    __tablename__ = "quiz_acceptable_answers"

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    question_id = db.Column(db.String(36), db.ForeignKey("quiz_questions.id"), nullable=False, index=True)
    text = db.Column(db.String(500), nullable=False)
    case_sensitive = db.Column(db.Boolean, nullable=False, default=False)


class QuizAttempt(db.Model):
    __tablename__ = "quiz_attempts"

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    quiz_id = db.Column(db.String(36), db.ForeignKey("quizzes.id"), nullable=False, index=True)
    student_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False, index=True)
    enrollment_id = db.Column(db.String(36), db.ForeignKey("enrollments.id"), nullable=False, index=True)

    started_at = db.Column(db.DateTime, nullable=False, default=utc_now)
    submitted_at = db.Column(db.DateTime, nullable=True)
    attempt_number = db.Column(db.Integer, nullable=False, default=1)

    auto_score = db.Column(db.Numeric(6, 2), nullable=True)
    manual_score = db.Column(db.Numeric(6, 2), nullable=True)
    final_score = db.Column(db.Numeric(6, 2), nullable=True)
    max_score = db.Column(db.Numeric(6, 2), nullable=False)

    passed = db.Column(db.Boolean, nullable=False, default=False)
    needs_manual_review = db.Column(db.Boolean, nullable=False, default=False)

    __table_args__ = (
        db.UniqueConstraint(
            "quiz_id", "student_id", "attempt_number", name="uq_attempt_triple"
        ),
    )

    student = db.relationship("User", foreign_keys=[student_id])
    enrollment = db.relationship("Enrollment", foreign_keys=[enrollment_id])
    answer_entries = db.relationship(
        "QuizAnswerEntry",
        backref="attempt",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )

    @property
    def in_progress(self) -> bool:
        return self.submitted_at is None

    def to_dict(self, *, include_answers: bool = False, hide_correct: bool = True) -> dict[str, Any]:
        data: dict[str, Any] = {
            "id": self.id,
            "quizId": self.quiz_id,
            "studentId": self.student_id,
            "startedAt": _iso(self.started_at),
            "submittedAt": _iso(self.submitted_at),
            "attemptNumber": self.attempt_number,
            "autoScore": float(self.auto_score) if self.auto_score is not None else None,
            "manualScore": float(self.manual_score) if self.manual_score is not None else None,
            "finalScore": float(self.final_score) if self.final_score is not None else None,
            "maxScore": float(self.max_score),
            "passed": self.passed,
            "needsManualReview": self.needs_manual_review,
        }
        if include_answers:
            data["answers"] = [
                e.to_dict() for e in self.answer_entries.all()
            ]
        return data


class QuizAnswerEntry(db.Model):
    __tablename__ = "quiz_answer_entries"

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    attempt_id = db.Column(db.String(36), db.ForeignKey("quiz_attempts.id"), nullable=False, index=True)
    question_id = db.Column(db.String(36), db.ForeignKey("quiz_questions.id"), nullable=False, index=True)

    response_text = db.Column(db.Text, nullable=True)
    selected_option_ids = db.Column(db.Text, nullable=True)  # JSON array

    per_question_score = db.Column(db.Numeric(6, 2), nullable=True)
    is_manually_graded = db.Column(db.Boolean, nullable=False, default=False)
    manual_feedback = db.Column(db.Text, nullable=True)

    __table_args__ = (
        db.UniqueConstraint("attempt_id", "question_id", name="uq_answer_per_question"),
    )

    def to_dict(self) -> dict[str, Any]:
        import json as _json
        selected: list = []
        if self.selected_option_ids:
            try:
                selected = _json.loads(self.selected_option_ids)
            except Exception:
                selected = []
        return {
            "id": self.id,
            "attemptId": self.attempt_id,
            "questionId": self.question_id,
            "responseText": self.response_text,
            "selectedOptionIds": selected,
            "perQuestionScore": float(self.per_question_score) if self.per_question_score is not None else None,
            "isManuallyGraded": self.is_manually_graded,
            "manualFeedback": self.manual_feedback,
        }


class AttemptScoreOverride(db.Model):
    __tablename__ = "attempt_score_overrides"

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    attempt_id = db.Column(db.String(36), db.ForeignKey("quiz_attempts.id"), nullable=False, index=True)
    old_final_score = db.Column(db.Numeric(6, 2), nullable=True)
    new_final_score = db.Column(db.Numeric(6, 2), nullable=False)
    reason = db.Column(db.String(500), nullable=True)
    overridden_by_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=True)
    overridden_at = db.Column(db.DateTime, nullable=False, default=utc_now)


class QuestionBankItem(db.Model):
    """A reusable question authored at course scope. When a Quiz sets
    `pool_size=N`, its `start_attempt` picks N random items from this
    bank instead of using its own hand-written questions.
    """
    __tablename__ = "question_bank_items"

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    course_id = db.Column(
        db.String(36), db.ForeignKey("courses.id"), nullable=False, index=True,
    )
    type = db.Column(db.String(20), nullable=False, default="mc_single")
    prompt = db.Column(db.Text, nullable=False)
    points = db.Column(db.Integer, nullable=False, default=1)
    created_by_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)

    options = db.relationship(
        "QuestionBankOption", backref="bank_item", lazy="dynamic",
        cascade="all, delete-orphan", order_by="QuestionBankOption.order_index",
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "courseId": self.course_id,
            "type": self.type,
            "prompt": self.prompt,
            "points": self.points,
            "options": [o.to_dict() for o in self.options.all()],
            "createdAt": _iso(self.created_at),
        }


class QuestionBankOption(db.Model):
    __tablename__ = "question_bank_options"

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    bank_item_id = db.Column(
        db.String(36), db.ForeignKey("question_bank_items.id"),
        nullable=False, index=True,
    )
    order_index = db.Column(db.Integer, nullable=False, default=0)
    text = db.Column(db.String(500), nullable=False)
    is_correct = db.Column(db.Boolean, nullable=False, default=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "bankItemId": self.bank_item_id,
            "orderIndex": self.order_index,
            "text": self.text,
            "isCorrect": self.is_correct,
        }
