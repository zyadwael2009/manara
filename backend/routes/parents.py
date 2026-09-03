"""Phase 6 — Parent portal.

READ-ONLY endpoints scoped to the caller's linked children.

Every path on this blueprint is a GET. `@parents_bp.before_request`
refuses any other verb with 405, so even a mis-authored future route
here cannot accept a write. Every handler starts with
`_ensure_can_view_child` which 404s an unknown child and 403s a child
the caller isn't linked to — no cross-parent leakage.

None of this blueprint issues, grades, submits, or otherwise mutates
anything. Parent = read + content-view, per Global Rule #7.
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from datetime import date as _date

from models import (
    AttendanceMark,
    Certificate,
    Enrollment,
    ParentStudentLink,
    QuizAttempt,
    SchoolClass,
    User,
    db,
)
from routes.auth import current_user, login_required
from utils.permissions import is_linked_parent_of, is_parent

parents_bp = Blueprint("parents", __name__)


# ---------------------------------------------------------------------------
# Hard refuse any non-GET verb on this blueprint. Belt-and-suspenders on top
# of only mounting GET routes.
#
# OPTIONS must pass through so Flask-CORS can answer the browser's cross-
# origin preflight; the browser fires OPTIONS before any GET/POST from a
# different origin and needs a 2xx response with the right ACAO headers,
# else it fails the actual request as "Failed to fetch." Blocking OPTIONS
# here was the bug that broke the parent portal on Flutter web.
# ---------------------------------------------------------------------------
@parents_bp.before_request
def _forbid_non_get():
    if request.method not in ("GET", "OPTIONS", "HEAD"):
        return jsonify({"error": "This endpoint is read-only."}), 405
    return None


# ---------------------------------------------------------------------------
# Shared guard: caller must be the linked parent of `child_id`. Anything else
# returns 404 (unknown) or 403 (not yours) — never a hint that a child with
# that id exists but isn't yours.
# ---------------------------------------------------------------------------
def _resolve_child(child_id: str) -> tuple[User | None, tuple | None]:
    parent = current_user()
    if not is_parent(parent):
        return None, (jsonify({"error": "Parent role required."}), 403)
    child = db.session.get(User, child_id)
    # Phase 25 hard-audit fix H-3: withdrawn/graduated children stay
    # visible to their linked parent — Phase 23's whole promise is
    # historical rows (grades, certs, transcript PDF) survive. The
    # PDF endpoints already surface those; blocking JSON reads here
    # created a UI where the tile appeared in `list_my_children` and
    # then every drill-down 404'd. The parent-link IS the auth.
    if child is None or child.role != "student":
        return None, (jsonify({"error": "Child not found."}), 404)
    if not is_linked_parent_of(parent, child):
        return None, (jsonify({"error": "You are not linked to this child."}), 403)
    return child, None


# ---------------------------------------------------------------------------
# List linked children
# ---------------------------------------------------------------------------
@parents_bp.route("/parents/mine/children", methods=["GET"])
@login_required
def list_my_children():
    parent = current_user()
    if not is_parent(parent):
        return jsonify({"error": "Parent role required."}), 403
    rows = (
        db.session.query(ParentStudentLink, User)
        .join(User, User.id == ParentStudentLink.student_id)
        .filter(ParentStudentLink.parent_id == parent.id)
        .order_by(User.name.asc())
        .all()
    )
    today = _date.today()
    out = []
    for link, student in rows:
        sc = (
            db.session.get(SchoolClass, student.class_id)
            if student.class_id else None
        )
        # Phase 12: today's attendance status → parent home red-badge signal.
        today_mark = AttendanceMark.query.filter_by(
            student_id=student.id, date=today,
        ).first()
        out.append({
            "linkId": link.id,
            "studentId": student.id,
            "name": student.name,
            "email": student.email,
            "classId": student.class_id,
            "className": sc.name if sc else None,
            "gradeName": sc.grade.name if (sc and sc.grade) else None,
            "relationship": link.relationship_type,
            "linkCreatedAt": link.created_at.isoformat() + "Z" if link.created_at else None,
            "todayAttendanceStatus": today_mark.status if today_mark else None,
            # Phase 25 hard-audit fix H-10: badge withdrawn/graduated
            # children so the parent UI can render them muted rather
            # than pretending they're still enrolled.
            "isActive": student.is_active,
            "withdrawnAt": student.withdrawn_at.isoformat() + "Z"
                if student.withdrawn_at else None,
            "graduatedAt": student.graduated_at.isoformat() + "Z"
                if student.graduated_at else None,
        })
    return jsonify(out), 200


# ---------------------------------------------------------------------------
# One child summary: their class, enrollments (with grade + cert), cert count
# ---------------------------------------------------------------------------
@parents_bp.route("/parents/mine/children/<string:child_id>/summary", methods=["GET"])
@login_required
def child_summary(child_id: str):
    child, err = _resolve_child(child_id)
    if err is not None:
        return err

    enrollments = (
        Enrollment.query.filter_by(student_id=child.id)
        .filter(Enrollment.status.in_(("active", "completed")))
        .all()
    )
    active_certs = (
        Certificate.query.join(Enrollment, Enrollment.id == Certificate.enrollment_id)
        .filter(Enrollment.student_id == child.id, Certificate.revoked.is_(False))
        .count()
    )
    sc = db.session.get(SchoolClass, child.class_id) if child.class_id else None
    return jsonify({
        "student": {
            "id": child.id,
            "name": child.name,
            "email": child.email,
            "classId": child.class_id,
            "className": sc.name if sc else None,
            "gradeName": sc.grade.name if (sc and sc.grade) else None,
        },
        "enrollments": [e.to_dict(include_course=True) for e in enrollments],
        "activeCertificateCount": active_certs,
    }), 200


# ---------------------------------------------------------------------------
# Full enrollment list (rich shape)
# ---------------------------------------------------------------------------
@parents_bp.route("/parents/mine/children/<string:child_id>/enrollments", methods=["GET"])
@login_required
def child_enrollments(child_id: str):
    child, err = _resolve_child(child_id)
    if err is not None:
        return err
    rows = (
        Enrollment.query.filter_by(student_id=child.id)
        .filter(Enrollment.status.in_(("active", "completed")))
        .order_by(Enrollment.enrolled_at.desc())
        .all()
    )
    return jsonify([e.to_dict(include_course=True) for e in rows]), 200


# ---------------------------------------------------------------------------
# Quiz attempts (never with answer key)
# ---------------------------------------------------------------------------
@parents_bp.route("/parents/mine/children/<string:child_id>/quiz-attempts", methods=["GET"])
@login_required
def child_quiz_attempts(child_id: str):
    child, err = _resolve_child(child_id)
    if err is not None:
        return err
    rows = (
        QuizAttempt.query.filter_by(student_id=child.id)
        .order_by(QuizAttempt.started_at.desc())
        .all()
    )
    return jsonify([a.to_dict() for a in rows]), 200


# ---------------------------------------------------------------------------
# Certificates
# ---------------------------------------------------------------------------
@parents_bp.route("/parents/mine/children/<string:child_id>/attendance", methods=["GET"])
@login_required
def child_attendance(child_id: str):
    child, err = _resolve_child(child_id)
    if err is not None:
        return err
    rows = (
        AttendanceMark.query.filter_by(student_id=child.id)
        .order_by(AttendanceMark.date.desc())
        .all()
    )
    return jsonify([r.to_dict() for r in rows]), 200


@parents_bp.route("/parents/mine/children/<string:child_id>/certificates", methods=["GET"])
@login_required
def child_certificates(child_id: str):
    child, err = _resolve_child(child_id)
    if err is not None:
        return err
    rows = (
        Certificate.query.join(Enrollment, Enrollment.id == Certificate.enrollment_id)
        .filter(Enrollment.student_id == child.id)
        .order_by(Certificate.issued_at.desc())
        .all()
    )
    return jsonify([c.to_dict(include_names=True) for c in rows]), 200
