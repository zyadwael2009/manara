"""Grade entry (gradebook write) + report card reads.

Trust-core: only the course teacher of the student's class (or admin, or
dept leader) can WRITE. Locked terms refuse teacher edits.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from flask import Blueprint, jsonify, request

from models import (
    ClassCourseTeacher,
    Course,
    CourseRubric,
    Enrollment,
    GradeCategory,
    GradeEntry,
    GradeEntryHistory,
    SchoolClass,
    SchoolYear,
    Term,
    User,
    db,
)
from routes.auth import current_user, login_required
from utils.certificates import maybe_issue_certificate
from utils.grading import recompute_enrollment_cache, student_report_card
from utils.permissions import (
    can_enter_grades_for,
    can_view_report_card,
    is_admin,
)
from utils.validation import (
    ValidationError,
    as_str,
    require_fields,
    require_json,
)
from utils.time import utc_now

grade_reports_bp = Blueprint("grade_reports", __name__)


# ---------------------------------------------------------------------------
# Gradebook — teacher's grid for a class × course × term
# ---------------------------------------------------------------------------
@grade_reports_bp.route("/classes/<string:class_id>/gradebook", methods=["GET"])
@login_required
def get_gradebook(class_id: str):
    """Grid: students × categories with their scores.

    Query: courseId (required), termId (required).
    Auth: admin, or the course teacher of this class-course, or the class's
    homeroom teacher (read-only).
    """
    sc = db.session.get(SchoolClass, class_id)
    if sc is None:
        return jsonify({"error": "Class not found."}), 404

    course_id = (request.args.get("courseId") or "").strip()
    term_id = (request.args.get("termId") or "").strip()
    if not course_id or not term_id:
        return jsonify({"error": "courseId and termId are required."}), 400

    course = db.session.get(Course, course_id)
    if course is None:
        return jsonify({"error": "Course not found."}), 400
    term = db.session.get(Term, term_id)
    if term is None:
        return jsonify({"error": "Term not found."}), 400

    user = current_user()
    is_class_course_teacher = (
        ClassCourseTeacher.query.filter_by(
            course_id=course.id, class_id=sc.id, teacher_id=user.id
        ).first()
        is not None
    )
    is_homeroom = sc.homeroom_teacher_id == user.id
    if not (is_admin(user) or is_class_course_teacher or is_homeroom):
        return jsonify({"error": "You do not have permission."}), 403

    # Fetch rubric + all enrollments for this course from students currently
    # in this class.
    rubric = (
        CourseRubric.query.filter_by(course_id=course.id)
        .order_by(CourseRubric.order_index.asc())
        .all()
    )
    student_ids = {u.id for u in sc.students}
    enrollments = (
        Enrollment.query.filter_by(course_id=course.id)
        .filter(Enrollment.student_id.in_(student_ids))
        .filter(Enrollment.status.in_(("active", "completed")))
        .all()
    )
    # Per-enrollment entries.
    entries_by_enroll = {}
    for e in enrollments:
        entries_by_enroll[e.id] = {
            en.grade_category_id: float(en.score)
            for en in GradeEntry.query.filter_by(enrollment_id=e.id, term_id=term.id).all()
        }

    rows = []
    for e in enrollments:
        s = e.student
        rows.append(
            {
                "enrollmentId": e.id,
                "studentId": s.id,
                "studentName": s.name,
                "entries": entries_by_enroll.get(e.id, {}),
                "cachedPercent": float(e.cached_percent) if e.cached_percent is not None else None,
                "cachedLetter": e.cached_letter,
                "cachedGpa": float(e.cached_gpa) if e.cached_gpa is not None else None,
            }
        )
    return (
        jsonify(
            {
                "classId": sc.id,
                "className": sc.name,
                "courseId": course.id,
                "courseTitle": course.title,
                "termId": term.id,
                "termName": term.name,
                "termIsLocked": term.is_locked,
                "rubric": [r.to_dict() for r in rubric],
                "students": rows,
                "canWrite": is_admin(user) or is_class_course_teacher,
            }
        ),
        200,
    )


# ---------------------------------------------------------------------------
# Batch grade entry — write scores for one student
# ---------------------------------------------------------------------------
@grade_reports_bp.route("/enrollments/<string:enrollment_id>/grades", methods=["PUT"])
@login_required
def put_grades(enrollment_id: str):
    """Body: { termId, entries: [{gradeCategoryId, score}, ...] }.

    For each entry: create-or-update. Writes a `grade_entry_history` row on
    every score change. Refuses if the term is locked and caller is not admin.
    Recomputes the enrollment's cache at the end.
    """
    enrollment = db.session.get(Enrollment, enrollment_id)
    if enrollment is None:
        return jsonify({"error": "Enrollment not found."}), 404

    student = enrollment.student
    course = enrollment.course
    user = current_user()
    if not can_enter_grades_for(user, student, course):
        return jsonify({"error": "You do not have permission."}), 403

    try:
        payload = require_json(request.get_json(silent=True))
        require_fields(payload, ("termId", "entries"))
        term_id = as_str(payload["termId"], "termId")
        entries = payload["entries"]
        if not isinstance(entries, list):
            raise ValidationError("`entries` must be an array.")
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400

    term = db.session.get(Term, term_id)
    if term is None:
        return jsonify({"error": "Term not found."}), 400
    if term.is_locked and not is_admin(user):
        return (
            jsonify(
                {
                    "error": "This term is locked. Ask an admin to unlock it before editing grades."
                }
            ),
            403,
        )

    # Rubric map for validation.
    rubric_max = {
        r.grade_category_id: int(r.max_score)
        for r in CourseRubric.query.filter_by(course_id=course.id).all()
    }
    if not rubric_max:
        return (
            jsonify({"error": "This course has no rubric yet. Admin must set one first."}),
            400,
        )

    written = []
    for it in entries:
        if not isinstance(it, dict):
            return jsonify({"error": "Each entry must be an object."}), 400
        cat_id = it.get("gradeCategoryId")
        if not cat_id or cat_id not in rubric_max:
            return (
                jsonify({"error": f"gradeCategoryId '{cat_id}' is not in this course's rubric."}),
                400,
            )
        try:
            score = float(it.get("score"))
        except (TypeError, ValueError):
            return jsonify({"error": "Each entry needs a numeric score."}), 400
        if score < 0 or score > rubric_max[cat_id]:
            return (
                jsonify(
                    {
                        "error": f"Score {score} out of range for this category (0-{rubric_max[cat_id]})."
                    }
                ),
                400,
            )
        reason = as_str(it.get("reason") or "", "reason", max_len=500) if it.get("reason") else None

        existing = GradeEntry.query.filter_by(
            enrollment_id=enrollment.id,
            grade_category_id=cat_id,
            term_id=term.id,
        ).first()
        if existing is None:
            new_entry = GradeEntry(
                enrollment_id=enrollment.id,
                grade_category_id=cat_id,
                term_id=term.id,
                score=Decimal(str(score)),
                entered_by_id=user.id,
            )
            db.session.add(new_entry)
            db.session.flush()  # populates .id for the history row
            db.session.add(
                GradeEntryHistory(
                    grade_entry_id=new_entry.id,
                    old_score=None,
                    new_score=Decimal(str(score)),
                    reason=reason,
                    changed_by_id=user.id,
                )
            )
            written.append(new_entry)
        else:
            old = existing.score
            existing.score = Decimal(str(score))
            existing.entered_by_id = user.id
            existing.updated_at = utc_now()
            db.session.add(
                GradeEntryHistory(
                    grade_entry_id=existing.id,
                    old_score=old,
                    new_score=Decimal(str(score)),
                    reason=reason,
                    changed_by_id=user.id,
                )
            )
            written.append(existing)

    # Recompute cache scoped to this term (since we just wrote to it).
    recompute_enrollment_cache(enrollment, term_id=term.id)
    # Grade write can open the certificate gate.
    maybe_issue_certificate(enrollment)
    db.session.commit()
    return jsonify({"written": [w.to_dict() for w in written]}), 200


# ---------------------------------------------------------------------------
# Report card reads
# ---------------------------------------------------------------------------
def _resolve_term_id(request_args) -> str | None:
    """If `termId` is given, return it; else return the current-year's first
    term id (best default for a report card view)."""
    term_id = (request_args.get("termId") or "").strip() or None
    if term_id:
        return term_id
    year = SchoolYear.query.filter_by(is_current=True).first()
    if year is None:
        return None
    t = Term.query.filter_by(school_year_id=year.id).order_by(Term.order_index.asc()).first()
    return t.id if t else None


@grade_reports_bp.route("/reports/mine", methods=["GET"])
@login_required
def my_report_card():
    user = current_user()
    term_id = _resolve_term_id(request.args)
    data = student_report_card(user.id, term_id=term_id)
    return jsonify(data), 200


@grade_reports_bp.route("/reports/students/<string:student_id>", methods=["GET"])
@login_required
def student_report_card_view(student_id: str):
    student = db.session.get(User, student_id)
    if student is None or student.role != "student":
        return jsonify({"error": "Student not found."}), 404
    user = current_user()
    if not can_view_report_card(user, student):
        return jsonify({"error": "You do not have permission."}), 403
    term_id = _resolve_term_id(request.args)
    data = student_report_card(student.id, term_id=term_id)
    return jsonify(data), 200
