"""Phase 13 — timetables.

Reads: any class stakeholder (admin, homeroom, class teacher, student in
class, linked parent). Writes: admin-only.

`/api/timetable/mine/nownext` is the live indicator endpoint used by
student + teacher home screens. It's computed server-side so the client
never has to reason about timezones.
"""
from __future__ import annotations

from datetime import date as _date, time as _time

from flask import Blueprint, jsonify, request

from models import (
    Course,
    SchoolClass,
    TIMETABLE_OVERRIDE_KINDS,
    TimetableOverride,
    TimetablePeriod,
    User,
    db,
)
from routes.auth import current_user, login_required, require_admin
from utils.permissions import (
    can_view_class_timetable,
    is_admin,
    teaches_course_in_class,
)
from utils.timetables import (
    compute_now_next,
    get_class_overrides,
    get_class_week,
    get_student_week,
    get_teacher_week,
)
from utils.validation import (
    ValidationError,
    as_str,
    one_of,
    require_fields,
    require_json,
)

timetables_bp = Blueprint("timetables", __name__)


def _parse_time(raw: str) -> _time:
    try:
        return _time.fromisoformat(raw)
    except (TypeError, ValueError):
        raise ValidationError(f"'{raw}' is not a valid HH:MM time.") from None


def _parse_date(raw: str) -> _date:
    try:
        return _date.fromisoformat(raw)
    except (TypeError, ValueError):
        raise ValidationError(f"'{raw}' is not a valid YYYY-MM-DD date.") from None


# ---------------------------------------------------------------------------
# GET class timetable — every class stakeholder can read.
# ---------------------------------------------------------------------------
@timetables_bp.route("/classes/<string:class_id>/timetable", methods=["GET"])
@login_required
def get_class_timetable(class_id: str):
    sc = db.session.get(SchoolClass, class_id)
    if sc is None:
        return jsonify({"error": "Class not found."}), 404
    user = current_user()
    # Wider read scope than the roster gate — students in the class need
    # their own schedule. `can_view_class_timetable` = admin OR homeroom
    # OR class teacher OR linked parent OR student placed in the class.
    if not can_view_class_timetable(user, sc):
        return jsonify({"error": "You do not have permission."}), 403
    return jsonify({
        "classId": sc.id,
        "className": sc.name,
        "periods": get_class_week(sc.id),
        "overridesInWindow": get_class_overrides(sc.id),
    }), 200


# ---------------------------------------------------------------------------
# PUT class periods — admin bulk-replace.
# ---------------------------------------------------------------------------
@timetables_bp.route("/classes/<string:class_id>/timetable/periods", methods=["PUT"])
@require_admin
def put_class_periods(class_id: str):
    sc = db.session.get(SchoolClass, class_id)
    if sc is None:
        return jsonify({"error": "Class not found."}), 404

    try:
        payload = require_json(request.get_json(silent=True))
        require_fields(payload, ("periods",))
        raw = payload["periods"]
        if not isinstance(raw, list):
            raise ValidationError("periods must be a list.")
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400

    # Validate every incoming row first — reject the whole PUT on any error.
    parsed: list[dict] = []
    seen_slots: set[tuple[int, str]] = set()
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            return jsonify({"error": f"periods[{i}] must be an object."}), 400
        try:
            course_id = as_str(item.get("courseId") or "", "courseId")
            day = item.get("dayOfWeek")
            if not isinstance(day, int) or not (0 <= day <= 6):
                raise ValidationError("dayOfWeek must be 0..6 (0=Mon).")
            start = _parse_time(as_str(item.get("startTime") or "", "startTime"))
            end = _parse_time(as_str(item.get("endTime") or "", "endTime"))
            if end <= start:
                raise ValidationError("endTime must be after startTime.")
            room_raw = item.get("room")
            room = None
            if room_raw:
                room = as_str(room_raw, "room", max_len=40)
            # Phase 27 — optional Meet/Zoom URL. Accept only http(s) so
            # we never render a `javascript:` or `data:` URI as a Join
            # link — the client just `launchUrl`s whatever we send back.
            meeting_url_raw = item.get("meetingUrl")
            meeting_url = None
            if meeting_url_raw not in (None, ""):
                meeting_url = as_str(meeting_url_raw, "meetingUrl", max_len=1000)
                low = meeting_url.lower().strip()
                if not (low.startswith("http://") or low.startswith("https://")):
                    raise ValidationError(
                        "meetingUrl must start with http:// or https://.")
        except ValidationError as e:
            return jsonify({"error": str(e)}), 400
        # Same-slot double-booking → 409.
        key = (day, start.strftime("%H:%M"))
        if key in seen_slots:
            return (
                jsonify({"error":
                    f"Two periods overlap on {['Mon','Tue','Wed','Thu','Fri','Sat','Sun'][day]} "
                    f"at {key[1]}. Move one."}),
                409,
            )
        seen_slots.add(key)
        course = db.session.get(Course, course_id)
        if course is None:
            return jsonify({"error": f"periods[{i}] courseId does not exist."}), 400
        if course.grade_id and course.grade_id != sc.grade_id:
            return (
                jsonify({"error":
                    f"periods[{i}] course '{course.title}' is not part of this class's grade."}),
                400,
            )
        parsed.append({
            "class_id": sc.id,
            "course_id": course_id,
            "day_of_week": day,
            "start_time": start,
            "end_time": end,
            "room": room,
            "order_index": i,
            "meeting_url": meeting_url,
        })

    # Bulk-replace.
    TimetablePeriod.query.filter_by(class_id=sc.id).delete()
    for row in parsed:
        db.session.add(TimetablePeriod(**row))
    db.session.commit()
    return jsonify({
        "classId": sc.id,
        "periods": get_class_week(sc.id),
    }), 200


# ---------------------------------------------------------------------------
# Phase 27 — PATCH the meeting URL on ONE period.
#
# Kept as its own endpoint (not stuffed into the bulk PUT above) so a
# course teacher can update the Meet link for their own period without
# having admin, and without needing to resend the full weekly grid.
# ---------------------------------------------------------------------------
@timetables_bp.route(
    "/classes/<string:class_id>/timetable/periods/<string:period_id>/meeting-url",
    methods=["PUT"],
)
@login_required
def set_period_meeting_url(class_id: str, period_id: str):
    sc = db.session.get(SchoolClass, class_id)
    if sc is None:
        return jsonify({"error": "Class not found."}), 404
    period = db.session.get(TimetablePeriod, period_id)
    if period is None or period.class_id != class_id:
        return jsonify({"error": "Period not found."}), 404

    user = current_user()
    course = db.session.get(Course, period.course_id) if period.course_id else None
    # Admin OR the teacher of this (class, course) may edit the Meet URL.
    if not is_admin(user):
        if course is None or not teaches_course_in_class(user, course, sc):
            return jsonify({"error": "You do not have permission."}), 403

    try:
        payload = require_json(request.get_json(silent=True))
        raw = payload.get("meetingUrl")
        if raw in (None, ""):
            period.meeting_url = None
        else:
            url = as_str(raw, "meetingUrl", max_len=1000)
            low = url.lower().strip()
            if not (low.startswith("http://") or low.startswith("https://")):
                raise ValidationError(
                    "meetingUrl must start with http:// or https://.")
            period.meeting_url = url
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400

    db.session.commit()
    return jsonify(period.to_dict(include_teacher=False)), 200


# ---------------------------------------------------------------------------
# Overrides
# ---------------------------------------------------------------------------
@timetables_bp.route("/classes/<string:class_id>/timetable/overrides", methods=["POST"])
@require_admin
def add_override(class_id: str):
    sc = db.session.get(SchoolClass, class_id)
    if sc is None:
        return jsonify({"error": "Class not found."}), 404
    try:
        payload = require_json(request.get_json(silent=True))
        require_fields(payload, ("date", "kind"))
        target_date = _parse_date(as_str(payload["date"], "date"))
        kind = one_of(payload["kind"], TIMETABLE_OVERRIDE_KINDS, "kind")
        period_id = payload.get("periodId")
        course_id = payload.get("courseId")
        start_raw = payload.get("startTime")
        end_raw = payload.get("endTime")
        room_raw = payload.get("room")
        note_raw = payload.get("note")
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400

    if kind == "canceled":
        if not period_id:
            return jsonify({"error": "canceled overrides require periodId."}), 400
        p = db.session.get(TimetablePeriod, period_id)
        if p is None or p.class_id != sc.id:
            return jsonify({"error": "periodId does not belong to this class."}), 400
        row = TimetableOverride(
            class_id=sc.id, date=target_date, kind="canceled", period_id=period_id,
        )
    else:  # custom
        if not (start_raw and end_raw):
            return jsonify({"error": "custom overrides require startTime + endTime."}), 400
        try:
            start = _parse_time(as_str(start_raw, "startTime"))
            end = _parse_time(as_str(end_raw, "endTime"))
            if end <= start:
                raise ValidationError("endTime must be after startTime.")
        except ValidationError as e:
            return jsonify({"error": str(e)}), 400
        row = TimetableOverride(
            class_id=sc.id, date=target_date, kind="custom",
            course_id=course_id,
            start_time=start, end_time=end,
            room=as_str(room_raw, "room", max_len=40) if room_raw else None,
            note=as_str(note_raw, "note", max_len=200) if note_raw else None,
        )
    db.session.add(row)
    db.session.commit()
    return jsonify(row.to_dict()), 201


@timetables_bp.route("/timetable/overrides/<string:ov_id>", methods=["DELETE"])
@require_admin
def delete_override(ov_id: str):
    row = db.session.get(TimetableOverride, ov_id)
    if row is None:
        return jsonify({"error": "Override not found."}), 404
    db.session.delete(row)
    db.session.commit()
    return jsonify({"message": "Deleted."}), 200


# ---------------------------------------------------------------------------
# My timetable + Now/Next — student/teacher scoped.
# ---------------------------------------------------------------------------
@timetables_bp.route("/timetable/mine/week", methods=["GET"])
@login_required
def get_my_week():
    user = current_user()
    if user.role == "student":
        return jsonify({"periods": get_student_week(user)}), 200
    if user.role == "instructor":
        return jsonify({"periods": get_teacher_week(user)}), 200
    # Admin / parent → not scoped by "my" here; use the class endpoint.
    return jsonify({"periods": []}), 200


@timetables_bp.route("/timetable/mine/nownext", methods=["GET"])
@login_required
def get_my_now_next():
    user = current_user()
    return jsonify(compute_now_next(user)), 200
