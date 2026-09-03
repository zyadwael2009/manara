"""Phase 24 — cross-cutting content search.

`GET /api/search?q=…&scope=…` — SQLite LIKE over course titles / module
titles / lesson titles / assignment titles / quiz titles. Student results
scope naturally: students only see courses they're enrolled in; teachers
see courses they teach; admin sees everything. Optional `scope=` param
filters to a single kind (`course` / `lesson` / `assignment` / `quiz` /
`student` — the last admin-only).

No FTS index — the query is bounded by user's own visibility scope, so
size is small.
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from models import (
    Assignment,
    ClassCourseTeacher,
    Course,
    Enrollment,
    Lesson,
    Module,
    Quiz,
    User,
    db,
)
from routes.auth import current_user, login_required
from utils.permissions import (
    is_admin,
    is_instructor,
    is_parent,
    is_student,
)

search_bp = Blueprint("search", __name__)


def _visible_course_ids(user: User) -> set[str]:
    if is_admin(user):
        return {c.id for c in Course.query.with_entities(Course.id).all()}
    if is_student(user):
        return {
            e.course_id for e in Enrollment.query.filter_by(student_id=user.id)
            .filter(Enrollment.status.in_(("active", "completed")))
            .all()
        }
    if is_instructor(user):
        return {
            cct.course_id
            for cct in ClassCourseTeacher.query.filter_by(teacher_id=user.id).all()
        }
    if is_parent(user):
        from models import ParentStudentLink
        child_ids = [
            l.student_id for l in ParentStudentLink.query.filter_by(parent_id=user.id).all()
        ]
        if not child_ids:
            return set()
        return {
            e.course_id for e in Enrollment.query.filter(Enrollment.student_id.in_(child_ids))
            .filter(Enrollment.status.in_(("active", "completed")))
            .all()
        }
    return set()


@search_bp.route("/search", methods=["GET"])
@login_required
def search():
    user = current_user()
    q_raw = (request.args.get("q") or "").strip()
    scope = (request.args.get("scope") or "all").strip().lower()
    if len(q_raw) < 2:
        return jsonify({
            "query": q_raw, "results": [], "message": "Type at least 2 characters.",
        }), 200
    # Phase 25 hard-audit fix H-11: escape LIKE metacharacters so
    # `?q=%` no longer means "match everything" (turning the 2-char
    # throttle into a full-scope enumeration bypass — worst-case an
    # admin `?q=%&scope=student` dumped every student name+email).
    _q_escaped = (
        q_raw.replace("\\", "\\\\")
             .replace("%", "\\%")
             .replace("_", "\\_")
    )
    pattern = f"%{_q_escaped}%"
    course_ids = _visible_course_ids(user)

    results: list[dict] = []

    def _in_scope(kind: str) -> bool:
        return scope == "all" or scope == kind

    if _in_scope("course") and course_ids:
        for c in (
            Course.query.filter(Course.id.in_(course_ids))
            .filter(Course.title.ilike(pattern, escape="\\"))
            .limit(20).all()
        ):
            results.append({
                "kind": "course", "id": c.id, "title": c.title,
                "subtitle": c.category, "courseId": c.id,
            })

    if _in_scope("lesson") and course_ids:
        rows = (
            db.session.query(Lesson, Module, Course)
            .join(Module, Module.id == Lesson.module_id)
            .join(Course, Course.id == Module.course_id)
            .filter(Course.id.in_(course_ids))
            .filter(Lesson.title.ilike(pattern, escape="\\"))
            .limit(20).all()
        )
        for lesson, module, course in rows:
            results.append({
                "kind": "lesson", "id": lesson.id, "title": lesson.title,
                "subtitle": f"{course.title} · {module.title}",
                "courseId": course.id, "lessonId": lesson.id,
            })

    if _in_scope("assignment") and course_ids:
        # Phase 25 hard-audit fix H-2: draft assignments (unpublished)
        # must not surface titles to students. Owners edit inside the
        # course editor, not via global search. Admin + course-teachers
        # bypass the filter so they can find their own drafts.
        q = (
            db.session.query(Assignment, Module, Course)
            .join(Module, Module.id == Assignment.module_id)
            .join(Course, Course.id == Module.course_id)
            .filter(Course.id.in_(course_ids))
            .filter(Assignment.title.ilike(pattern, escape="\\"))
        )
        if not (is_admin(user) or is_instructor(user)):
            q = q.filter(Assignment.is_published.is_(True))
        rows = q.limit(20).all()
        for a, module, course in rows:
            results.append({
                "kind": "assignment", "id": a.id, "title": a.title,
                "subtitle": f"{course.title} · {module.title}",
                "courseId": course.id, "assignmentId": a.id,
            })

    if _in_scope("quiz") and course_ids:
        # Same rule as assignments — draft quizzes don't leak.
        q = (
            db.session.query(Quiz, Module, Course)
            .join(Module, Module.id == Quiz.module_id)
            .join(Course, Course.id == Module.course_id)
            .filter(Course.id.in_(course_ids))
            .filter(Quiz.title.ilike(pattern, escape="\\"))
        )
        if not (is_admin(user) or is_instructor(user)):
            q = q.filter(Quiz.is_published.is_(True))
        rows = q.limit(20).all()
        for q, module, course in rows:
            results.append({
                "kind": "quiz", "id": q.id, "title": q.title,
                "subtitle": f"{course.title} · {module.title}",
                "courseId": course.id, "quizId": q.id,
            })

    # Admin-only student search.
    if is_admin(user) and _in_scope("student"):
        for u in (
            User.query.filter_by(role="student")
            .filter(db.or_(
                User.name.ilike(pattern, escape="\\"),
                User.email.ilike(pattern, escape="\\"),
            ))
            .limit(20).all()
        ):
            results.append({
                "kind": "student", "id": u.id, "title": u.name,
                "subtitle": u.email, "studentId": u.id,
            })

    return jsonify({"query": q_raw, "results": results}), 200
