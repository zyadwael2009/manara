"""Phase 12 — daily attendance.

Homeroom teacher (per class) + admin can mark. Any staff who can see a
student's records + linked parent + the student themself can read.

Same-day edits are free; backdating (writing a date != today) is
admin-only. This matches real K-12 policy — homeroom fixes mistakes
inside the day, past days need office sign-off.

Writes end with `roll_up_to_commitment` + `recompute_enrollment_cache`
+ `maybe_issue_certificate` for every affected student. The Commitment
grade category picks up the attendance fraction so cumulative % (and
therefore the cert gate) updates transactionally.
"""
from __future__ import annotations

from datetime import date as _date

from flask import Blueprint, jsonify, request

from models import (
    ATTENDANCE_STATUSES,
    AttendanceMark,
    Enrollment,
    ParentStudentLink,
    SchoolClass,
    User,
    db,
)
from routes.auth import current_user, login_required
from utils.pagination import paginate
from utils.attendance import roll_up_to_commitment
from utils.certificates import maybe_issue_certificate
from utils.grading import recompute_enrollment_cache
from utils.permissions import (
    can_mark_attendance,
    can_view_student_records,
    homerooms_class,
    is_admin,
    is_instructor,
    is_student,
    teaches_course_in_any_class,
)
from utils.validation import (
    ValidationError,
    as_str,
    one_of,
    require_fields,
    require_json,
)

attendance_bp = Blueprint("attendance", __name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _parse_iso_date(raw: str) -> _date:
    try:
        return _date.fromisoformat(raw)
    except (TypeError, ValueError):
        raise ValidationError(f"'{raw}' is not a valid YYYY-MM-DD date.") from None


def _can_view_class_attendance(user, sc: SchoolClass) -> bool:
    """Admin, homeroom teacher of the class, or any course teacher of the
    class. Everyone else 403 — same shape as the Phase 9 class-roster gate.
    """
    if user is None:
        return False
    if is_admin(user):
        return True
    if homerooms_class(user, sc):
        return True
    if is_instructor(user):
        from models import ClassCourseTeacher
        row = ClassCourseTeacher.query.filter_by(
            class_id=sc.id, teacher_id=user.id,
        ).first()
        if row is not None:
            return True
    return False


# ---------------------------------------------------------------------------
# GET class attendance for a date — roster with each student's mark (or null)
# ---------------------------------------------------------------------------
@attendance_bp.route("/classes/<string:class_id>/attendance", methods=["GET"])
@login_required
def get_class_attendance(class_id: str):
    sc = db.session.get(SchoolClass, class_id)
    if sc is None:
        return jsonify({"error": "Class not found."}), 404
    user = current_user()
    if not _can_view_class_attendance(user, sc):
        return jsonify({"error": "You do not have permission."}), 403

    raw_date = (request.args.get("date") or "").strip()
    if not raw_date:
        raw_date = _date.today().isoformat()
    try:
        target_date = _parse_iso_date(raw_date)
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400

    students = list(sc.students.all())
    marks_by_student = {
        m.student_id: m
        for m in AttendanceMark.query.filter_by(class_id=sc.id, date=target_date).all()
    }
    out = []
    for s in students:
        m = marks_by_student.get(s.id)
        out.append({
            "student": {"id": s.id, "name": s.name, "email": s.email},
            "mark": m.to_dict() if m else None,
        })
    return jsonify({
        "classId": sc.id,
        "className": sc.name,
        "date": target_date.isoformat(),
        "rows": out,
        "canWrite": bool(is_admin(user) or homerooms_class(user, sc)),
        "isToday": target_date == _date.today(),
    }), 200


# ---------------------------------------------------------------------------
# PUT bulk-upsert class attendance for a date
# ---------------------------------------------------------------------------
@attendance_bp.route("/classes/<string:class_id>/attendance", methods=["PUT"])
@login_required
def put_class_attendance(class_id: str):
    sc = db.session.get(SchoolClass, class_id)
    if sc is None:
        return jsonify({"error": "Class not found."}), 404
    user = current_user()
    if not (is_admin(user) or homerooms_class(user, sc)):
        return jsonify({"error": "You do not have permission."}), 403

    try:
        payload = require_json(request.get_json(silent=True))
        require_fields(payload, ("date", "marks"))
        target_date = _parse_iso_date(as_str(payload["date"], "date"))
        marks_in = payload["marks"]
        if not isinstance(marks_in, list):
            raise ValidationError("marks must be a list.")
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400

    # Same-day edits free; backdating (or forward-dating) requires admin.
    if target_date != _date.today() and not is_admin(user):
        return (
            jsonify({"error": "Only admin can mark attendance for a date other than today."}),
            403,
        )

    # Restrict marks to students currently placed in this class — a
    # homeroom shouldn't write marks for someone else's class.
    valid_student_ids = {s.id for s in sc.students.all()}
    touched_student_ids: set[str] = set()
    # Phase 21 — track notable marks (absent/late/excused) so we can
    # ping the student + linked parents at commit time.
    notable_marks: list[tuple[str, str]] = []  # (student_id, status)

    for item in marks_in:
        if not isinstance(item, dict):
            continue
        try:
            student_id = as_str(item.get("studentId") or "", "studentId")
            status = one_of(item.get("status"), ATTENDANCE_STATUSES, "status")
            reason_raw = item.get("reason") or ""
            reason = as_str(reason_raw, "reason", max_len=200) or None if reason_raw else None
        except ValidationError as e:
            return jsonify({"error": str(e)}), 400
        if student_id not in valid_student_ids:
            return (
                jsonify({"error": f"Student {student_id} is not in this class."}),
                400,
            )

        row = AttendanceMark.query.filter_by(
            student_id=student_id, date=target_date,
        ).first()
        if row is None:
            row = AttendanceMark(
                student_id=student_id,
                class_id=sc.id,
                date=target_date,
                status=status,
                reason=reason,
                marked_by_id=user.id,
            )
            db.session.add(row)
        else:
            row.status = status
            row.reason = reason
            row.marked_by_id = user.id
        touched_student_ids.add(student_id)
        if status in ("absent", "late", "excused"):
            notable_marks.append((student_id, status))

    db.session.flush()

    # Trust-core wiring: attendance changes Commitment → cumulative % →
    # cert gate. Fire the standard rollup + recompute + issue chain.
    from utils.quizzes import _current_term_id
    term_id = _current_term_id()
    for sid in touched_student_ids:
        student = db.session.get(User, sid)
        if student is None:
            continue
        roll_up_to_commitment(student, term_id)
        enrollments = (
            Enrollment.query.filter_by(student_id=student.id)
            .filter(Enrollment.status.in_(("active", "completed")))
            .all()
        )
        for e in enrollments:
            recompute_enrollment_cache(e, term_id=term_id)
            maybe_issue_certificate(e)

    # Phase 21 — bell notifications for notable marks. Ping the student
    # and every linked parent. Same-day idempotency handled by enqueue.
    if notable_marks:
        from utils.notifications import enqueue
        parent_links = (
            ParentStudentLink.query
            .filter(ParentStudentLink.student_id.in_(
                {sid for sid, _ in notable_marks}
            ))
            .all()
        )
        parents_by_student: dict[str, list[str]] = {}
        for link in parent_links:
            parents_by_student.setdefault(link.student_id, []).append(link.parent_id)
        date_label = target_date.strftime("%d %b %Y")
        # Phase 25 hard-audit fix H-5: ref_id includes the date so
        # `enqueue`'s 24h dedup key `(user_id, kind, ref_type, ref_id)`
        # doesn't collapse Monday's + Tuesday's absent-marks into one
        # notification. Without this, day N+1 was silently swallowed.
        ref_date = target_date.isoformat()
        for sid, status in notable_marks:
            title = f"Marked {status} today" if target_date == _date.today() \
                    else f"Marked {status} on {date_label}"
            enqueue(sid, kind="attendance_marked", title=title,
                    body="", ref_type="attendance", ref_id=ref_date)
            for pid in parents_by_student.get(sid, []):
                stu = db.session.get(User, sid)
                enqueue(pid, kind="attendance_marked",
                        title=f"{stu.name if stu else 'Your child'} was {status}",
                        body=date_label,
                        ref_type="attendance", ref_id=ref_date)

    db.session.commit()
    return jsonify({
        "classId": sc.id,
        "date": target_date.isoformat(),
        "marksWritten": len(touched_student_ids),
    }), 200


# ---------------------------------------------------------------------------
# GET a student's attendance history (used by admin, teacher, self)
# ---------------------------------------------------------------------------
@attendance_bp.route("/users/<string:student_id>/attendance", methods=["GET"])
@login_required
def get_student_attendance(student_id: str):
    student = db.session.get(User, student_id)
    if student is None or student.role != "student":
        return jsonify({"error": "Student not found."}), 404
    user = current_user()
    if not can_view_student_records(user, student):
        return jsonify({"error": "You do not have permission."}), 403

    q = AttendanceMark.query.filter_by(student_id=student.id)
    frm = (request.args.get("from") or "").strip()
    to = (request.args.get("to") or "").strip()
    try:
        if frm:
            q = q.filter(AttendanceMark.date >= _parse_iso_date(frm))
        if to:
            q = q.filter(AttendanceMark.date <= _parse_iso_date(to))
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400

    q = q.order_by(AttendanceMark.date.desc())
    # Attendance is the one history in the app that grows with *time* rather
    # than with roster size: one row per school day, so ~180 a year and a few
    # thousand across a K-12 career. `from`/`to` are optional, so an
    # unfiltered call returns the lot.
    #
    # Back-compat: no `page`/`pageSize` still returns the bare array the
    # Flutter calendar expects. Passing either returns the standard
    # `{items, page, pageSize, hasMore}` envelope.
    if request.args.get("page") or request.args.get("pageSize"):
        return jsonify(
            paginate(q, render_item=lambda r: r.to_dict(), max_page_size=200)
        ), 200
    rows = q.all()
    return jsonify([r.to_dict() for r in rows]), 200


# ---------------------------------------------------------------------------
# GET own attendance — student convenience shortcut
# ---------------------------------------------------------------------------
@attendance_bp.route("/attendance/mine", methods=["GET"])
@login_required
def get_my_attendance():
    user = current_user()
    if not is_student(user):
        return jsonify({"error": "Students only."}), 403
    q = AttendanceMark.query.filter_by(student_id=user.id)
    frm = (request.args.get("from") or "").strip()
    to = (request.args.get("to") or "").strip()
    try:
        if frm:
            q = q.filter(AttendanceMark.date >= _parse_iso_date(frm))
        if to:
            q = q.filter(AttendanceMark.date <= _parse_iso_date(to))
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400
    q = q.order_by(AttendanceMark.date.desc())
    # Attendance is the one history in the app that grows with *time* rather
    # than with roster size: one row per school day, so ~180 a year and a few
    # thousand across a K-12 career. `from`/`to` are optional, so an
    # unfiltered call returns the lot.
    #
    # Back-compat: no `page`/`pageSize` still returns the bare array the
    # Flutter calendar expects. Passing either returns the standard
    # `{items, page, pageSize, hasMore}` envelope.
    if request.args.get("page") or request.args.get("pageSize"):
        return jsonify(
            paginate(q, render_item=lambda r: r.to_dict(), max_page_size=200)
        ), 200
    rows = q.all()
    return jsonify([r.to_dict() for r in rows]), 200
