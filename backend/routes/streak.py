"""Phase 24 — daily-open streak + on-the-fly badges.

Streak:
  * `POST /api/streak/tick` — the client calls this once per session
    start. Server updates the streak; +1 for consecutive UTC days,
    reset to 1 on a gap, no-op if already ticked today.
  * `GET  /api/streak/mine`  — read current state.

Badges are computed on the fly from existing tables — no new writes.
"""
from __future__ import annotations

from datetime import datetime

from flask import Blueprint, jsonify

from models import (
    AttendanceMark,
    Certificate,
    Enrollment,
    QuizAttempt,
    StudentStreak,
    db,
)
from routes.auth import current_user, login_required
from utils.permissions import is_student
from utils.time import utc_now

streak_bp = Blueprint("streak", __name__)


def _get_or_create(user_id: str) -> StudentStreak:
    s = db.session.get(StudentStreak, user_id)
    if s is None:
        s = StudentStreak(user_id=user_id, current_streak=0, longest_streak=0)
        db.session.add(s)
    return s


@streak_bp.route("/streak/tick", methods=["POST"])
@login_required
def tick_streak():
    user = current_user()
    if not is_student(user):
        # Only students accrue streaks; keep the endpoint quiet for others
        # so the client can call it unconditionally on session start.
        return jsonify({"userId": user.id, "currentStreak": 0,
                        "longestStreak": 0, "lastActivityDate": None}), 200
    s = _get_or_create(user.id)
    # Phase 25 hard-audit fix H-7: docstring + model comment promise
    # UTC calendar days, but `_date.today()` returns the SERVER's
    # local date. Every other timestamp in the app uses `utc_now()`;
    # this switches to match so a school running the server outside
    # UTC doesn't see phantom midnight resets that disagree with
    # `notification.created_at` and other timestamps.
    today = utc_now().date()
    if s.last_activity_date == today:
        pass  # already ticked
    elif s.last_activity_date is None:
        s.current_streak = 1
    else:
        gap = (today - s.last_activity_date).days
        if gap == 1:
            s.current_streak += 1
        elif gap > 1:
            s.current_streak = 1
        # gap < 1 shouldn't happen with UTC dates but is a no-op if it does.
    if s.current_streak > s.longest_streak:
        s.longest_streak = s.current_streak
    s.last_activity_date = today
    db.session.commit()
    return jsonify(s.to_dict()), 200


@streak_bp.route("/streak/mine", methods=["GET"])
@login_required
def get_streak():
    user = current_user()
    s = db.session.get(StudentStreak, user.id) or StudentStreak(
        user_id=user.id, current_streak=0, longest_streak=0,
    )
    return jsonify(s.to_dict()), 200


# ---------------------------------------------------------------------------
# Badges (computed on the fly — no writes)
# ---------------------------------------------------------------------------
_BADGE_DEFS = [
    ("first_cert", "First certificate", "workspace_premium",
     "You earned your first certificate."),
    ("five_quiz_streak", "Five in a row", "auto_awesome",
     "Passed 5 quizzes without a fail in between."),
    ("perfect_week", "Perfect week", "event_available",
     "Present or excused every day this week."),
    ("ten_day_streak", "10-day streak", "local_fire_department",
     "Opened Manara 10 days in a row."),
]


@streak_bp.route("/badges/mine", methods=["GET"])
@login_required
def my_badges():
    user = current_user()
    earned_ids: set[str] = set()

    if is_student(user):
        # first_cert — any un-revoked certificate.
        has_cert = (
            db.session.query(Certificate.id)
            .join(Enrollment, Enrollment.id == Certificate.enrollment_id)
            .filter(Enrollment.student_id == user.id)
            .filter(Certificate.revoked.is_(False))
            .first()
        ) is not None
        if has_cert:
            earned_ids.add("first_cert")

        # five_quiz_streak — walk attempts chronologically, count consec
        # passes across every quiz. Any fail resets to 0.
        rows = (
            QuizAttempt.query
            .filter_by(student_id=user.id)
            .filter(QuizAttempt.submitted_at.isnot(None))
            .order_by(QuizAttempt.submitted_at.asc())
            .all()
        )
        streak = 0
        best = 0
        for a in rows:
            if a.passed:
                streak += 1
                if streak > best:
                    best = streak
            else:
                streak = 0
        if best >= 5:
            earned_ids.add("five_quiz_streak")

        # perfect_week — last 7 dates with a mark must all be present/excused.
        today = utc_now().date()
        from datetime import timedelta
        week_ago = today - timedelta(days=6)
        marks = (
            AttendanceMark.query.filter_by(student_id=user.id)
            .filter(AttendanceMark.date >= week_ago)
            .all()
        )
        if marks and all(m.status in ("present", "excused") for m in marks):
            earned_ids.add("perfect_week")

        # ten_day_streak — from the streak row.
        s = db.session.get(StudentStreak, user.id)
        if s is not None and s.longest_streak >= 10:
            earned_ids.add("ten_day_streak")

    badges = [
        {"id": bid, "title": title, "icon": icon, "description": desc,
         "earned": bid in earned_ids}
        for bid, title, icon, desc in _BADGE_DEFS
    ]
    return jsonify({"badges": badges, "earnedCount": len(earned_ids)}), 200
