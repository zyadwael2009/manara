"""Phase 14 — assignments + submissions + inline grading."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from flask import Blueprint, jsonify, request

from models import (
    Assignment,
    AssignmentGroup,
    AssignmentGroupMember,
    AssignmentSubmission,
    Course,
    Enrollment,
    Module,
    User,
    db,
)
from routes.auth import current_user, login_required
from utils.assignments import roll_up_assignment_category
from utils.certificates import maybe_issue_certificate
from utils.grading import recompute_enrollment_cache
from utils.permissions import (
    can_edit_course_content,
    can_enter_grades_for,
    can_view_content,
    classes_user_teaches_for_course,
    has_active_enrollment,
    is_admin,
    is_student,
    teaches_course_in_any_class,
)
from utils.validation import (
    ValidationError,
    as_int,
    as_str,
    require_fields,
    require_json,
)
from utils.time import utc_now

assignments_bp = Blueprint("assignments", __name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _submissions_exist(assignment_id: str) -> bool:
    return AssignmentSubmission.query.filter_by(
        assignment_id=assignment_id
    ).first() is not None


def _authorship_check(assignment: Assignment):
    """Return (jsonify, code) if caller can't edit. None if allowed."""
    user = current_user()
    course = assignment.module.course if assignment.module else None
    if course is None:
        return jsonify({"error": "Assignment has no course."}), 400
    if not can_edit_course_content(user, course):
        return jsonify({"error": "You do not have permission."}), 403
    return None


def _parse_due(raw) -> datetime | None:
    if raw is None or raw == "":
        return None
    if not isinstance(raw, str):
        raise ValidationError("dueAt must be a string.")
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).replace(tzinfo=None)
    except (TypeError, ValueError):
        raise ValidationError(f"'{raw}' is not a valid ISO 8601 datetime.") from None


# ---------------------------------------------------------------------------
# Create + edit + publish
# ---------------------------------------------------------------------------
@assignments_bp.route("/modules/<string:module_id>/assignments", methods=["POST"])
@login_required
def create_assignment(module_id: str):
    module = db.session.get(Module, module_id)
    if module is None:
        return jsonify({"error": "Module not found."}), 404
    user = current_user()
    if not can_edit_course_content(user, module.course):
        return jsonify({"error": "You do not have permission."}), 403
    try:
        payload = require_json(request.get_json(silent=True))
        require_fields(payload, ("title",))
        title = as_str(payload["title"], "title", max_len=200)
        description = as_str(payload.get("description") or "", "description", max_len=10_000)
        max_points = as_int(payload.get("maxPoints"), "maxPoints", default=100)
        allow_text = bool(payload.get("allowText", True))
        allow_file = bool(payload.get("allowFile", True))
        due_at = _parse_due(payload.get("dueAt"))
        # Phase 27 — optional group-mode + max-size cap.
        is_group = bool(payload.get("isGroup", False))
        max_group_size = payload.get("maxGroupSize")
        if max_group_size is not None:
            max_group_size = as_int(max_group_size, "maxGroupSize")
            if max_group_size < 2:
                raise ValidationError("maxGroupSize must be at least 2.")
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400
    if max_points <= 0:
        return jsonify({"error": "maxPoints must be positive."}), 400
    if not (allow_text or allow_file):
        return jsonify({"error": "At least one of allowText/allowFile must be true."}), 400

    a = Assignment(
        module_id=module.id,
        title=title,
        description=description,
        max_points=max_points,
        allow_text=allow_text,
        allow_file=allow_file,
        due_at=due_at,
        is_published=False,
        is_group=is_group,
        max_group_size=max_group_size if is_group else None,
        created_by_id=user.id,
    )
    db.session.add(a)
    db.session.commit()
    return jsonify(a.to_dict()), 201


@assignments_bp.route("/assignments/<string:aid>", methods=["PUT", "PATCH"])
@login_required
def update_assignment(aid: str):
    a = db.session.get(Assignment, aid)
    if a is None:
        return jsonify({"error": "Assignment not found."}), 404
    err = _authorship_check(a)
    if err:
        return err
    if _submissions_exist(a.id):
        return (
            jsonify({"error":
                "This assignment has student submissions. Duplicate it before restructuring."}),
            409,
        )
    try:
        payload = require_json(request.get_json(silent=True))
        if "title" in payload:
            a.title = as_str(payload["title"], "title", max_len=200)
        if "description" in payload:
            a.description = as_str(payload["description"], "description", max_len=10_000)
        if "maxPoints" in payload:
            mp = as_int(payload["maxPoints"], "maxPoints")
            if mp <= 0:
                return jsonify({"error": "maxPoints must be positive."}), 400
            a.max_points = mp
        if "allowText" in payload:
            a.allow_text = bool(payload["allowText"])
        if "allowFile" in payload:
            a.allow_file = bool(payload["allowFile"])
        if not (a.allow_text or a.allow_file):
            return jsonify({"error": "At least one of allowText/allowFile must be true."}), 400
        if "dueAt" in payload:
            a.due_at = _parse_due(payload.get("dueAt"))
        # Phase 27 — allow toggling group-mode + max-size while there
        # are no submissions (the _submissions_exist gate above already
        # blocked us if any exist, so we can freely flip these).
        if "isGroup" in payload:
            a.is_group = bool(payload["isGroup"])
            if not a.is_group:
                a.max_group_size = None
        if "maxGroupSize" in payload:
            mgs = payload.get("maxGroupSize")
            if mgs is None:
                a.max_group_size = None
            else:
                mgs = as_int(mgs, "maxGroupSize")
                if mgs < 2:
                    raise ValidationError("maxGroupSize must be at least 2.")
                a.max_group_size = mgs
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400
    db.session.commit()
    return jsonify(a.to_dict()), 200


@assignments_bp.route("/assignments/<string:aid>", methods=["DELETE"])
@login_required
def delete_assignment(aid: str):
    a = db.session.get(Assignment, aid)
    if a is None:
        return jsonify({"error": "Assignment not found."}), 404
    err = _authorship_check(a)
    if err:
        return err
    if _submissions_exist(a.id):
        return (
            jsonify({"error":
                "This assignment has student submissions. Un-publish it instead."}),
            409,
        )
    db.session.delete(a)
    db.session.commit()
    return jsonify({"message": "Assignment deleted."}), 200


@assignments_bp.route("/assignments/<string:aid>/publish", methods=["POST"])
@login_required
def publish_assignment(aid: str):
    a = db.session.get(Assignment, aid)
    if a is None:
        return jsonify({"error": "Assignment not found."}), 404
    err = _authorship_check(a)
    if err:
        return err
    a.is_published = True
    db.session.commit()
    return jsonify(a.to_dict()), 200


@assignments_bp.route("/assignments/<string:aid>/unpublish", methods=["POST"])
@login_required
def unpublish_assignment(aid: str):
    a = db.session.get(Assignment, aid)
    if a is None:
        return jsonify({"error": "Assignment not found."}), 404
    err = _authorship_check(a)
    if err:
        return err
    a.is_published = False
    # Unpublishing shifts the denominator of the Assignments rollup —
    # same shape as quiz-unpublish in Phase 9 F5. Re-run for every
    # enrollment so students who lose an assignment they hadn't done
    # don't stay stuck below the cert threshold.
    course = a.module.course if a.module else None
    if course is not None:
        from utils.quizzes import _current_term_id
        term_id = _current_term_id()
        for e in Enrollment.query.filter_by(course_id=course.id).filter(
            Enrollment.status.in_(("active", "completed"))
        ).all():
            roll_up_assignment_category(e, term_id=term_id)
            recompute_enrollment_cache(e, term_id=term_id)
            maybe_issue_certificate(e)
    db.session.commit()
    return jsonify(a.to_dict()), 200


# ---------------------------------------------------------------------------
# Reads — course-scoped list + single assignment
# ---------------------------------------------------------------------------
@assignments_bp.route("/courses/<string:course_id>/assignments", methods=["GET"])
@login_required
def list_course_assignments(course_id: str):
    course = db.session.get(Course, course_id)
    if course is None:
        return jsonify({"error": "Course not found."}), 404
    user = current_user()
    if not can_view_content(user, course):
        return jsonify({"error": "You do not have permission."}), 403

    show_drafts = is_admin(user) or teaches_course_in_any_class(user, course)
    q = Assignment.query.join(Module, Module.id == Assignment.module_id).filter(
        Module.course_id == course.id
    )
    if not show_drafts:
        q = q.filter(Assignment.is_published.is_(True))
    q = q.order_by(Assignment.due_at.asc().nullslast(), Assignment.created_at.asc())
    student_id = user.id if is_student(user) else None

    # Phase 33 fix #12 — batch-load the caller's submissions in one
    # query instead of a per-row lookup inside `to_dict`.
    def _sub_map(rows_):
        if student_id is None or not rows_:
            return {}
        ids = [a.id for a in rows_]
        return {
            s.assignment_id: s for s in AssignmentSubmission.query.filter(
                AssignmentSubmission.assignment_id.in_(ids),
                AssignmentSubmission.student_id == student_id,
            ).all()
        }

    # Phase 33 fix #18 — optional envelope pagination; bare array
    # shape preserved for legacy callers.
    if request.args.get("page") or request.args.get("pageSize"):
        try:
            page = max(1, int(request.args.get("page", 1)))
        except (TypeError, ValueError):
            page = 1
        try:
            page_size = max(1, min(50, int(request.args.get("pageSize", 20))))
        except (TypeError, ValueError):
            page_size = 20
        offset = (page - 1) * page_size
        page_rows = q.limit(page_size + 1).offset(offset).all()
        has_more = len(page_rows) > page_size
        if has_more:
            page_rows = page_rows[:page_size]
        smap = _sub_map(page_rows)
        return jsonify({
            "items": [
                a.to_dict(
                    include_my_submission_for=student_id,
                    submission_by_assignment=smap,
                ) for a in page_rows
            ],
            "page": page,
            "pageSize": page_size,
            "hasMore": has_more,
        }), 200

    rows = q.all()
    smap = _sub_map(rows)
    return jsonify([
        a.to_dict(
            include_my_submission_for=student_id,
            submission_by_assignment=smap,
        ) for a in rows
    ]), 200


@assignments_bp.route("/assignments/my", methods=["GET"])
@assignments_bp.route("/assignments/my/", methods=["GET"])
@login_required
def my_assignments_all():
    """Phase 18 — every published assignment across the caller's live
    enrollments, plus their own submission state for each.

    Sorted by due date (ascending, nulls last). Non-students → empty list.
    Read-only; scoped on the caller's own enrollments.
    """
    user = current_user()
    paged = bool(request.args.get("page") or request.args.get("pageSize"))

    def _empty():
        if paged:
            try:
                page = max(1, int(request.args.get("page", 1)))
            except (TypeError, ValueError):
                page = 1
            try:
                page_size = max(1, min(50, int(request.args.get("pageSize", 20))))
            except (TypeError, ValueError):
                page_size = 20
            return jsonify({
                "items": [], "page": page,
                "pageSize": page_size, "hasMore": False,
            }), 200
        return jsonify([]), 200

    if not is_student(user):
        return _empty()

    enrolls = (
        Enrollment.query.filter_by(student_id=user.id)
        .filter(Enrollment.status.in_(("active", "completed")))
        .all()
    )
    if not enrolls:
        return _empty()

    course_by_id = {e.course_id: e.course for e in enrolls if e.course is not None}
    modules_by_course: dict[str, list[Module]] = {}
    for m in Module.query.filter(Module.course_id.in_(course_by_id.keys())).all():
        modules_by_course.setdefault(m.course_id, []).append(m)
    module_ids = [m.id for lst in modules_by_course.values() for m in lst]
    module_by_id = {m.id: m for lst in modules_by_course.values() for m in lst}

    rows = (
        Assignment.query.filter(Assignment.module_id.in_(module_ids))
        .filter(Assignment.is_published.is_(True))
        .order_by(Assignment.due_at.asc().nullslast(), Assignment.created_at.asc())
        .all()
    ) if module_ids else []

    # Phase 33 fix #12 — batch-load the caller's submissions once, not
    # once per row. Old shape burned N SELECTs against
    # assignment_submissions for a page of N.
    submission_by_assignment = {}
    if rows:
        ids = [a.id for a in rows]
        submission_by_assignment = {
            s.assignment_id: s for s in AssignmentSubmission.query.filter(
                AssignmentSubmission.assignment_id.in_(ids),
                AssignmentSubmission.student_id == user.id,
            ).all()
        }

    out: list[dict] = []
    for a in rows:
        module = module_by_id.get(a.module_id)
        course = course_by_id.get(module.course_id) if module else None
        row = a.to_dict(
            include_my_submission_for=user.id,
            submission_by_assignment=submission_by_assignment,
        )
        row["moduleTitle"] = module.title if module else ""
        row["course"] = {
            "id": course.id if course else None,
            "title": course.title if course else "",
            "category": course.category if course else "general",
        }
        out.append(row)
    # Phase 30 · T5 — optional pagination over the composed list. Back-
    # compat: no `page` arg → the original bare-array shape. Server-
    # side slicing here (rather than in the ORM query) because the
    # payload is a compose of ORM row + module + course lookups.
    if request.args.get("page") or request.args.get("pageSize"):
        try:
            page = max(1, int(request.args.get("page", 1)))
        except (TypeError, ValueError):
            page = 1
        try:
            page_size = max(1, min(50, int(request.args.get("pageSize", 20))))
        except (TypeError, ValueError):
            page_size = 20
        start = (page - 1) * page_size
        items = out[start:start + page_size]
        return jsonify({
            "items": items,
            "page": page,
            "pageSize": page_size,
            "hasMore": len(out) > start + page_size,
        }), 200
    return jsonify(out), 200


@assignments_bp.route("/assignments/<string:aid>", methods=["GET"])
@login_required
def get_assignment(aid: str):
    a = db.session.get(Assignment, aid)
    if a is None:
        return jsonify({"error": "Assignment not found."}), 404
    user = current_user()
    course = a.module.course if a.module else None
    if course is None or not can_view_content(user, course):
        return jsonify({"error": "You do not have permission."}), 403
    if not a.is_published and not can_edit_course_content(user, course):
        return jsonify({"error": "Assignment not found."}), 404
    student_id = user.id if is_student(user) else None
    return jsonify(a.to_dict(include_my_submission_for=student_id)), 200


# ---------------------------------------------------------------------------
# Submissions
# ---------------------------------------------------------------------------
@assignments_bp.route("/assignments/<string:aid>/submissions", methods=["POST"])
@login_required
def submit_assignment(aid: str):
    a = db.session.get(Assignment, aid)
    if a is None:
        return jsonify({"error": "Assignment not found."}), 404
    if not a.is_published:
        return jsonify({"error": "Assignment is not published."}), 404
    user = current_user()
    course = a.module.course if a.module else None
    if course is None or not has_active_enrollment(user, course):
        return jsonify({"error": "You are not enrolled in this course."}), 403
    enrollment = Enrollment.query.filter_by(
        student_id=user.id, course_id=course.id,
    ).first()
    if enrollment is None:
        return jsonify({"error": "Enrollment not found."}), 400

    try:
        payload = require_json(request.get_json(silent=True))
        text_raw = payload.get("responseText")
        file_url_raw = payload.get("fileUrl")
        file_kind_raw = payload.get("fileKind")

        response_text = None
        if text_raw is not None:
            if not a.allow_text:
                raise ValidationError("This assignment does not accept text answers.")
            if not isinstance(text_raw, str):
                raise ValidationError("responseText must be a string.")
            if len(text_raw) > 20_000:
                raise ValidationError("responseText exceeds 20000 characters.")
            response_text = text_raw

        file_url = None
        file_kind = None
        if file_url_raw:
            if not a.allow_file:
                raise ValidationError("This assignment does not accept file uploads.")
            file_url = as_str(file_url_raw, "fileUrl", max_len=1000)
            if file_kind_raw:
                file_kind = as_str(file_kind_raw, "fileKind", max_len=20)
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400

    if not response_text and not file_url:
        return jsonify({"error": "Submission is empty."}), 400

    now = utc_now()
    is_late = bool(a.due_at and now > a.due_at)

    # Phase 27 — group-mode fan-out. If this is a group assignment, the
    # caller MUST be in a group for it (they can't submit solo); every
    # group-mate's submission is upserted with the same content so the
    # grader only marks one row and the fan-out in `grade_submission`
    # covers the rest.
    group_id: str | None = None
    group_members: list[User] = [user]
    if a.is_group:
        mem = (
            AssignmentGroupMember.query
            .join(AssignmentGroup, AssignmentGroup.id == AssignmentGroupMember.group_id)
            .filter(
                AssignmentGroupMember.student_id == user.id,
                AssignmentGroup.assignment_id == a.id,
            )
            .first()
        )
        if mem is None:
            return jsonify(
                {"error": "Join a group before submitting this assignment."},
            ), 409
        group_id = mem.group_id
        rows = AssignmentGroupMember.query.filter_by(group_id=group_id).all()
        group_members = [
            db.session.get(User, r.student_id) for r in rows
        ]
        group_members = [u for u in group_members if u is not None]

    caller_sub: AssignmentSubmission | None = None
    touched_enrollments: list[Enrollment] = []
    for member in group_members:
        # Every group-mate must be enrolled for the fan-out to land in
        # their gradebook; if one is not, skip them silently — the
        # course teacher will still see the missing gradebook row.
        m_enr = Enrollment.query.filter_by(
            student_id=member.id, course_id=course.id,
        ).first()
        if m_enr is None:
            continue
        sub = AssignmentSubmission.query.filter_by(
            assignment_id=a.id, student_id=member.id,
        ).first()
        if sub is None:
            sub = AssignmentSubmission(
                assignment_id=a.id,
                student_id=member.id,
                enrollment_id=m_enr.id,
                submitted_at=now,
                is_late=is_late,
                response_text=response_text,
                file_url=file_url,
                file_kind=file_kind,
                group_id=group_id,
            )
            db.session.add(sub)
        else:
            # Re-submit: clear any prior grade so the teacher re-scores.
            sub.submitted_at = now
            sub.is_late = is_late
            sub.response_text = response_text
            sub.file_url = file_url
            sub.file_kind = file_kind
            sub.group_id = group_id
            sub.graded_score = None
            sub.graded_max = None
            sub.graded_feedback = None
            sub.graded_by_id = None
            sub.graded_at = None
        touched_enrollments.append(m_enr)
        if member.id == user.id:
            caller_sub = sub
    db.session.commit()

    # Re-submit clears the grade → rollup drops → recompute + cert gate
    # for every touched enrollment (solo = just the caller, group = all).
    for enr in touched_enrollments:
        roll_up_assignment_category(enr)
        recompute_enrollment_cache(enr)
        maybe_issue_certificate(enr)
    if touched_enrollments:
        db.session.commit()

    return jsonify(caller_sub.to_dict() if caller_sub else {}), 201


@assignments_bp.route("/assignments/<string:aid>/submissions", methods=["GET"])
@login_required
def list_submissions(aid: str):
    a = db.session.get(Assignment, aid)
    if a is None:
        return jsonify({"error": "Assignment not found."}), 404
    user = current_user()
    course = a.module.course if a.module else None
    if course is None or not (is_admin(user) or teaches_course_in_any_class(user, course)):
        return jsonify({"error": "You do not have permission."}), 403

    rows = list(a.submissions.all())
    # Non-admin: restrict to the caller's-class students (same shape as
    # Phase 9 quiz-attempts F2 fix).
    if not is_admin(user):
        allowed = classes_user_teaches_for_course(user, course)
        rows = [
            s for s in rows
            if s.student is not None and s.student.class_id in allowed
        ]
    return jsonify([s.to_dict(include_student_name=True) for s in rows]), 200


@assignments_bp.route("/submissions/<string:sid>/grade", methods=["PUT"])
@login_required
def grade_submission(sid: str):
    sub = db.session.get(AssignmentSubmission, sid)
    if sub is None:
        return jsonify({"error": "Submission not found."}), 404
    user = current_user()
    student = sub.student
    a = db.session.get(Assignment, sub.assignment_id)
    course = a.module.course if (a and a.module) else None
    if student is None or course is None:
        return jsonify({"error": "Submission is orphaned."}), 400
    if not can_enter_grades_for(user, student, course):
        return jsonify({"error": "You do not have permission."}), 403

    try:
        payload = require_json(request.get_json(silent=True))
        require_fields(payload, ("score",))
        try:
            score = float(payload["score"])
        except (TypeError, ValueError):
            raise ValidationError("score must be a number.") from None
        feedback = payload.get("feedback")
        if feedback is not None:
            feedback = as_str(feedback, "feedback", max_len=5000) or None
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400

    if score < 0 or score > a.max_points:
        return jsonify({"error": f"score must be between 0 and {a.max_points}."}), 400

    now = utc_now()

    # Phase 27 — group-mode grade fan-out. If this submission belongs to
    # a group, apply the same score/feedback to EVERY group-mate's
    # submission and roll up each of their enrollments. Solo mode is
    # just the caller-submission by itself.
    if sub.group_id is not None:
        peers = AssignmentSubmission.query.filter_by(
            assignment_id=sub.assignment_id, group_id=sub.group_id,
        ).all()
    else:
        peers = [sub]

    from utils.notifications import enqueue
    for peer in peers:
        peer.graded_score = Decimal(str(score))
        peer.graded_max = Decimal(str(a.max_points))
        peer.graded_feedback = feedback
        peer.graded_by_id = user.id
        peer.graded_at = now
    db.session.flush()

    for peer in peers:
        enr = db.session.get(Enrollment, peer.enrollment_id)
        if enr is not None:
            roll_up_assignment_category(enr)
            recompute_enrollment_cache(enr)
            maybe_issue_certificate(enr)
        # Phase 21 — bell notification, once per group-mate.
        enqueue(
            peer.student_id,
            kind="assignment_graded",
            title=f"Grade posted: {a.title}",
            body=f"{score}/{a.max_points}" + (f" — {feedback}" if feedback else ""),
            ref_type="assignment",
            ref_id=a.id,
        )

    db.session.commit()
    return jsonify(sub.to_dict(include_student_name=True)), 200
