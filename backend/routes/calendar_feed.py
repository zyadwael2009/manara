"""Phase 25 — per-user ICS calendar feed + token issuance.

Endpoints:
  * `POST /api/calendar/mine/token` — creates (or rotates) the caller's
    calendar_token; returns `{token, url}`.
  * `GET  /api/calendar/mine/token`  — reads the current token (creating
    one on first read).
  * `DELETE /api/calendar/mine/token` — revokes the current token
    (existing subscribers stop receiving updates).
  * `GET  /api/calendar/<token>.ics` — public-by-token ICS feed.
    Content depends on the user's role:
      - Student: their timetable periods (repeating weekly), their
        homework posts, upcoming assignments, and open quizzes.
      - Teacher: the periods they teach + their own quiz/assignment
        deadlines.
      - Everyone else: an empty valid calendar.
"""
from __future__ import annotations

import secrets
from datetime import date as _date, datetime, timedelta

from flask import Blueprint, Response, jsonify, request

from models import (
    Assignment,
    ClassCourseTeacher,
    Enrollment,
    HomeworkPost,
    Module,
    Quiz,
    SchoolClass,
    TimetablePeriod,
    User,
    db,
)
from routes.auth import current_user, login_required
from utils.time import utc_now

calendar_feed_bp = Blueprint("calendar_feed", __name__)


def _ensure_token(user: User) -> str:
    if user.calendar_token:
        return user.calendar_token
    user.calendar_token = secrets.token_urlsafe(24)
    db.session.commit()
    return user.calendar_token


def _feed_url(token: str) -> str:
    root = request.host_url.rstrip("/")
    return f"{root}/api/calendar/{token}.ics"


# ---------------------------------------------------------------------------
# Token endpoints
# ---------------------------------------------------------------------------
@calendar_feed_bp.route("/calendar/mine/token", methods=["GET"])
@login_required
def get_token():
    user = current_user()
    token = _ensure_token(user)
    return jsonify({"token": token, "url": _feed_url(token)}), 200


@calendar_feed_bp.route("/calendar/mine/token", methods=["POST"])
@login_required
def rotate_token():
    """Force a fresh token — invalidates the old subscription."""
    user = current_user()
    user.calendar_token = secrets.token_urlsafe(24)
    db.session.commit()
    return jsonify({"token": user.calendar_token,
                    "url": _feed_url(user.calendar_token)}), 200


@calendar_feed_bp.route("/calendar/mine/token", methods=["DELETE"])
@login_required
def revoke_token():
    user = current_user()
    user.calendar_token = None
    db.session.commit()
    return "", 204


# ---------------------------------------------------------------------------
# ICS feed
# ---------------------------------------------------------------------------
@calendar_feed_bp.route("/calendar/<string:token>.ics", methods=["GET"])
def ics_feed(token: str):
    """Public-by-token. Any calendar app can subscribe. If the token was
    revoked or never created, returns 404 rather than an empty feed —
    calendar apps then stop retrying."""
    user = User.query.filter_by(calendar_token=token).first()
    if user is None or not user.is_active:
        return jsonify({"error": "Unknown or revoked token."}), 404

    ics_body = _render_ics(user)
    resp = Response(ics_body, mimetype="text/calendar; charset=utf-8")
    resp.headers["Content-Disposition"] = 'inline; filename="manara.ics"'
    return resp


# ---------------------------------------------------------------------------
# ICS assembly
# ---------------------------------------------------------------------------
def _escape(s: str | None) -> str:
    if s is None:
        return ""
    return (
        s.replace("\\", "\\\\")
         .replace(";", r"\;")
         .replace(",", r"\,")
         .replace("\n", r"\n")
    )


def _fmt_utc(dt: datetime) -> str:
    """RFC 5545 UTC timestamp (Z suffix). Use for `DTSTAMP` and any
    event whose canonical time is genuinely UTC (assignment deadlines
    stored server-side as `utc_now()`)."""
    return dt.strftime("%Y%m%dT%H%M%SZ")


def _fmt_floating(dt: datetime) -> str:
    """RFC 5545 "floating" datetime — no Z, no TZID. Interpreted in
    the viewer's local timezone. Used for period events whose canonical
    time is the school's local wall-clock (e.g. "9:00" = 9am wherever
    the calendar app is running), and for homework/quiz-window events
    that we want to show up at the same wall-clock on the client.

    Phase 25 hard-audit fix H-8: previously periods were written with
    a UTC `Z` suffix, causing every non-UTC school to see events drift
    by their offset, plus DST-driven jumps twice a year."""
    return dt.strftime("%Y%m%dT%H%M%S")


def _fmt_date(d: _date) -> str:
    return d.strftime("%Y%m%d")


def _render_ics(user: User) -> str:
    lines: list[str] = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Manara//School Calendar//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:Manara · {_escape(user.name)}",
        # Phase 25 hard-audit fix H-8: no fixed calendar timezone.
        # Period events are emitted as "floating" times (see `_fmt_floating`),
        # so they land at the school's wall-clock in every viewer's
        # local calendar regardless of the server's timezone.
    ]

    now = utc_now()
    stamp = _fmt_utc(now)

    # ---- Timetable periods -------------------------------------------------
    #
    # Student: their class's periods (once per period).
    # Teacher: every period they teach (via ClassCourseTeacher).
    # We emit each period as a WEEKLY recurring event with the first
    # occurrence anchored to a fixed reference Monday so calendars
    # extend the RRULE forward and back around it. The wall-clock is
    # emitted as floating (no timezone), so 09:00 lands at 09:00 in
    # the viewer's local calendar wherever the school is.
    #
    # Fix H-8/H-15 hard-audit: previously anchored to `now`, which
    # meant subscribing at 3pm on a Monday for a 09:00 Monday period
    # produced an event that "started 6 hours ago" and never fired.
    def _next_instance(dow_0_6: int, hh: int, mm: int) -> datetime:
        # Reference Monday: the most recent Monday at 00:00 UTC.
        today = utc_now().date()
        anchor = today - timedelta(days=today.weekday())
        target = anchor + timedelta(days=dow_0_6)
        return datetime(target.year, target.month, target.day, hh, mm)

    periods: list[tuple[TimetablePeriod, str, str | None]] = []
    if user.role == "student" and user.class_id is not None:
        sc = db.session.get(SchoolClass, user.class_id)
        for p in TimetablePeriod.query.filter_by(class_id=user.class_id).all():
            teacher_id = None
            cct = ClassCourseTeacher.query.filter_by(
                class_id=p.class_id, course_id=p.course_id,
            ).first()
            if cct is not None:
                t = db.session.get(User, cct.teacher_id)
                teacher_id = t.name if t else None
            periods.append((p, sc.name if sc else "", teacher_id))
    elif user.role == "instructor":
        cct_rows = ClassCourseTeacher.query.filter_by(teacher_id=user.id).all()
        pairs = {(r.class_id, r.course_id) for r in cct_rows}
        class_ids = {c for c, _ in pairs}
        for p in TimetablePeriod.query.filter(
            TimetablePeriod.class_id.in_(class_ids)
        ).all():
            if (p.class_id, p.course_id) not in pairs:
                continue
            sc = db.session.get(SchoolClass, p.class_id)
            periods.append((p, sc.name if sc else "", user.name))

    for p, class_name, teacher_name in periods:
        start = _next_instance(p.day_of_week, p.start_time.hour, p.start_time.minute)
        end = start.replace(hour=p.end_time.hour, minute=p.end_time.minute)
        course = p.course
        summary = f"{course.title if course else 'Class'} · {class_name}"
        room = f"Room {p.room}" if p.room else ""
        who = teacher_name or ""
        description = " · ".join(x for x in (who, room) if x)
        lines.extend([
            "BEGIN:VEVENT",
            f"UID:period-{p.id}@manara",
            f"DTSTAMP:{stamp}",
            # Floating times — see `_fmt_floating` docstring.
            f"DTSTART:{_fmt_floating(start)}",
            f"DTEND:{_fmt_floating(end)}",
            "RRULE:FREQ=WEEKLY;COUNT=52",
            f"SUMMARY:{_escape(summary)}",
            f"DESCRIPTION:{_escape(description)}",
            "END:VEVENT",
        ])

    # ---- Student-only: assignments due + open quizzes + homework posts ----
    if user.role == "student":
        enrolls = (
            Enrollment.query.filter_by(student_id=user.id)
            .filter(Enrollment.status.in_(("active", "completed")))
            .all()
        )
        course_ids = [e.course_id for e in enrolls]
        module_ids = [
            m.id for m in Module.query.filter(Module.course_id.in_(course_ids)).all()
        ] if course_ids else []

        # Assignments — one all-day event on the due date; time-stamped
        # to the actual due datetime so email reminders fire on time.
        if module_ids:
            for a in (
                Assignment.query
                .filter(Assignment.module_id.in_(module_ids))
                .filter(Assignment.is_published.is_(True))
                .filter(Assignment.due_at.isnot(None))
                .all()
            ):
                due = a.due_at
                start = due - timedelta(hours=1)
                lines.extend([
                    "BEGIN:VEVENT",
                    f"UID:assignment-{a.id}@manara",
                    f"DTSTAMP:{stamp}",
                    f"DTSTART:{_fmt_utc(start)}",
                    f"DTEND:{_fmt_utc(due)}",
                    f"SUMMARY:{_escape('Assignment due: ' + a.title)}",
                    f"DESCRIPTION:{_escape(f'{a.max_points} pts')}",
                    "END:VEVENT",
                ])

            # Quizzes — expose only quizzes with an available_until (deadline).
            for q in (
                Quiz.query.filter(Quiz.module_id.in_(module_ids))
                .filter(Quiz.is_published.is_(True))
                .filter(Quiz.available_until.isnot(None))
                .all()
            ):
                lines.extend([
                    "BEGIN:VEVENT",
                    f"UID:quiz-{q.id}@manara",
                    f"DTSTAMP:{stamp}",
                    f"DTSTART:{_fmt_utc(q.available_until - timedelta(hours=1))}",
                    f"DTEND:{_fmt_utc(q.available_until)}",
                    f"SUMMARY:{_escape('Quiz closes: ' + q.title)}",
                    "END:VEVENT",
                ])

        # Homework board posts — all-day.
        if user.class_id is not None:
            recent_from = now.date() - timedelta(days=30)
            for hp in (
                HomeworkPost.query.filter_by(class_id=user.class_id)
                .filter(HomeworkPost.date >= recent_from).all()
            ):
                # All-day VEVENT — no times.
                lines.extend([
                    "BEGIN:VEVENT",
                    f"UID:homework-{hp.id}@manara",
                    f"DTSTAMP:{stamp}",
                    f"DTSTART;VALUE=DATE:{_fmt_date(hp.date)}",
                    f"DTEND;VALUE=DATE:{_fmt_date(hp.date + timedelta(days=1))}",
                    f"SUMMARY:{_escape('Homework: ' + hp.title)}",
                    f"DESCRIPTION:{_escape(hp.body or '')}",
                    "END:VEVENT",
                ])

    lines.append("END:VCALENDAR")
    # RFC 5545: CRLF line endings.
    return "\r\n".join(lines) + "\r\n"
