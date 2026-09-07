"""Everything that reaches a person: announcements, the notification feed and its preferences, direct messages, lesson comments, the homework board, and browser push subscriptions."""
from __future__ import annotations

from models.base import (
    db,
    generate_uuid,
    utc_now,
    _iso,
    Any,
)

class Announcement(db.Model):
    __tablename__ = "announcements"

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    audience = db.Column(db.String(20), nullable=False)  # ANNOUNCEMENT_AUDIENCES
    class_id = db.Column(
        db.String(36), db.ForeignKey("classes.id"), nullable=True, index=True,
    )
    course_id = db.Column(
        db.String(36), db.ForeignKey("courses.id"), nullable=True, index=True,
    )
    author_id = db.Column(
        db.String(36), db.ForeignKey("users.id"), nullable=False, index=True,
    )
    title = db.Column(db.String(200), nullable=False)
    body = db.Column(db.Text, nullable=False, default="")
    expires_at = db.Column(db.DateTime, nullable=True)

    created_at = db.Column(db.DateTime, nullable=False, default=utc_now, index=True)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=utc_now, onupdate=utc_now,
    )

    author = db.relationship("User", foreign_keys=[author_id])
    school_class = db.relationship("SchoolClass", foreign_keys=[class_id])
    course = db.relationship("Course", foreign_keys=[course_id])

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "audience": self.audience,
            "classId": self.class_id,
            "className": self.school_class.name if self.school_class else None,
            "courseId": self.course_id,
            "courseTitle": self.course.title if self.course else None,
            "authorId": self.author_id,
            "authorName": self.author.name if self.author else None,
            "title": self.title,
            "body": self.body,
            "createdAt": _iso(self.created_at),
            "updatedAt": _iso(self.updated_at),
            "expiresAt": _iso(self.expires_at),
        }


# =============================================================================
# Phase 21 — Communication & engagement
#
# All four tables are additive and read-only from a trust-core point of view.
# The `enqueue()` helper in `utils/notifications.py` writes into
# `notifications`; the DM + comments + homework blueprints own their own
# tables. Nothing here touches enrollment, grade, or certificate state.
# =============================================================================
# Every kind `utils.notifications.enqueue()` is ever called with. This is the
# single source of truth: it drives both the opt-out list the preferences
# screen renders and the validation on writes to it.
#
# It was previously declared here AND redeclared further down for the Phase 32
# preferences work, with a different set of names. The second definition
# silently shadowed this one at import time, so the preferences screen offered
# `grade_posted`, `cert_issued`, `attendance_absent`, `quiz_due` and
# `streak_reminder` — none of which anything emits — while the four kinds the
# app really does send under other names (`grade_updated`,
# `attendance_marked`, `certificate_issued`, `comment_reply`) could not be
# switched off at all: `enqueue()` looks preferences up by the emitted kind,
# found no row, and fell open.
NOTIFICATION_KINDS = (
    "announcement",
    "assignment_graded",
    "attendance_marked",
    "certificate_issued",
    "comment_reply",
    "fee_created",
    "fee_overdue",
    "fee_payment",
    "grade_updated",
    "message",
)


class Notification(db.Model):
    """One row per delivered event to one user's inbox.

    Idempotency (see `utils.notifications.enqueue`): a same-day duplicate
    on `(user_id, kind, ref_type, ref_id)` is suppressed so a rerun of
    a rollup pipeline doesn't spam the bell.
    """
    __tablename__ = "notifications"

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    user_id = db.Column(
        db.String(36), db.ForeignKey("users.id"), nullable=False, index=True,
    )
    kind = db.Column(db.String(40), nullable=False)  # NOTIFICATION_KINDS
    title = db.Column(db.String(200), nullable=False)
    body = db.Column(db.Text, nullable=False, default="")
    ref_type = db.Column(db.String(40), nullable=True)  # "course" | "quiz" | ...
    ref_id = db.Column(db.String(36), nullable=True)
    read_at = db.Column(db.DateTime, nullable=True, index=True)
    created_at = db.Column(
        db.DateTime, nullable=False, default=utc_now, index=True,
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "userId": self.user_id,
            "kind": self.kind,
            "title": self.title,
            "body": self.body,
            "refType": self.ref_type,
            "refId": self.ref_id,
            "readAt": _iso(self.read_at),
            "createdAt": _iso(self.created_at),
        }


class MessageThread(db.Model):
    """One thread pairs one parent with one teacher on a subject.

    Same (parent, teacher, subject) triple → same thread — the compose
    flow either creates one or replies into the existing one so the
    inbox stays tidy.
    """
    __tablename__ = "message_threads"

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    parent_id = db.Column(
        db.String(36), db.ForeignKey("users.id"), nullable=False, index=True,
    )
    teacher_id = db.Column(
        db.String(36), db.ForeignKey("users.id"), nullable=False, index=True,
    )
    subject = db.Column(db.String(200), nullable=False, default="")
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)
    last_message_at = db.Column(
        db.DateTime, nullable=False, default=utc_now, index=True,
    )

    parent = db.relationship("User", foreign_keys=[parent_id])
    teacher = db.relationship("User", foreign_keys=[teacher_id])
    messages = db.relationship(
        "Message", backref="thread", lazy="dynamic",
        cascade="all, delete-orphan",
    )

    def to_dict(self, *, viewer_id: str | None = None) -> dict[str, Any]:
        last = (
            self.messages.order_by(Message.created_at.desc()).first()
        )
        return {
            "id": self.id,
            "parentId": self.parent_id,
            "parentName": self.parent.name if self.parent else None,
            "teacherId": self.teacher_id,
            "teacherName": self.teacher.name if self.teacher else None,
            "subject": self.subject,
            "createdAt": _iso(self.created_at),
            "lastMessageAt": _iso(self.last_message_at),
            "lastMessagePreview": (last.body[:120] if last else ""),
            "hasUnreadForViewer": (
                viewer_id is not None
                and last is not None
                and last.author_id != viewer_id
                and last.read_by_other_at is None
            ),
        }


class Message(db.Model):
    __tablename__ = "messages"

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    thread_id = db.Column(
        db.String(36), db.ForeignKey("message_threads.id"), nullable=False, index=True,
    )
    author_id = db.Column(
        db.String(36), db.ForeignKey("users.id"), nullable=False, index=True,
    )
    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)
    read_by_other_at = db.Column(db.DateTime, nullable=True)

    author = db.relationship("User", foreign_keys=[author_id])

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "threadId": self.thread_id,
            "authorId": self.author_id,
            "authorName": self.author.name if self.author else None,
            "body": self.body,
            "createdAt": _iso(self.created_at),
            "readByOtherAt": _iso(self.read_by_other_at),
        }


class LessonComment(db.Model):
    """Question + one-deep answers thread under one lesson.

    `parent_comment_id` is null for a top-level question; set to the
    question's id for an answer. Author + admin can delete their own.
    """
    __tablename__ = "lesson_comments"

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    lesson_id = db.Column(
        db.String(36), db.ForeignKey("lessons.id"), nullable=False, index=True,
    )
    author_id = db.Column(
        db.String(36), db.ForeignKey("users.id"), nullable=False, index=True,
    )
    parent_comment_id = db.Column(
        db.String(36), db.ForeignKey("lesson_comments.id"), nullable=True, index=True,
    )
    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(
        db.DateTime, nullable=False, default=utc_now, index=True,
    )

    author = db.relationship("User", foreign_keys=[author_id])

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "lessonId": self.lesson_id,
            "authorId": self.author_id,
            "authorName": self.author.name if self.author else None,
            "authorRole": self.author.role if self.author else None,
            "parentCommentId": self.parent_comment_id,
            "body": self.body,
            "createdAt": _iso(self.created_at),
        }


class HomeworkPost(db.Model):
    """One post per class per school day, upserted by the homeroom teacher."""
    __tablename__ = "homework_posts"

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    class_id = db.Column(
        db.String(36), db.ForeignKey("classes.id"), nullable=False, index=True,
    )
    author_id = db.Column(
        db.String(36), db.ForeignKey("users.id"), nullable=False, index=True,
    )
    date = db.Column(db.Date, nullable=False, index=True)
    title = db.Column(db.String(200), nullable=False, default="")
    body = db.Column(db.Text, nullable=False, default="")
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=utc_now, onupdate=utc_now,
    )

    __table_args__ = (
        db.UniqueConstraint("class_id", "date", name="uq_homework_class_date"),
    )

    author = db.relationship("User", foreign_keys=[author_id])
    school_class = db.relationship("SchoolClass", foreign_keys=[class_id])

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "classId": self.class_id,
            "className": self.school_class.name if self.school_class else None,
            "authorId": self.author_id,
            "authorName": self.author.name if self.author else None,
            "date": self.date.isoformat() if self.date else None,
            "title": self.title,
            "body": self.body,
            "createdAt": _iso(self.created_at),
            "updatedAt": _iso(self.updated_at),
        }


# =============================================================================
# Phase 28 — Web Push subscriptions
#
# One row per (user, browser session). Endpoint + p256dh + auth are the
# opaque strings the browser Push API returns; the backend signs a VAPID
# JWT and POSTs to `endpoint` to deliver a notification. `platform` is
# forward-looking — always 'web' this phase, kept as a column so a
# future mobile FCM sub can plug in without a migration.
#
# Trust-core: touches no grade or enrollment state. Best-effort delivery
# only; stale endpoints (410 from the push service) are auto-pruned.
# =============================================================================
class PushSubscription(db.Model):
    __tablename__ = "push_subscriptions"

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    user_id = db.Column(
        db.String(36), db.ForeignKey("users.id"), nullable=False, index=True,
    )
    endpoint = db.Column(db.String(1000), nullable=False)
    p256dh = db.Column(db.String(200), nullable=False)
    auth = db.Column(db.String(80), nullable=False)
    user_agent = db.Column(db.String(400), nullable=True)
    platform = db.Column(db.String(20), nullable=False, default="web")
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)
    last_seen_at = db.Column(db.DateTime, nullable=False, default=utc_now)

    __table_args__ = (
        db.UniqueConstraint(
            "user_id", "endpoint", name="uq_push_user_endpoint",
        ),
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "userId": self.user_id,
            "endpoint": self.endpoint,
            "platform": self.platform,
            "userAgent": self.user_agent,
            "createdAt": _iso(self.created_at),
            "lastSeenAt": _iso(self.last_seen_at),
        }


# =============================================================================
# Phase 32 · T1 — Notification preferences
#
# One row per (user, kind). Absence of a row means "enabled" (the
# default) so a freshly-registered user gets the bell for everything
# without a seed step. `utils/notifications.enqueue` reads this table
# and skips the write when the user has opted out — the trust-core
# grade/attendance/assignment write pipelines never care.
#
# `kind` is the same string used everywhere `enqueue()` is called
# today: "grade_posted", "assignment_graded", "fee_created",
# "fee_payment", "fee_overdue", "announcement", "message", "quiz_due",
# "attendance_absent", "streak_reminder", "cert_issued". Unknown kinds
# are always allowed (fail-open) so a new notification type ships
# without a per-user opt-in flag day.
# =============================================================================
# The kinds a user can opt out of are `NOTIFICATION_KINDS`, declared once with
# the Notification model above. A second, divergent copy used to live here and
# shadowed it — see the comment on that declaration.
#
# It stays a plain tuple rather than a Column constraint because the enqueue
# writer must fail open on an unknown kind: a newly added notification type
# should reach people before anyone backfills preference rows for it.


class NotificationPreference(db.Model):
    __tablename__ = "notification_preferences"

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    user_id = db.Column(
        db.String(36), db.ForeignKey("users.id"),
        nullable=False, index=True,
    )
    kind = db.Column(db.String(40), nullable=False)
    enabled = db.Column(db.Boolean, nullable=False, default=True)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=utc_now,
        onupdate=utc_now,
    )

    __table_args__ = (
        db.UniqueConstraint("user_id", "kind", name="uq_notif_pref_user_kind"),
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "userId": self.user_id,
            "kind": self.kind,
            "enabled": self.enabled,
            "updatedAt": _iso(self.updated_at),
        }
