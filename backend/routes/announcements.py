"""Phase 19 — school / class / course announcements.

Author flow (POST /api/announcements):
  * Admin can post any audience.
  * Homeroom teacher can post audience="class" only for a class they homeroom.
  * Course teacher can post audience="course" only for a (class, course)
    pair they teach via ClassCourseTeacher.
  * Everyone else → 403.

Reader flow (GET /api/announcements/mine):
  * Student sees: school-wide + class-wide for their class + course-wide for
    every course they're actively enrolled in.
  * Parent sees: school-wide + everything relevant to any linked child.
  * Teacher / admin see: their own authored announcements (so they can
    manage them).

Delete: author OR admin.

Trust-core: an entirely new table + endpoints. No writes to enrollments,
grades, or certificates. Reads never leak beyond the caller's own audience
scope.
"""
from __future__ import annotations

from datetime import datetime

from flask import Blueprint, jsonify, request

from models import (
    ANNOUNCEMENT_AUDIENCES,
    Announcement,
    ClassCourseTeacher,
    Course,
    Enrollment,
    ParentStudentLink,
    SchoolClass,
    User,
    db,
)
from routes.auth import current_user, login_required
from utils.permissions import (
    homerooms_class,
    is_admin,
    is_parent,
    is_student,
)
from utils.validation import (
    ValidationError,
    as_str,
    require_fields,
    require_json,
)
from utils.time import utc_now

announcements_bp = Blueprint("announcements", __name__)


# ---------------------------------------------------------------------------
# Author guards
# ---------------------------------------------------------------------------
def _can_author(user: User, audience: str, class_id: str | None, course_id: str | None) -> bool:
    """Deliberately explicit — see the module docstring."""
    if user is None:
        return False
    if is_admin(user):
        return True
    if audience == "school":
        return False  # only admin
    if audience == "class":
        if class_id is None:
            return False
        sc = db.session.get(SchoolClass, class_id)
        return sc is not None and homerooms_class(user, sc)
    if audience == "course":
        if course_id is None:
            return False
        # A course teacher for any class → yes. If class_id is given, they
        # must teach that (class, course) pair specifically.
        q = ClassCourseTeacher.query.filter_by(
            teacher_id=user.id, course_id=course_id,
        )
        if class_id is not None:
            q = q.filter_by(class_id=class_id)
        return q.first() is not None
    return False


# ---------------------------------------------------------------------------
# Writes
# ---------------------------------------------------------------------------
@announcements_bp.route("/announcements", methods=["POST"])
@login_required
def create_announcement():
    try:
        payload = require_json(request.get_json(silent=True))
        require_fields(payload, ("audience", "title"))
        audience = as_str(payload["audience"], "audience", max_len=20)
        if audience not in ANNOUNCEMENT_AUDIENCES:
            raise ValidationError(
                f"audience must be one of {ANNOUNCEMENT_AUDIENCES}"
            )
        title = as_str(payload["title"], "title", max_len=200)
        body = as_str(payload.get("body", ""), "body", max_len=5000) or ""
        class_id = payload.get("classId")
        course_id = payload.get("courseId")
        expires_at_raw = payload.get("expiresAt")
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400

    if not title.strip():
        return jsonify({"error": "title is required."}), 400

    # School-wide never carries class/course; enforce that.
    if audience == "school":
        class_id = None
        course_id = None
    if audience == "class" and not class_id:
        return jsonify({"error": "classId is required for class announcements."}), 400
    if audience == "course" and not course_id:
        return jsonify({"error": "courseId is required for course announcements."}), 400

    user = current_user()
    if not _can_author(user, audience, class_id, course_id):
        return jsonify({"error": "You do not have permission to post this."}), 403

    expires_at = None
    if expires_at_raw:
        try:
            expires_at = datetime.fromisoformat(
                str(expires_at_raw).replace("Z", "+00:00")
            ).replace(tzinfo=None)
        except (TypeError, ValueError):
            return jsonify({"error": "expiresAt must be ISO 8601."}), 400

    row = Announcement(
        audience=audience,
        class_id=class_id,
        course_id=course_id,
        author_id=user.id,
        title=title.strip(),
        body=body.strip(),
        expires_at=expires_at,
    )
    db.session.add(row)
    db.session.flush()

    # Phase 21 — fan-out to notification inbox for every recipient of
    # this audience. Same predicate logic as the reader.
    #
    # Phase 25 hard-audit fix H-9: one failed enqueue used to roll back
    # the whole announcement + every already-enqueued notification. At
    # school-wide fan-out (hundreds of recipients) that made the whole
    # feature availability-brittle. Now: the announcement row is
    # committed first (author's write succeeds no matter what), then
    # notifications are enqueued in a separate transaction with a
    # try/except that lets individual failures fall through.
    db.session.commit()

    from utils.notifications import enqueue
    for target_id in _recipient_ids(audience, class_id, course_id):
        try:
            enqueue(
                target_id,
                kind="announcement",
                title=row.title,
                body=row.body[:280],
                ref_type="announcement",
                ref_id=row.id,
            )
        except Exception:
            # Do NOT re-raise — one bad recipient shouldn't drop the
            # whole fan-out. `enqueue`'s own transaction is the
            # granularity; roll back this row so the next iteration
            # can try independently.
            db.session.rollback()
            continue
    db.session.commit()
    return jsonify(row.to_dict()), 201


def _recipient_ids(audience: str, class_id: str | None, course_id: str | None) -> set[str]:
    """Compute the set of user ids that should get a bell notification
    for this announcement. Includes students matching the audience AND
    any parents linked to those students. Excludes the author (handled
    in `enqueue` by the same-day dupe guard if they happen to also be
    a target — rare edge case)."""
    ids: set[str] = set()
    q = User.query.filter(User.is_active.is_(True))
    if audience == "school":
        students = q.filter_by(role="student").all()
    elif audience == "class":
        students = q.filter_by(role="student", class_id=class_id).all()
    elif audience == "course":
        # Students enrolled in this course, optionally scoped to a class.
        stud_ids = [
            e.student_id for e in Enrollment.query
            .filter_by(course_id=course_id)
            .filter(Enrollment.status.in_(("active", "completed")))
            .all()
        ]
        students = q.filter(User.id.in_(stud_ids)).all() if stud_ids else []
        if class_id is not None:
            students = [s for s in students if s.class_id == class_id]
    else:
        students = []
    for s in students:
        ids.add(s.id)
    if students:
        stud_ids = [s.id for s in students]
        for link in ParentStudentLink.query.filter(
            ParentStudentLink.student_id.in_(stud_ids)
        ).all():
            ids.add(link.parent_id)
    return ids


@announcements_bp.route("/announcements/<string:aid>", methods=["DELETE"])
@login_required
def delete_announcement(aid: str):
    row = db.session.get(Announcement, aid)
    if row is None:
        return jsonify({"error": "Announcement not found."}), 404
    user = current_user()
    if not (is_admin(user) or row.author_id == user.id):
        return jsonify({"error": "You do not have permission."}), 403
    db.session.delete(row)
    db.session.commit()
    return "", 204


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------
def _audience_query_for(user: User):
    """Return the base Announcement query filtered to what `user` should see.

    Non-expired only (expires_at is NULL or in the future).
    """
    now = utc_now()
    q = Announcement.query.filter(
        db.or_(Announcement.expires_at.is_(None), Announcement.expires_at > now)
    )

    if is_student(user):
        student_class_id = user.class_id
        course_ids = [
            e.course_id for e in Enrollment.query
            .filter_by(student_id=user.id)
            .filter(Enrollment.status.in_(("active", "completed")))
            .all()
        ]
        conds = [Announcement.audience == "school"]
        if student_class_id:
            conds.append(
                db.and_(
                    Announcement.audience == "class",
                    Announcement.class_id == student_class_id,
                )
            )
        if course_ids:
            conds.append(
                db.and_(
                    Announcement.audience == "course",
                    Announcement.course_id.in_(course_ids),
                    # Course-scoped to a specific class either matches the
                    # student's class or is null (all sections).
                    db.or_(
                        Announcement.class_id.is_(None),
                        Announcement.class_id == student_class_id,
                    ),
                )
            )
        return q.filter(db.or_(*conds))

    if is_parent(user):
        links = ParentStudentLink.query.filter_by(parent_id=user.id).all()
        child_ids = [l.student_id for l in links]
        children = User.query.filter(User.id.in_(child_ids)).all() if child_ids else []
        class_ids = {c.class_id for c in children if c.class_id}
        course_ids = set()
        for cid in child_ids:
            for e in (
                Enrollment.query.filter_by(student_id=cid)
                .filter(Enrollment.status.in_(("active", "completed")))
                .all()
            ):
                course_ids.add(e.course_id)
        conds = [Announcement.audience == "school"]
        if class_ids:
            conds.append(
                db.and_(
                    Announcement.audience == "class",
                    Announcement.class_id.in_(class_ids),
                )
            )
        if course_ids:
            conds.append(
                db.and_(
                    Announcement.audience == "course",
                    Announcement.course_id.in_(course_ids),
                )
            )
        return q.filter(db.or_(*conds))

    # Teacher / admin — show their own authored feed. (Admin sees school-wide
    # ones too since they authored those.)
    return q.filter(Announcement.author_id == user.id)


@announcements_bp.route("/announcements/mine", methods=["GET"])
@announcements_bp.route("/announcements/mine/", methods=["GET"])
@login_required
def my_announcements():
    """Announcements audience-scoped to the caller.

    Phase 29 · T3 — pagination. `?page=N&pageSize=M` (max 50). When no
    page is supplied the response is a plain array (back-compat); with
    `page`/`pageSize` it becomes `{items, page, pageSize, hasMore}`.
    Legacy `?limit=N` (max 200) still works and returns the paged
    envelope as a single page.
    """
    user = current_user()
    q = (
        _audience_query_for(user)
        .order_by(Announcement.created_at.desc())
    )
    from utils.pagination import paginate
    if request.args.get("limit"):
        try:
            legacy_limit = max(1, min(200, int(request.args["limit"])))
        except (TypeError, ValueError):
            legacy_limit = 50
        page = paginate(q, render_item=lambda r: r.to_dict(),
                        page=1, page_size=legacy_limit, max_page_size=200)
        return jsonify(page), 200
    if not request.args.get("page") and not request.args.get("pageSize"):
        rows = q.limit(50).all()
        return jsonify([r.to_dict() for r in rows]), 200
    page = paginate(q, render_item=lambda r: r.to_dict())
    return jsonify(page), 200
