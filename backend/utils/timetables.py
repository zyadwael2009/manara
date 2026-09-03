"""Phase 13 — timetable read helpers + Now/Next computation.

The base weekly schedule lives in `timetable_periods`. Date-based
exceptions live in `timetable_overrides` and are applied on the fly at
read time — no denormalized "materialized week" table. This keeps the
data source of truth tight and lets an admin edit either side without
running a background job.

Timezone: everything is naive `utc_now()` / `date.today()`.
For the demo school (single tenant, single timezone) that's fine;
multi-tenant/multi-tz would need a per-school timezone column and
per-request conversion.
"""
from __future__ import annotations

from datetime import date as _date, datetime, time as _time, timedelta

from models import (
    ClassCourseTeacher,
    SchoolClass,
    TimetableOverride,
    TimetablePeriod,
    User,
    db,
)
from utils.time import utc_now


# ---------------------------------------------------------------------------
# Class-scoped week (base weekly, no overrides applied)
# ---------------------------------------------------------------------------
def get_class_week(class_id: str) -> list[dict]:
    """Base weekly schedule for one class, ordered (day, start_time)."""
    periods = (
        TimetablePeriod.query.filter_by(class_id=class_id)
        .order_by(TimetablePeriod.day_of_week, TimetablePeriod.start_time)
        .all()
    )
    return [p.to_dict() for p in periods]


def get_class_overrides(class_id: str, days_ahead: int = 30) -> list[dict]:
    """Overrides in the next `days_ahead` days for this class."""
    today = _date.today()
    end = today + timedelta(days=days_ahead)
    rows = (
        TimetableOverride.query.filter_by(class_id=class_id)
        .filter(TimetableOverride.date >= today)
        .filter(TimetableOverride.date <= end)
        .order_by(TimetableOverride.date, TimetableOverride.start_time.nullslast())
        .all()
    )
    return [r.to_dict() for r in rows]


# ---------------------------------------------------------------------------
# Student / teacher week
# ---------------------------------------------------------------------------
def get_student_week(student: User) -> list[dict]:
    """A student's week = their class's week. Empty if unplaced."""
    if student is None or student.class_id is None:
        return []
    return get_class_week(student.class_id)


def get_teacher_week(teacher: User) -> list[dict]:
    """A teacher's aggregated week = every period whose (class, course) they
    teach. One teacher can teach the same course in multiple classes → one
    entry per (day, start_time, class).
    """
    if teacher is None:
        return []
    cct_rows = ClassCourseTeacher.query.filter_by(teacher_id=teacher.id).all()
    if not cct_rows:
        return []
    pairs = {(r.class_id, r.course_id) for r in cct_rows}
    class_ids = {r.class_id for r in cct_rows}
    periods = (
        TimetablePeriod.query.filter(TimetablePeriod.class_id.in_(class_ids))
        .order_by(TimetablePeriod.day_of_week, TimetablePeriod.start_time)
        .all()
    )
    out: list[dict] = []
    for p in periods:
        if (p.class_id, p.course_id) not in pairs:
            continue
        d = p.to_dict()
        sc = db.session.get(SchoolClass, p.class_id)
        d["className"] = sc.name if sc else None
        out.append(d)
    return out


# ---------------------------------------------------------------------------
# Now / Next
# ---------------------------------------------------------------------------
def _resolve_periods_for_date(class_id: str, target: _date) -> list[dict]:
    """The effective schedule for one class on one date — base periods for
    the weekday, MINUS canceled overrides, PLUS custom overrides. Sorted
    by start_time."""
    dow = target.weekday()  # 0=Mon .. 6=Sun
    base = list(
        TimetablePeriod.query.filter_by(class_id=class_id, day_of_week=dow).all()
    )
    overrides = list(
        TimetableOverride.query.filter_by(class_id=class_id, date=target).all()
    )
    canceled_ids = {o.period_id for o in overrides if o.kind == "canceled" and o.period_id}
    effective: list[dict] = []
    for p in base:
        if p.id in canceled_ids:
            continue
        d = p.to_dict()
        d["_start"] = p.start_time
        effective.append(d)
    for o in overrides:
        if o.kind != "custom" or o.start_time is None:
            continue
        d = o.to_dict()
        # Shape the override to look like a period entry for the client.
        d["dayOfWeek"] = dow
        d["isOverride"] = True
        d["_start"] = o.start_time
        effective.append(d)
    effective.sort(key=lambda x: x["_start"])
    for d in effective:
        d.pop("_start", None)
    return effective


def compute_now_next(user: User, now: datetime | None = None) -> dict:
    """Return {"now": …, "next": …} for the user. Uses the user's own
    class (if student) or their aggregated teaching (if teacher).

    Admin / parent / unlinked user → both None. Parents view their child's
    schedule through the child-dashboard, not this endpoint.
    """
    if user is None:
        return {"now": None, "next": None}
    now = now or utc_now()
    today = now.date()
    now_t = now.time()

    # Collect (source_class_id, effective_periods_for_today) rows.
    class_ids: list[str] = []
    if user.role == "student" and user.class_id:
        class_ids = [user.class_id]
    elif user.role == "instructor":
        class_ids = list({r.class_id for r in ClassCourseTeacher.query.filter_by(
            teacher_id=user.id,
        ).all()})
    if not class_ids:
        return {"now": None, "next": None}

    # Assemble today's periods across all relevant classes, sorted by time.
    todays: list[dict] = []
    for cid in class_ids:
        for entry in _resolve_periods_for_date(cid, today):
            entry["_class_id"] = cid
            todays.append(entry)
    todays.sort(key=lambda x: x.get("startTime") or "")

    # For teachers, only surface periods where they're the class teacher on
    # THIS course; get_student_week already scopes right for students.
    if user.role == "instructor":
        allowed_pairs = {
            (r.class_id, r.course_id)
            for r in ClassCourseTeacher.query.filter_by(teacher_id=user.id).all()
        }
        todays = [
            e for e in todays
            if e.get("isOverride")  # customs pass through
            or (e["_class_id"], e.get("courseId")) in allowed_pairs
        ]

    now_slot = None
    next_slot = None
    for e in todays:
        start = e.get("startTime")
        end = e.get("endTime")
        if not start or not end:
            continue
        st = _time.fromisoformat(start)
        et = _time.fromisoformat(end)
        if st <= now_t <= et:
            now_slot = {
                "period": e,
                "endsAt": end,
                "endsInMinutes": _minutes_between(now_t, et),
            }
        elif st > now_t and next_slot is None:
            next_slot = {
                "period": e,
                "startsAt": start,
                "startsInMinutes": _minutes_between(now_t, st),
                "sameDay": True,
            }

    # If no "next" today, fall through to tomorrow's first period.
    if next_slot is None:
        tomorrow = today + timedelta(days=1)
        for cid in class_ids:
            for entry in _resolve_periods_for_date(cid, tomorrow):
                if entry.get("startTime"):
                    next_slot = {
                        "period": entry,
                        "startsAt": entry["startTime"],
                        "startsInMinutes": None,
                        "sameDay": False,
                    }
                    break
            if next_slot is not None:
                break

    return {"now": now_slot, "next": next_slot}


def _minutes_between(a: _time, b: _time) -> int:
    """(b - a) in whole minutes, floored to 0."""
    a_min = a.hour * 60 + a.minute
    b_min = b.hour * 60 + b.minute
    return max(0, b_min - a_min)
