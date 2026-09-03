"""Phase 18 — the student "Today" landing endpoint.

One aggregate call for the inline card that sits at the top of My classes:
today's remaining periods, assignments due today, and open quizzes with
attempts still available.

Read-only. No writes, no trust-core impact. Every query is keyed on
`current_user()` and filtered through the caller's own enrollments.
"""
from __future__ import annotations

from datetime import date as _date, datetime

from flask import Blueprint, jsonify

from models import (
    Assignment,
    Enrollment,
    Module,
    Quiz,
    User,
    db,
)
from routes.auth import current_user, login_required
from utils.permissions import is_student
from utils.quizzes import compute_student_quiz_history
from utils.timetables import _resolve_periods_for_date
from utils.time import utc_now

today_bp = Blueprint("today", __name__)


def _now() -> datetime:
    return utc_now()


@today_bp.route("/students/today", methods=["GET"])
@today_bp.route("/students/today/", methods=["GET"])
@login_required
def my_today():
    user: User = current_user()
    if not is_student(user):
        # Non-students see empty everything. Keeps the endpoint safe for
        # accidental calls from other UIs without leaking data.
        return jsonify({
            "date": _date.today().isoformat(),
            "periods": [],
            "assignmentsDueToday": [],
            "openQuizzes": [],
        }), 200

    today = _date.today()
    now = _now()

    # --- Today's periods for the student's class -----------------------
    periods: list[dict] = []
    if user.class_id is not None:
        periods = _resolve_periods_for_date(user.class_id, today)

    # --- Assignments due today across the caller's live enrollments ----
    enrolls = (
        Enrollment.query.filter_by(student_id=user.id)
        .filter(Enrollment.status.in_(("active", "completed")))
        .all()
    )
    course_ids = [e.course_id for e in enrolls]
    course_by_id = {e.course_id: e.course for e in enrolls if e.course is not None}

    assignments_due: list[dict] = []
    if course_ids:
        # Assignment.due_at is a DateTime — filter for [today 00:00, tomorrow 00:00).
        day_start = datetime(today.year, today.month, today.day)
        day_end = datetime.fromordinal(today.toordinal() + 1)
        module_ids_for_courses = [
            m.id for m in Module.query.filter(Module.course_id.in_(course_ids)).all()
        ]
        due_rows = (
            Assignment.query
            .filter(Assignment.module_id.in_(module_ids_for_courses))
            .filter(Assignment.is_published.is_(True))
            .filter(Assignment.due_at.isnot(None))
            .filter(Assignment.due_at >= day_start)
            .filter(Assignment.due_at < day_end)
            .all()
        ) if module_ids_for_courses else []
        for a in due_rows:
            module = db.session.get(Module, a.module_id)
            course = course_by_id.get(module.course_id) if module else None
            assignments_due.append({
                "id": a.id,
                "title": a.title,
                "dueAt": a.due_at.isoformat() + "Z" if a.due_at else None,
                "maxPoints": a.max_points,
                "moduleId": a.module_id,
                "moduleTitle": module.title if module else "",
                "courseId": course.id if course else None,
                "courseTitle": course.title if course else "",
            })

    # --- Open quizzes: published, in a live enrollment, attempts remain
    open_quizzes: list[dict] = []
    if course_ids:
        module_ids_for_courses = [
            m.id for m in Module.query.filter(Module.course_id.in_(course_ids)).all()
        ]
        pub_quizzes = (
            Quiz.query.filter(Quiz.module_id.in_(module_ids_for_courses))
            .filter(Quiz.is_published.is_(True))
            .all()
        ) if module_ids_for_courses else []
        history = compute_student_quiz_history(user.id, [q.id for q in pub_quizzes])
        for q in pub_quizzes:
            hist = history.get(q.id)
            attempts_used = hist["attemptsCount"] if hist else 0
            cap_ok = (q.max_attempts is None) or (attempts_used < q.max_attempts)
            window_ok = True
            if q.available_from and now < q.available_from:
                window_ok = False
            if q.available_until and now > q.available_until:
                window_ok = False
            if not (cap_ok and window_ok):
                continue
            module = db.session.get(Module, q.module_id)
            course = course_by_id.get(module.course_id) if module else None
            open_quizzes.append({
                "id": q.id,
                "title": q.title,
                "totalPoints": q.total_points(),
                "attemptsUsed": attempts_used,
                "maxAttempts": q.max_attempts,
                "passingScore": q.passing_score,
                "courseId": course.id if course else None,
                "courseTitle": course.title if course else "",
                "moduleTitle": module.title if module else "",
            })

    return jsonify({
        "date": today.isoformat(),
        "periods": periods,
        "assignmentsDueToday": assignments_due,
        "openQuizzes": open_quizzes,
    }), 200
