"""Streaks and badges."""
from __future__ import annotations

from models.base import (
    db,
    Any,
)

# =============================================================================
# Phase 24 — Streaks / badges / question bank
# =============================================================================
class StudentStreak(db.Model):
    """Per-student daily-open streak. Ticked once per session-start.

    A "day" is a UTC calendar date. Consecutive days grow the streak;
    a gap of >1 day resets to 1.
    """
    __tablename__ = "student_streaks"

    user_id = db.Column(
        db.String(36), db.ForeignKey("users.id"),
        primary_key=True,
    )
    current_streak = db.Column(db.Integer, nullable=False, default=0)
    longest_streak = db.Column(db.Integer, nullable=False, default=0)
    last_activity_date = db.Column(db.Date, nullable=True)

    def to_dict(self) -> dict[str, Any]:
        return {
            "userId": self.user_id,
            "currentStreak": self.current_streak,
            "longestStreak": self.longest_streak,
            "lastActivityDate": (
                self.last_activity_date.isoformat()
                if self.last_activity_date else None
            ),
        }
