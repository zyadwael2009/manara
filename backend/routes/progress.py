"""Progress tracking — mark complete, video-position beat, resume pointer.

All writes are student-owned: only the enrolled student can mark their own
lesson complete. Teachers/parents/admin CANNOT backfill progress.
"""
from __future__ import annotations

from datetime import datetime

from flask import Blueprint, jsonify, request

from models import (
    Enrollment,
    Lesson,
    LessonProgress,
    Module,
    User,
    db,
)
from routes.auth import current_user, login_required
from utils.certificates import maybe_issue_certificate
from utils.grading import recompute_progress_percent
from utils.permissions import (
    can_view_student_records,
    has_active_enrollment,
    is_admin,
    is_student,
)
from utils.validation import (
    ValidationError,
    as_int,
    require_json,
)
from utils.time import utc_now

progress_bp = Blueprint("progress", __name__)


def _get_enrollment_for_lesson(user: User, lesson: Lesson) -> Enrollment | None:
    """Return the caller's active enrollment for the lesson's course, or None."""
    course_id = lesson.module.course_id
    return (
        Enrollment.query.filter_by(student_id=user.id, course_id=course_id)
        .filter(Enrollment.status.in_(("active", "completed")))
        .first()
    )


def _upsert_progress(
    enrollment: Enrollment, lesson: Lesson, *, completed: bool | None = None,
    last_position_seconds: int | None = None,
) -> LessonProgress:
    row = LessonProgress.query.filter_by(
        enrollment_id=enrollment.id, lesson_id=lesson.id
    ).first()
    now = utc_now()
    if row is None:
        row = LessonProgress(
            enrollment_id=enrollment.id,
            lesson_id=lesson.id,
            completed=False,
            last_position_seconds=0,
        )
        db.session.add(row)
    row.last_visited_at = now
    if last_position_seconds is not None and last_position_seconds >= 0:
        # Only advance; never regress.
        if last_position_seconds > (row.last_position_seconds or 0):
            row.last_position_seconds = last_position_seconds
    if completed is True and not row.completed:
        row.completed = True
        row.completed_at = now
    return row


@progress_bp.route("/lessons/<string:lesson_id>/complete", methods=["POST"])
@login_required
def mark_complete(lesson_id: str):
    """Student explicitly marks a lesson complete."""
    lesson = db.session.get(Lesson, lesson_id)
    if lesson is None:
        return jsonify({"error": "Lesson not found."}), 404
    user = current_user()
    if not is_student(user):
        return jsonify({"error": "Only enrolled students can mark lessons complete."}), 403
    enrollment = _get_enrollment_for_lesson(user, lesson)
    if enrollment is None:
        return jsonify({"error": "You are not enrolled in this course."}), 403

    row = _upsert_progress(enrollment, lesson, completed=True)
    recompute_progress_percent(enrollment)
    maybe_issue_certificate(enrollment)
    db.session.commit()
    return jsonify(row.to_dict()), 200


@progress_bp.route("/lessons/<string:lesson_id>/progress", methods=["POST"])
@login_required
def record_progress(lesson_id: str):
    """Beat endpoint — student sends `{ lastPositionSeconds, viewed? }`.

    Auto-marks complete if:
      * `viewed` is truthy (text scrolled to bottom / PDF last-page reached), OR
      * `lastPositionSeconds >= 0.8 * duration_minutes * 60` (video 80%).
    """
    lesson = db.session.get(Lesson, lesson_id)
    if lesson is None:
        return jsonify({"error": "Lesson not found."}), 404
    user = current_user()
    if not is_student(user):
        return jsonify({"error": "Only enrolled students can record progress."}), 403
    enrollment = _get_enrollment_for_lesson(user, lesson)
    if enrollment is None:
        return jsonify({"error": "You are not enrolled in this course."}), 403

    try:
        payload = require_json(request.get_json(silent=True))
        last_pos = as_int(payload.get("lastPositionSeconds"), "lastPositionSeconds", default=0)
        viewed = bool(payload.get("viewed", False))
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400

    # Phase 33 fix #15 — clamp `last_pos` so a client can't POST a
    # bogus huge value (e.g. 999999999) to sail past the 80% gate on
    # a video whose true duration is 5 minutes. Upper bound is the
    # lesson's own duration plus one-minute slack; hard-cap at 24h
    # even without a stored duration.
    HARD_CAP = 86400  # 24h in seconds
    last_pos = max(0, min(last_pos, HARD_CAP))
    if lesson.type == "video" and lesson.duration_minutes:
        last_pos = min(last_pos, lesson.duration_minutes * 60 + 60)

    auto_complete = False
    if viewed:
        auto_complete = True
    elif lesson.type == "video" and lesson.duration_minutes:
        threshold = int(0.8 * lesson.duration_minutes * 60)
        if last_pos >= threshold:
            auto_complete = True

    row = _upsert_progress(
        enrollment, lesson,
        completed=True if auto_complete else None,
        last_position_seconds=last_pos,
    )
    if auto_complete:
        recompute_progress_percent(enrollment)
        maybe_issue_certificate(enrollment)
    db.session.commit()
    return jsonify(row.to_dict()), 200


@progress_bp.route("/enrollments/<string:enrollment_id>/progress", methods=["GET"])
@login_required
def get_enrollment_progress(enrollment_id: str):
    """Lesson-by-lesson state for one enrollment, plus a next-incomplete
    pointer. Auth: student themself, course teacher, admin, homeroom
    teacher, (later) parent — via can_view_student_records.
    """
    e = db.session.get(Enrollment, enrollment_id)
    if e is None:
        return jsonify({"error": "Enrollment not found."}), 404
    user = current_user()
    if not can_view_student_records(user, e.student):
        return jsonify({"error": "You do not have permission."}), 403

    # All lessons of the course, ordered.
    course = e.course
    lessons: list[Lesson] = []
    if course is not None:
        for m in course.modules.order_by(Module.order_index):
            for l in m.lessons.order_by(Lesson.order_index):
                lessons.append(l)

    rows = {
        p.lesson_id: p for p in LessonProgress.query.filter_by(enrollment_id=e.id).all()
    }
    next_incomplete = None
    lesson_progress = []
    for l in lessons:
        p = rows.get(l.id)
        d = {
            "lessonId": l.id,
            "title": l.title,
            "type": l.type,
            "moduleId": l.module_id,
            "completed": bool(p and p.completed),
            "lastPositionSeconds": (p.last_position_seconds if p else 0),
        }
        lesson_progress.append(d)
        if next_incomplete is None and not d["completed"]:
            next_incomplete = l.id
    return (
        jsonify(
            {
                "enrollmentId": e.id,
                "progressPercent": e.progress_percent,
                "nextLessonId": next_incomplete,
                "lessons": lesson_progress,
            }
        ),
        200,
    )


@progress_bp.route("/enrollments/mine/continue", methods=["GET"])
@login_required
def continue_where_left_off():
    """Return the most-recently-touched incomplete lesson for the current
    student — powers the 'Continue' band on My Classes."""
    user = current_user()
    if not is_student(user):
        return jsonify(None), 200
    # Find the most recent LessonProgress row that is NOT completed OR the
    # most recent active enrollment if the student has never touched a lesson.
    latest_touched = (
        LessonProgress.query.join(Enrollment, Enrollment.id == LessonProgress.enrollment_id)
        .filter(Enrollment.student_id == user.id)
        .filter(LessonProgress.completed.is_(False))
        .order_by(LessonProgress.last_visited_at.desc().nullslast())
        .first()
    )
    if latest_touched is not None:
        lesson = db.session.get(Lesson, latest_touched.lesson_id)
        enrollment = db.session.get(Enrollment, latest_touched.enrollment_id)
        # Phase 9 audit fix F8: if the touched lesson was deleted (LessonProgress
        # has no FK cascade), don't emit a pointer with `lessonId: null` — the
        # Flutter model non-null-casts it and crashes the Home "Continue" band.
        # Fall through to the "first-lesson-of-any-active-enrollment" fallback.
        if lesson is not None and enrollment is not None:
            return (
                jsonify(
                    {
                        "enrollmentId": enrollment.id,
                        "courseId": enrollment.course_id,
                        "courseTitle": enrollment.course.title if enrollment.course else None,
                        "moduleId": lesson.module_id,
                        "moduleTitle": lesson.module.title if lesson.module else None,
                        "lessonId": lesson.id,
                        "lessonTitle": lesson.title,
                        "lastPositionSeconds": latest_touched.last_position_seconds,
                    }
                ),
                200,
            )
    # Fallback: any active enrollment with at least one lesson.
    for e in Enrollment.query.filter_by(student_id=user.id, status="active").all():
        if e.course and e.course.modules.count() > 0:
            first_module = e.course.modules.order_by(Module.order_index).first()
            first_lesson = first_module.lessons.order_by(Lesson.order_index).first() if first_module else None
            if first_lesson is not None:
                return (
                    jsonify(
                        {
                            "enrollmentId": e.id,
                            "courseId": e.course_id,
                            "courseTitle": e.course.title,
                            "moduleId": first_module.id,
                            "moduleTitle": first_module.title,
                            "lessonId": first_lesson.id,
                            "lessonTitle": first_lesson.title,
                            "lastPositionSeconds": 0,
                        }
                    ),
                    200,
                )
    return jsonify(None), 200
