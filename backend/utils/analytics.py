"""Read-only aggregation helpers for Phase 7 dashboards.

Everything here is derivative — never a source of truth. The functions
read the same cached columns the rest of the app writes to
(`enrollment.progress_percent`, `enrollment.cached_percent`,
`enrollment.cached_letter`, `certificate.revoked`, etc.), so dashboard
numbers agree with the gradebook and student screens by construction.

No writes. No new tables. No rollup caches. If a dashboard call proves
slow at real scale, add an index — never a snapshot table (drifts).
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta
from typing import Iterable

from sqlalchemy import func

from models import (
    Assignment,
    AssignmentSubmission,
    AttendanceMark,
    Certificate,
    ClassCourseTeacher,
    Course,
    Enrollment,
    LessonProgress,
    Module,
    Lesson,
    Quiz,
    QuizAttempt,
    SchoolClass,
    User,
    db,
)
from utils.permissions import classes_user_teaches_for_course, is_admin
from utils.time import utc_now


# ---------------------------------------------------------------------------
# Small internal helpers
# ---------------------------------------------------------------------------
def _safe_div(n: float | int, d: float | int) -> float:
    """Divide, but return 0.0 on divide-by-zero. Used everywhere so an
    empty course renders as 0%, never a crash."""
    if not d:
        return 0.0
    return float(n) / float(d)


def _pct(n: float | int, d: float | int) -> float:
    """Same as _safe_div but expressed as a 0-100 percent, rounded to 2dp."""
    return round(_safe_div(n, d) * 100.0, 2)


def _quiz_best_score_pct(quiz: Quiz, student_id: str) -> float | None:
    """Best-of-attempts score as a percent for one (student, quiz).

    Kept as a fallback for code paths that need a single-pair lookup;
    dashboard code now uses `_quiz_pass_map` / `_quiz_attempted_set` which
    batch across all (student, quiz) pairs in one SQL. Matches the "best"
    scoring rule used by utils/certificates.py.
    """
    attempts = QuizAttempt.query.filter_by(
        quiz_id=quiz.id, student_id=student_id
    ).filter(QuizAttempt.submitted_at.isnot(None)).all()
    if not attempts:
        return None
    max_pct = None
    for a in attempts:
        if a.final_score is None or a.max_score is None or a.max_score == 0:
            continue
        p = float(a.final_score) / float(a.max_score) * 100.0
        if max_pct is None or p > max_pct:
            max_pct = p
    return max_pct


def _student_passed_quiz(quiz: Quiz, student_id: str) -> bool:
    """Same passing rule as utils/certificates.py:_all_quizzes_passed."""
    best = _quiz_best_score_pct(quiz, student_id)
    if best is None:
        return False
    return best >= (quiz.passing_score or 0)


# ---------------------------------------------------------------------------
# Batched aggregate helpers (Phase 10 audit fix M1)
#
# Old dashboard path fired one query per (student × quiz) pair —
# ~1250 queries on the seeded 25-student × ~5-quiz school. These two
# helpers replace that entire nested loop with two SQL group-bys.
# ---------------------------------------------------------------------------
def _quiz_pass_map(
    quizzes: list[Quiz], student_ids: list[str]
) -> dict[tuple[str, str], bool]:
    """Return {(quiz_id, student_id): True} for every pair where the student
    cleared the quiz's `passing_score` on any submitted attempt.

    Missing keys mean "not passed" (which correctly handles the
    unattempted case)."""
    if not quizzes or not student_ids:
        return {}
    quiz_ids = [q.id for q in quizzes]
    # Batched fetch — one query — then Python-side join against each
    # quiz's own passing_score.
    rows = (
        db.session.query(
            QuizAttempt.quiz_id,
            QuizAttempt.student_id,
            QuizAttempt.final_score,
            QuizAttempt.max_score,
        )
        .filter(QuizAttempt.submitted_at.isnot(None))
        .filter(QuizAttempt.quiz_id.in_(quiz_ids))
        .filter(QuizAttempt.student_id.in_(student_ids))
        .all()
    )
    thresholds = {q.id: (q.passing_score or 0) for q in quizzes}
    # Best percentage seen per (quiz, student).
    best: dict[tuple[str, str], float] = {}
    for qid, sid, final, mx in rows:
        if final is None or mx is None or mx == 0:
            continue
        pct = float(final) / float(mx) * 100.0
        key = (qid, sid)
        if pct > best.get(key, -1.0):
            best[key] = pct
    return {
        key: (score >= thresholds.get(key[0], 0))
        for key, score in best.items()
        if score >= thresholds.get(key[0], 0)
    }


def _quiz_attempted_set(
    quiz_ids: list[str], student_ids: list[str]
) -> set[tuple[str, str]]:
    """{(quiz_id, student_id)} for every pair with at least one submitted
    attempt. One query."""
    if not quiz_ids or not student_ids:
        return set()
    rows = (
        db.session.query(QuizAttempt.quiz_id, QuizAttempt.student_id)
        .filter(QuizAttempt.submitted_at.isnot(None))
        .filter(QuizAttempt.quiz_id.in_(quiz_ids))
        .filter(QuizAttempt.student_id.in_(student_ids))
        .distinct()
        .all()
    )
    return {(qid, sid) for qid, sid in rows}


def _course_published_quizzes(course: Course) -> list[Quiz]:
    """Every published quiz across every module of a course."""
    out: list[Quiz] = []
    for module in course.modules:
        for q in Quiz.query.filter_by(module_id=module.id, is_published=True).all():
            out.append(q)
    return out


def _letter_from_pct(p: float | None) -> str | None:
    """Same A/B/C/D/F cutoffs the gradebook uses. Kept here (small) so
    the dashboard doesn't reach into utils/grading.py for a single band."""
    if p is None:
        return None
    if p >= 90:
        return "A"
    if p >= 80:
        return "B"
    if p >= 70:
        return "C"
    if p >= 60:
        return "D"
    return "F"


# ---------------------------------------------------------------------------
# Instructor: which courses does this user teach?
# ---------------------------------------------------------------------------
def _instructor_courses(user: User) -> list[Course]:
    """Every course this user is a class-course teacher of. Admin sees all.

    We do NOT include courses where `Course.instructor_id == user.id`
    without a class-course-teacher row, because Phase 2 downgraded
    `instructor_id` to a hint and made ClassCourseTeacher the
    authoritative "who teaches" relationship (see Course model comment).
    """
    if is_admin(user):
        return Course.query.order_by(Course.title.asc()).all()
    course_ids = {
        row.course_id
        for row in ClassCourseTeacher.query.filter_by(teacher_id=user.id).all()
    }
    if not course_ids:
        return []
    return (
        Course.query.filter(Course.id.in_(course_ids))
        .order_by(Course.title.asc())
        .all()
    )


# ---------------------------------------------------------------------------
# Public API — instructor
# ---------------------------------------------------------------------------
def instructor_course_rows(user: User) -> list[dict]:
    """One row per course the user teaches, with the top-line KPIs.

    Phase 9 audit fix F3: non-admin teachers see only the slice of each
    course they actually teach (their own classes). An admin sees the
    whole school.
    """
    admin = is_admin(user)
    rows: list[dict] = []
    for c in _instructor_courses(user):
        enrollments = Enrollment.query.filter_by(course_id=c.id).filter(
            Enrollment.status.in_(("active", "completed"))
        ).all()
        if not admin:
            allowed = classes_user_teaches_for_course(user, c)
            enrollments = [
                e for e in enrollments
                if e.student is not None and e.student.class_id in allowed
            ]
        n = len(enrollments)
        avg_completion = _safe_div(
            sum((e.progress_percent or 0) for e in enrollments), n
        )
        completion_rate = _safe_div(
            sum(1 for e in enrollments if (e.progress_percent or 0) >= 100), n
        )

        # Quiz pass rate: fraction of (student × published-quiz) pairs the
        # student has cleared. Unattempted quizzes count as fail.
        # Phase 10 audit fix M1: batched — one query per course instead of
        # one per (student, quiz) pair.
        quizzes = _course_published_quizzes(c)
        if quizzes and enrollments:
            total_pairs = len(quizzes) * n
            pass_map = _quiz_pass_map(quizzes, [e.student_id for e in enrollments])
            passed_pairs = len(pass_map)
            quiz_pass_rate = _safe_div(passed_pairs, total_pairs)
        else:
            quiz_pass_rate = 0.0

        # Cert count restricted to the caller's slice of the course.
        if admin:
            cert_count = (
                Certificate.query.join(Enrollment, Enrollment.id == Certificate.enrollment_id)
                .filter(Enrollment.course_id == c.id, Certificate.revoked.is_(False))
                .count()
            )
        else:
            enrollment_ids = {e.id for e in enrollments}
            if enrollment_ids:
                cert_count = (
                    Certificate.query
                    .filter(
                        Certificate.enrollment_id.in_(enrollment_ids),
                        Certificate.revoked.is_(False),
                    )
                    .count()
                )
            else:
                cert_count = 0
        cert_rate = _safe_div(cert_count, n)

        rows.append({
            "id": c.id,
            "title": c.title,
            "gradeName": c.grade.name if c.grade else None,
            "category": c.category,
            "enrollmentCount": n,
            "avgCompletion": round(avg_completion, 2),
            "completionRate": round(completion_rate, 4),
            "quizPassRate": round(quiz_pass_rate, 4),
            "certRate": round(cert_rate, 4),
            "certCount": cert_count,
            "quizCount": len(quizzes),
        })
    return rows


def course_drilldown(course: Course, viewer: User | None = None) -> dict:
    """Rich per-course breakdown: completion histogram, per-module & per-quiz
    rates, top 5 students, at-risk list.

    Phase 9 audit fix F3: `viewer` is the caller. If not admin, filter the
    enrollment set to students in classes the viewer teaches for this course
    — so Teacher X in Class A never sees Class B students' names in the
    at-risk / top-5 lists.
    """
    enrollments = Enrollment.query.filter_by(course_id=course.id).filter(
        Enrollment.status.in_(("active", "completed"))
    ).all()
    if viewer is not None and not is_admin(viewer):
        allowed = classes_user_teaches_for_course(viewer, course)
        enrollments = [
            e for e in enrollments
            if e.student is not None and e.student.class_id in allowed
        ]
    n = len(enrollments)

    # Completion histogram — 5 buckets of 20% each, 100 lands in the last.
    buckets = [0, 0, 0, 0, 0]
    for e in enrollments:
        p = int(e.progress_percent or 0)
        idx = min(p // 20, 4)
        buckets[idx] += 1
    histogram = [
        {"label": "0-19%", "count": buckets[0]},
        {"label": "20-39%", "count": buckets[1]},
        {"label": "40-59%", "count": buckets[2]},
        {"label": "60-79%", "count": buckets[3]},
        {"label": "80-100%", "count": buckets[4]},
    ]

    # Per-module completion: for each enrollment, fraction of that module's
    # lessons the student has marked complete; then average across
    # enrollments. Modules with zero lessons render as 0.
    module_rows: list[dict] = []
    for module in course.modules.order_by(Module.order_index).all():
        lesson_ids = [lid for (lid,) in db.session.query(Lesson.id).filter_by(module_id=module.id).all()]
        if not lesson_ids or not enrollments:
            module_rows.append({"id": module.id, "title": module.title, "avgCompletion": 0.0})
            continue
        total = 0.0
        for e in enrollments:
            done = (
                LessonProgress.query.filter(
                    LessonProgress.enrollment_id == e.id,
                    LessonProgress.lesson_id.in_(lesson_ids),
                    LessonProgress.completed.is_(True),
                ).count()
            )
            total += done / len(lesson_ids)
        module_rows.append({
            "id": module.id,
            "title": module.title,
            "avgCompletion": _pct(total, len(enrollments)),
        })

    # Per-quiz pass rate.
    # Phase 10 audit fix M1: batched — one _quiz_pass_map + one
    # _quiz_attempted_set query cover every (student × quiz) pair in this
    # course. Was previously ~250 sub-queries per drilldown on seed data.
    quizzes_all = _course_published_quizzes(course)
    student_ids = [e.student_id for e in enrollments]
    pass_map = _quiz_pass_map(quizzes_all, student_ids)
    attempted_set = _quiz_attempted_set([q.id for q in quizzes_all], student_ids)
    quiz_rows: list[dict] = []
    for q in quizzes_all:
        if not enrollments:
            quiz_rows.append({
                "id": q.id, "title": q.title,
                "passingScore": q.passing_score,
                "passRate": 0.0, "attemptedRate": 0.0,
            })
            continue
        passed = sum(1 for sid in student_ids if (q.id, sid) in pass_map)
        attempted = sum(1 for sid in student_ids if (q.id, sid) in attempted_set)
        quiz_rows.append({
            "id": q.id,
            "title": q.title,
            "passingScore": q.passing_score,
            "passRate": _pct(passed, len(enrollments)) / 100.0,
            "attemptedRate": _pct(attempted, len(enrollments)) / 100.0,
        })

    # Top 5 by cached cumulative percent (nulls last).
    ranked = sorted(
        enrollments,
        key=lambda e: (float(e.cached_percent) if e.cached_percent is not None else -1.0),
        reverse=True,
    )
    top5: list[dict] = []
    for e in ranked[:5]:
        if e.cached_percent is None:
            continue
        s = e.student
        top5.append({
            "studentId": s.id if s else None,
            "studentName": s.name if s else None,
            "percent": float(e.cached_percent),
            "letter": e.cached_letter,
        })

    # At-risk: progress < 50 OR cached_percent < threshold.
    threshold = course.min_certificate_percent if course.min_certificate_percent is not None else 60
    at_risk: list[dict] = []
    for e in enrollments:
        reasons: list[str] = []
        p = int(e.progress_percent or 0)
        if p < 50:
            reasons.append("low_progress")
        if e.cached_percent is not None and float(e.cached_percent) < threshold:
            reasons.append("below_grade_threshold")
        if not reasons:
            continue
        s = e.student
        at_risk.append({
            "studentId": s.id if s else None,
            "studentName": s.name if s else None,
            "progressPercent": p,
            "cachedPercent": float(e.cached_percent) if e.cached_percent is not None else None,
            "reasons": reasons,
        })

    return {
        "courseId": course.id,
        "courseTitle": course.title,
        "enrollmentCount": n,
        "minCertificatePercent": threshold,
        "completionHistogram": histogram,
        "moduleCompletion": module_rows,
        "quizPassRates": quiz_rows,
        "topStudents": top5,
        "atRisk": at_risk,
    }


# ---------------------------------------------------------------------------
# Public API — admin
# ---------------------------------------------------------------------------
def admin_topline() -> dict:
    total_users = User.query.filter_by(is_active=True).count()
    by_role: dict[str, int] = dict(
        db.session.query(User.role, func.count(User.id))
        .filter(User.is_active.is_(True))
        .group_by(User.role)
        .all()
    )
    published_courses = Course.query.filter_by(status="published").count()
    draft_courses = Course.query.filter_by(status="draft").count()
    active_enrollments = Enrollment.query.filter(
        Enrollment.status.in_(("active", "completed"))
    ).count()
    completed = Enrollment.query.filter(
        Enrollment.status.in_(("active", "completed")),
        Enrollment.progress_percent >= 100,
    ).count()

    now = utc_now()
    since_30 = now - timedelta(days=30)
    certs_30 = Certificate.query.filter(
        Certificate.issued_at >= since_30, Certificate.revoked.is_(False)
    ).count()

    # Phase 30 · T2 — fee KPI rollup: total outstanding balance and
    # number of students with any overdue fee. Fees are orthogonal to
    # grading so this stays a purely aggregate read (no join into
    # enrollments/certificates).
    from models import FeeItem, FeePayment
    from sqlalchemy import func as _f
    fee_billed = float(
        db.session.query(_f.coalesce(_f.sum(FeeItem.amount), 0)).scalar() or 0
    )
    fee_paid = float(
        db.session.query(_f.coalesce(_f.sum(FeePayment.amount), 0)).scalar() or 0
    )
    fee_outstanding = round(fee_billed - fee_paid, 2)

    # "Overdue" = due_date < today and balance > 0. Use a subquery that
    # sums payments per fee to compute balance in-DB rather than
    # per-row-Python.
    today = now.date()
    payments_by_fee = (
        db.session.query(
            FeePayment.fee_item_id.label("fid"),
            _f.coalesce(_f.sum(FeePayment.amount), 0).label("paid"),
        )
        .group_by(FeePayment.fee_item_id)
        .subquery()
    )
    overdue_student_ids = (
        db.session.query(FeeItem.student_id)
        .outerjoin(payments_by_fee, payments_by_fee.c.fid == FeeItem.id)
        .filter(FeeItem.due_date.isnot(None))
        .filter(FeeItem.due_date < today)
        .filter(
            FeeItem.amount > _f.coalesce(payments_by_fee.c.paid, 0)
        )
        .distinct()
        .all()
    )
    overdue_students = len(overdue_student_ids)

    return {
        "totalUsers": total_users,
        "usersByRole": {
            "admin": int(by_role.get("admin", 0)),
            "instructor": int(by_role.get("instructor", 0)),
            "student": int(by_role.get("student", 0)),
            "parent": int(by_role.get("parent", 0)),
        },
        "publishedCourses": published_courses,
        "draftCourses": draft_courses,
        "activeEnrollments": active_enrollments,
        "platformCompletionRate": round(_safe_div(completed, active_enrollments), 4),
        "certsIssuedLast30d": certs_30,
        "feeOutstandingTotal": fee_outstanding,
        "studentsWithOverdueFees": overdue_students,
    }


def most_popular_courses(limit: int = 10) -> list[dict]:
    """Top courses by active-enrollment count. Draft courses included so an
    admin can still see draft demand — filter in the UI if not wanted."""
    rows = (
        db.session.query(
            Course.id, Course.title, func.count(Enrollment.id).label("n")
        )
        .outerjoin(Enrollment, (Enrollment.course_id == Course.id)
                   & (Enrollment.status.in_(("active", "completed"))))
        .group_by(Course.id, Course.title)
        .order_by(func.count(Enrollment.id).desc(), Course.title.asc())
        .limit(limit)
        .all()
    )
    return [{"courseId": r[0], "title": r[1], "enrollmentCount": int(r[2] or 0)} for r in rows]


def highest_completion_courses(limit: int = 10, min_n: int = 5) -> list[dict]:
    """Top courses by average progress %, with a floor on enrollment count so
    a course with a single 100% student doesn't dominate."""
    rows = (
        db.session.query(
            Course.id,
            Course.title,
            func.avg(Enrollment.progress_percent).label("avg"),
            func.count(Enrollment.id).label("n"),
        )
        .join(Enrollment, Enrollment.course_id == Course.id)
        .filter(Enrollment.status.in_(("active", "completed")))
        .group_by(Course.id, Course.title)
        .having(func.count(Enrollment.id) >= min_n)
        .order_by(func.avg(Enrollment.progress_percent).desc(), Course.title.asc())
        .limit(limit)
        .all()
    )
    return [
        {
            "courseId": r[0],
            "title": r[1],
            "avgCompletion": round(float(r[2] or 0.0), 2),
            "enrollmentCount": int(r[3]),
        }
        for r in rows
    ]


def _month_bucket_series(dates: Iterable[datetime], months: int) -> list[dict]:
    """Bucket a stream of datetimes into the last `months` calendar buckets,
    zero-filled. Bucket key = 'YYYY-MM' of the datetime's month.
    """
    now = utc_now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    keys: list[tuple[int, int]] = []
    # Walk back `months - 1` calendar months from `now`, oldest first.
    year, month = now.year, now.month
    stack: list[tuple[int, int]] = []
    for _ in range(months):
        stack.append((year, month))
        month -= 1
        if month == 0:
            month = 12
            year -= 1
    stack.reverse()
    keys = stack
    counts: dict[tuple[int, int], int] = {k: 0 for k in keys}
    key_set = set(keys)
    for d in dates:
        k = (d.year, d.month)
        if k in key_set:
            counts[k] += 1
    return [
        {"month": f"{y:04d}-{m:02d}", "count": counts[(y, m)]}
        for (y, m) in keys
    ]


def certs_per_month(months: int = 6) -> list[dict]:
    """Certificates issued per month for the last `months` calendar months.
    Zero-filled. Revoked certs still count on the month they were issued —
    they represent past activity even if later invalidated.
    """
    since = utc_now().replace(day=1) - timedelta(days=32 * (months - 1))
    rows = (
        db.session.query(Certificate.issued_at)
        .filter(Certificate.issued_at >= since)
        .all()
    )
    return _month_bucket_series((r[0] for r in rows if r[0] is not None), months)


def users_per_month(months: int = 6) -> list[dict]:
    since = utc_now().replace(day=1) - timedelta(days=32 * (months - 1))
    rows = (
        db.session.query(User.created_at)
        .filter(User.created_at >= since)
        .all()
    )
    return _month_bucket_series((r[0] for r in rows if r[0] is not None), months)


def grade_band_distribution() -> dict:
    """Enrollment count per letter grade across the whole platform.
    Uses the cached_letter column (kept fresh by utils/grading.py). Only
    enrollments that have a cached percent get counted — an enrollment
    with no grade entries yet doesn't fall into any band.
    """
    counts = Counter()
    rows = (
        db.session.query(Enrollment.cached_letter)
        .filter(Enrollment.cached_letter.isnot(None))
        .filter(Enrollment.status.in_(("active", "completed")))
        .all()
    )
    for (letter,) in rows:
        counts[letter] += 1
    return {
        "A": int(counts.get("A", 0)),
        "B": int(counts.get("B", 0)),
        "C": int(counts.get("C", 0)),
        "D": int(counts.get("D", 0)),
        "F": int(counts.get("F", 0)),
    }


# ---------------------------------------------------------------------------
# Phase 22 — at-risk student flagging
#
# Read-only. Uses only cached / derived signals already present in the DB.
# No new writes, no rollup dependence. Callers are the class-roster
# endpoint (Phase 22.1) and the homeroom UI.
# ---------------------------------------------------------------------------
_AT_RISK_MIN_PERCENT = 60.0
_AT_RISK_MIN_ATTENDANCE = 80.0
_AT_RISK_MISSING_ASSIGNMENTS = 3
_AT_RISK_FAILED_QUIZZES = 2


def compute_at_risk(student: User) -> dict:
    """Return `{atRisk: bool, reasons: [...]}` for one student.

    Reasons currently checked:
      * `low_grade`         — mean of cached_percent across active
                              enrollments < 60.
      * `low_attendance`    — attendance % < 80.
      * `missing_work`      — 3+ past-due assignments never submitted.
      * `failing_quizzes`   — 2+ quizzes where BEST attempt fell below
                              the passing score.
    """
    reasons: list[str] = []

    # 1) Low cumulative grade.
    enrolls = (
        Enrollment.query.filter_by(student_id=student.id)
        .filter(Enrollment.status.in_(("active", "completed")))
        .all()
    )
    percents = [
        float(e.cached_percent)
        for e in enrolls
        if e.cached_percent is not None
    ]
    if percents and (sum(percents) / len(percents)) < _AT_RISK_MIN_PERCENT:
        reasons.append("low_grade")

    # 2) Low attendance.
    from utils.attendance import compute_student_attendance_summary
    att = compute_student_attendance_summary(student.id)
    if att["percent"] is not None and att["percent"] < _AT_RISK_MIN_ATTENDANCE:
        reasons.append("low_attendance")

    # 3) Missing assignments — past-due, no submission, in this student's
    #    active enrollments' modules.
    course_ids = [e.course_id for e in enrolls]
    if course_ids:
        module_ids = [
            m.id for m in Module.query.filter(Module.course_id.in_(course_ids)).all()
        ]
        if module_ids:
            now = utc_now()
            due_past = (
                Assignment.query
                .filter(Assignment.module_id.in_(module_ids))
                .filter(Assignment.is_published.is_(True))
                .filter(Assignment.due_at.isnot(None))
                .filter(Assignment.due_at < now)
                .all()
            )
            missed = 0
            for a in due_past:
                sub = AssignmentSubmission.query.filter_by(
                    assignment_id=a.id, student_id=student.id,
                ).first()
                if sub is None or sub.submitted_at is None:
                    missed += 1
            if missed >= _AT_RISK_MISSING_ASSIGNMENTS:
                reasons.append("missing_work")

    # 4) Failed quizzes — best attempt below passing score.
    if course_ids:
        module_ids = [
            m.id for m in Module.query.filter(Module.course_id.in_(course_ids)).all()
        ]
        pub_quizzes = (
            Quiz.query.filter(Quiz.module_id.in_(module_ids))
            .filter(Quiz.is_published.is_(True))
            .all()
        ) if module_ids else []
        failing = 0
        for q in pub_quizzes:
            attempts = (
                QuizAttempt.query.filter_by(
                    quiz_id=q.id, student_id=student.id,
                )
                .filter(QuizAttempt.submitted_at.isnot(None))
                .filter(QuizAttempt.final_score.isnot(None))
                .filter(QuizAttempt.max_score.isnot(None))
                .all()
            )
            if not attempts:
                continue
            best_pct = max(
                (float(a.final_score) / float(a.max_score) * 100.0)
                for a in attempts
                if a.max_score and float(a.max_score) > 0
            )
            if best_pct < q.passing_score:
                failing += 1
        if failing >= _AT_RISK_FAILED_QUIZZES:
            reasons.append("failing_quizzes")

    return {"atRisk": bool(reasons), "reasons": reasons}


# ---------------------------------------------------------------------------
# Phase 22 — attendance patterns dashboard
# ---------------------------------------------------------------------------
def compute_attendance_patterns(
    *, chronic_threshold_pct: float = 80.0, top_n: int = 10
) -> dict:
    """Admin-only patterns block:
      * chronicAbsentees — students below `chronic_threshold_pct`
                           attendance (top-N by absent count desc).
      * tardyLeaders     — top-N by late-count desc.
      * classes          — per-class mean attendance %, top-N desc.
    """
    from utils.attendance import compute_student_attendance_summary

    # Chronic absentees + tardy leaders — walk every active student.
    students = User.query.filter_by(role="student", is_active=True).all()
    chronic: list[dict] = []
    tardy: list[dict] = []
    for s in students:
        summary = compute_student_attendance_summary(s.id)
        if summary["total"] == 0:
            continue
        pct = summary["percent"]
        if pct is not None and pct < chronic_threshold_pct:
            chronic.append({
                "studentId": s.id,
                "name": s.name,
                "pctPresent": pct,
                "absentCount": summary["absent"],
            })
        if summary["late"] > 0:
            tardy.append({
                "studentId": s.id,
                "name": s.name,
                "lateCount": summary["late"],
            })
    chronic.sort(key=lambda r: (-r["absentCount"], r["pctPresent"] or 0))
    tardy.sort(key=lambda r: -r["lateCount"])

    # Per-class mean attendance — one grouped SQL over marks.
    rows = (
        db.session.query(
            AttendanceMark.class_id,
            AttendanceMark.status,
            func.count(AttendanceMark.id),
        )
        .group_by(AttendanceMark.class_id, AttendanceMark.status)
        .all()
    )
    by_class: dict[str, dict] = {}
    for cid, status, n in rows:
        entry = by_class.setdefault(cid, {"total": 0, "good": 0})
        entry["total"] += int(n)
        if status in ("present", "excused"):
            entry["good"] += int(n)
    class_rows: list[dict] = []
    for cid, agg in by_class.items():
        if agg["total"] == 0:
            continue
        sc = db.session.get(SchoolClass, cid)
        class_rows.append({
            "classId": cid,
            "name": sc.name if sc else "",
            "pctPresent": round(agg["good"] / agg["total"] * 100.0, 1),
            "marksCount": agg["total"],
        })
    class_rows.sort(key=lambda r: -r["pctPresent"])

    return {
        "chronicAbsentees": chronic[:top_n],
        "tardyLeaders": tardy[:top_n],
        "classes": class_rows[:top_n],
    }
