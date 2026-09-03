"""Phase 7 — Dashboards & Reports.

Three read-only endpoints:
  * GET  /api/dashboard/instructor                 — instructor or admin
  * GET  /api/dashboard/instructor/courses/<id>    — course-teacher / admin
  * GET  /api/dashboard/admin                      — admin only

There are NO write methods in this blueprint. Every metric reads the
same cached columns the rest of the app writes to (progress_percent,
cached_percent, cached_letter, certificate.revoked) so a number that
shows up here always agrees with what the student sees in their
gradebook.
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from models import (
    AttendanceMark,
    Certificate,
    Course,
    Enrollment,
    GradeEntry,
    SchoolClass,
    Term,
    User,
    db,
)
from routes.auth import current_user, login_required, require_admin
from utils.analytics import (
    admin_topline,
    certs_per_month,
    course_drilldown,
    grade_band_distribution,
    highest_completion_courses,
    instructor_course_rows,
    most_popular_courses,
    users_per_month,
)
from utils.permissions import (
    is_admin,
    is_instructor,
    teaches_course_in_any_class,
)

dashboards_bp = Blueprint("dashboards", __name__)


def _can_view_course_analytics(user, course: Course) -> bool:
    """Admin, or any teacher who's on class_course_teachers for this course.
    Deliberately NOT the department leader — leaders review content, not
    per-course rosters, and we don't want unexpected cross-course drilldown
    leakage. Add if the product wants it later.
    """
    if is_admin(user):
        return True
    return teaches_course_in_any_class(user, course)


# ---------------------------------------------------------------------------
# Instructor landing — every course you teach, at-a-glance
# ---------------------------------------------------------------------------
@dashboards_bp.route("/dashboard/instructor", methods=["GET"])
@login_required
def instructor_dashboard():
    user = current_user()
    if not (is_instructor(user) or is_admin(user)):
        return jsonify({"error": "You do not have permission."}), 403
    rows = instructor_course_rows(user)
    # Top-line summary across all their courses — sums enrolments and
    # weighted averages the per-course metrics so the header KPIs match
    # what you'd get by hand from the rows below.
    total_students = sum(r["enrollmentCount"] for r in rows)
    if total_students:
        weighted_completion = sum(
            r["avgCompletion"] * r["enrollmentCount"] for r in rows
        ) / total_students
        weighted_quiz_pass = sum(
            r["quizPassRate"] * r["enrollmentCount"] for r in rows
        ) / total_students
    else:
        weighted_completion = 0.0
        weighted_quiz_pass = 0.0
    return jsonify({
        "courses": rows,
        "summary": {
            "courseCount": len(rows),
            "totalStudents": total_students,
            "avgCompletion": round(weighted_completion, 2),
            "avgQuizPassRate": round(weighted_quiz_pass, 4),
        },
    }), 200


# ---------------------------------------------------------------------------
# Per-course drill-down
# ---------------------------------------------------------------------------
@dashboards_bp.route("/dashboard/instructor/courses/<string:course_id>", methods=["GET"])
@login_required
def instructor_course_drilldown(course_id: str):
    user = current_user()
    course = db.session.get(Course, course_id)
    if course is None:
        return jsonify({"error": "Course not found."}), 404
    if not _can_view_course_analytics(user, course):
        return jsonify({"error": "You do not have permission."}), 403
    return jsonify(course_drilldown(course, viewer=user)), 200


# ---------------------------------------------------------------------------
# Admin dashboard
# ---------------------------------------------------------------------------
@dashboards_bp.route("/dashboard/admin", methods=["GET"])
@require_admin
def admin_dashboard():
    return jsonify({
        "topline": admin_topline(),
        "mostPopular": most_popular_courses(limit=10),
        "highestCompletion": highest_completion_courses(limit=10, min_n=5),
        "certsPerMonth": certs_per_month(months=6),
        "usersPerMonth": users_per_month(months=6),
        "gradeBands": grade_band_distribution(),
    }), 200


# ---------------------------------------------------------------------------
# Phase 28 — Cohort / semester comparison
#
# Compares two terms side-by-side across the metrics an admin most often
# asks about ("did last semester improve on the one before it?"). All
# reads join through the SAME cache the rest of the app relies on
# (`enrollments.cached_percent`, `certificate.revoked`), so the numbers
# here always agree with the report card and the admin dashboard.
# ---------------------------------------------------------------------------
def _term_snapshot(term: Term) -> dict:
    """Return the per-metric numbers for one term, broken out by class.

    Metrics per class:
      * students          — active students in the class
      * attendanceRate    — present marks / total marks in the term window
      * avgPercent        — mean of enrollments.cached_percent for that class
      * passRate          — % of active enrollments with cached_percent >= 60
      * certCount         — non-revoked certificates issued in this term
    """
    # Term window is used only for attendance + certificate filtering;
    # grade cache is a rolling snapshot, so we use it as-is.
    start = term.start_date
    end = term.end_date
    # Every class in the school — the per-class block skips ones with
    # no active students, so we still get one row per active class
    # without needing a class↔term join table.
    classes = db.session.query(SchoolClass).all()
    per_class: list[dict] = []
    for sc in classes:
        cid = sc.id
        students = [s for s in sc.students if s.is_active]
        student_ids = [s.id for s in students]
        if not student_ids:
            continue

        # Attendance rate over the term window.
        attn_q = AttendanceMark.query.filter(
            AttendanceMark.student_id.in_(student_ids),
        )
        if start is not None:
            attn_q = attn_q.filter(AttendanceMark.date >= start)
        if end is not None:
            attn_q = attn_q.filter(AttendanceMark.date <= end)
        marks = attn_q.all()
        total = len(marks)
        present = sum(1 for m in marks if m.status == "present")
        attendance_rate = (present / total) if total else 0.0

        # Grade percent + pass rate over active enrollments for this class.
        enrolls = Enrollment.query.filter(
            Enrollment.student_id.in_(student_ids),
            Enrollment.status == "active",
        ).all()
        pcts = [
            float(e.cached_percent)
            for e in enrolls if e.cached_percent is not None
        ]
        avg_percent = (sum(pcts) / len(pcts)) if pcts else 0.0
        pass_rate = (
            (sum(1 for p in pcts if p >= 60) / len(pcts))
            if pcts else 0.0
        )

        # Cert count — issued inside the term window, not revoked.
        # Certificate is scoped by enrollment_id, so join through
        # Enrollment.student_id to filter to this class's students.
        cert_q = (
            Certificate.query
            .join(Enrollment, Enrollment.id == Certificate.enrollment_id)
            .filter(
                Enrollment.student_id.in_(student_ids),
                Certificate.revoked.is_(False),
            )
        )
        if start is not None:
            cert_q = cert_q.filter(Certificate.issued_at >= start)
        if end is not None:
            # End-of-day slack — Certificate.issued_at is datetime, term.end_date is date.
            from datetime import datetime as _dt, time as _time
            cert_q = cert_q.filter(
                Certificate.issued_at <= _dt.combine(end, _time.max))
        cert_count = cert_q.count()

        per_class.append({
            "classId": cid,
            "className": sc.name,
            "gradeId": sc.grade_id,
            "students": len(students),
            "attendanceRate": round(attendance_rate, 4),
            "avgPercent": round(avg_percent, 2),
            "passRate": round(pass_rate, 4),
            "certCount": cert_count,
        })

    # Whole-term rollup (unweighted so a small class doesn't get lost).
    if per_class:
        overall_attn = sum(c["attendanceRate"] for c in per_class) / len(per_class)
        overall_pct = sum(c["avgPercent"] for c in per_class) / len(per_class)
        overall_pass = sum(c["passRate"] for c in per_class) / len(per_class)
        overall_certs = sum(c["certCount"] for c in per_class)
    else:
        overall_attn = overall_pct = overall_pass = 0.0
        overall_certs = 0

    return {
        "termId": term.id,
        "termName": term.name,
        "startDate": term.start_date.isoformat() if term.start_date else None,
        "endDate": term.end_date.isoformat() if term.end_date else None,
        "perClass": per_class,
        "overall": {
            "attendanceRate": round(overall_attn, 4),
            "avgPercent": round(overall_pct, 2),
            "passRate": round(overall_pass, 4),
            "certCount": overall_certs,
        },
    }


@dashboards_bp.route("/dashboards/cohort-comparison", methods=["GET"])
@require_admin
def cohort_comparison():
    a_id = request.args.get("termAId")
    b_id = request.args.get("termBId")
    if not a_id or not b_id:
        return jsonify({"error": "termAId and termBId are required."}), 400
    a = db.session.get(Term, a_id)
    b = db.session.get(Term, b_id)
    if a is None or b is None:
        return jsonify({"error": "One or both terms not found."}), 404
    return jsonify({
        "termA": _term_snapshot(a),
        "termB": _term_snapshot(b),
    }), 200


# ---------------------------------------------------------------------------
# Phase 30 · T3 — Cohort comparison CSV export
#
# Same shape as the JSON endpoint, flattened to one row per class with
# the four metrics side-by-side (termA_x, termB_x). One trailing row
# for the whole-term overall so the CSV alone is enough for a
# post-meeting spreadsheet compare.
# ---------------------------------------------------------------------------
@dashboards_bp.route("/dashboards/cohort-comparison.csv", methods=["GET"])
@require_admin
def cohort_comparison_csv():
    a_id = request.args.get("termAId")
    b_id = request.args.get("termBId")
    if not a_id or not b_id:
        return jsonify({"error": "termAId and termBId are required."}), 400
    a = db.session.get(Term, a_id)
    b = db.session.get(Term, b_id)
    if a is None or b is None:
        return jsonify({"error": "One or both terms not found."}), 404
    snap_a = _term_snapshot(a)
    snap_b = _term_snapshot(b)

    import csv as _csv
    import io as _io
    from flask import Response
    buf = _io.StringIO()
    writer = _csv.writer(buf)
    writer.writerow([
        "classId", "className", "gradeId",
        f"{a.name}_students", f"{a.name}_attendanceRate",
        f"{a.name}_avgPercent", f"{a.name}_passRate", f"{a.name}_certCount",
        f"{b.name}_students", f"{b.name}_attendanceRate",
        f"{b.name}_avgPercent", f"{b.name}_passRate", f"{b.name}_certCount",
    ])
    # Merge on classId — a class in only one term still shows.
    by_id: dict[str, dict] = {}
    for row in snap_a["perClass"]:
        by_id.setdefault(row["classId"], {})["a"] = row
    for row in snap_b["perClass"]:
        by_id.setdefault(row["classId"], {})["b"] = row

    for cid, pair in by_id.items():
        ra = pair.get("a") or {}
        rb = pair.get("b") or {}
        name = ra.get("className") or rb.get("className") or ""
        grade = ra.get("gradeId") or rb.get("gradeId") or ""
        writer.writerow([
            cid, name, grade,
            ra.get("students", ""), ra.get("attendanceRate", ""),
            ra.get("avgPercent", ""), ra.get("passRate", ""),
            ra.get("certCount", ""),
            rb.get("students", ""), rb.get("attendanceRate", ""),
            rb.get("avgPercent", ""), rb.get("passRate", ""),
            rb.get("certCount", ""),
        ])
    # Trailing whole-term rollup.
    oa = snap_a["overall"]
    ob = snap_b["overall"]
    writer.writerow([
        "", "OVERALL", "",
        "", oa["attendanceRate"], oa["avgPercent"],
        oa["passRate"], oa["certCount"],
        "", ob["attendanceRate"], ob["avgPercent"],
        ob["passRate"], ob["certCount"],
    ])
    return Response(
        buf.getvalue(),
        mimetype="text/csv",
        headers={
            "Content-Disposition":
                f'attachment; filename="cohort-{a.name}-vs-{b.name}.csv"',
        },
    )


# ---------------------------------------------------------------------------
# Phase 31 · T3 — Cohort comparison PDF export
#
# Same two term snapshots as the JSON/CSV endpoints, rendered as a
# two-page PDF (one page per term) sharing the fees-PDF chrome so an
# admin folder of exports has one voice.
# ---------------------------------------------------------------------------
@dashboards_bp.route("/dashboards/cohort-comparison.pdf", methods=["GET"])
@require_admin
def cohort_comparison_pdf():
    from flask import Response as _Response
    a_id = request.args.get("termAId")
    b_id = request.args.get("termBId")
    if not a_id or not b_id:
        return jsonify({"error": "termAId and termBId are required."}), 400
    a = db.session.get(Term, a_id)
    b = db.session.get(Term, b_id)
    if a is None or b is None:
        return jsonify({"error": "One or both terms not found."}), 404
    from utils.pdf import render_cohort_comparison_pdf
    try:
        pdf_bytes = render_cohort_comparison_pdf(
            _term_snapshot(a), _term_snapshot(b),
        )
    except Exception:  # pragma: no cover - reportlab breakage
        return jsonify({"error": "Could not render PDF."}), 500
    return _Response(
        pdf_bytes,
        mimetype="application/pdf",
        headers={
            "Content-Disposition":
                f'inline; filename="cohort-{a.name}-vs-{b.name}.pdf"',
        },
    )
