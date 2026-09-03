"""Phase 8 tests — seed self-consistency.

Proves the demo seed produces a coherent, gate-honest school state:
  - Every certificate was issued via the trust-core gate (progress=100 +
    passing grade + all quizzes passed) — none seeded in behind the API.
  - Every graded active enrollment has its cached_percent + cached_letter
    columns written (proves utils.grading ran through the seed flow).
  - The grade-band distribution covers at least three letter grades so the
    admin dashboard donut has real texture.

These invariants are the ones that would silently break if the seed ever
grew a back-door DB insert for grades or certificates.
"""
from __future__ import annotations

import sys

import pytest


@pytest.fixture()
def app_with_seed(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx")

    for mod in [
        "config", "models",
        "utils.permissions", "utils.grading", "utils.quizzes",
        "utils.certificates", "utils.analytics", "utils.attendance", "utils.timetables", "utils.assignments",
        "routes", "routes.auth", "routes.users",
        "routes.sections", "routes.grades", "routes.classes",
        "routes.courses", "routes.modules", "routes.lessons",
        "routes.enrollments", "routes.students",
        "routes.department_leaders", "routes.uploads",
        "routes.progress", "routes.grading_admin",
        "routes.rubrics", "routes.grade_reports",
        "routes.quizzes", "routes.quiz_take", "routes.quiz_admin",
        "routes.certificates", "routes.dashboards", "routes.parents", "routes.attendance", "routes.timetables", "routes.assignments",
        "app", "seed_dev",
    ]:
        sys.modules.pop(mod, None)

    from app import create_app
    from config import Config
    from models import db

    inst = tmp_path / "instance"
    inst.mkdir()
    (inst / "uploads").mkdir()

    class TestConfig(Config):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{(tmp_path / 'test.db').as_posix()}"
        TESTING = True
        SQLALCHEMY_ENGINE_OPTIONS = {}
        MAX_CONTENT_LENGTH = 5 * 1024 * 1024

    app = create_app(TestConfig)
    app.instance_path = str(inst)

    # Patch seed_dev.create_app so `seed_dev.main()` uses our TestConfig app
    # instead of building a fresh one against the real dev DB.
    import seed_dev
    monkeypatch.setattr(seed_dev, "create_app", lambda *a, **kw: app)

    with app.app_context():
        db.drop_all()
        db.create_all()

    return app


def test_full_seed_is_self_consistent(app_with_seed, capsys):
    from seed_dev import main as run_seed
    from models import (
        Certificate,
        Enrollment,
        GradeEntry,
        ParentStudentLink,
        User,
        db,
    )
    from utils.certificates import is_eligible

    with app_with_seed.app_context():
        run_seed()

        # Phase 15: multi-grade K-12 school. Bounds are wide because the seed
        # size can shift as rosters are edited; the test guards invariants,
        # not exact counts.
        student_count = User.query.filter_by(role="student", is_active=True).count()
        assert student_count >= 100, (
            f"expected >= 100 students (multi-grade K-12), got {student_count}"
        )

        # Multiple demo parents with mixed link fanout.
        parents = User.query.filter_by(role="parent", is_active=True).all()
        assert len(parents) >= 2
        max_children = max(
            ParentStudentLink.query.filter_by(parent_id=p.id).count()
            for p in parents
        )
        assert max_children >= 2, (
            f"expected at least one parent linked to multiple children, "
            f"got max fanout {max_children}"
        )

        # Every certificate was actually gate-eligible when issued. If any
        # fails, the seed has drifted into back-door territory.
        certs = Certificate.query.filter(Certificate.revoked.is_(False)).all()
        assert len(certs) >= 5, f"expected >=5 seeded certs, got {len(certs)}"
        for cert in certs:
            ok, missing = is_eligible(cert.enrollment)
            assert ok, (
                f"cert {cert.certificate_number} for enrollment {cert.enrollment_id}"
                f" fails is_eligible: {missing}"
            )

        # Every ACTIVE enrollment with grade entries has a cached_percent
        # + cached_letter written. If either is None, utils.grading didn't
        # recompute — a real regression that would leave the gradebook stale.
        rows = (
            db.session.query(Enrollment)
            .filter(Enrollment.status.in_(("active", "completed")))
            .all()
        )
        graded_missing_cache = 0
        for e in rows:
            has_entries = GradeEntry.query.filter_by(enrollment_id=e.id).first() is not None
            if has_entries and (e.cached_percent is None or e.cached_letter is None):
                graded_missing_cache += 1
        assert graded_missing_cache == 0, (
            f"{graded_missing_cache} graded enrollments have NULL cached_percent/letter"
        )

        # Grade-band distribution has real texture — at least 3 different letters.
        letters = {e.cached_letter for e in rows if e.cached_letter is not None}
        letters_top_level = {letter[0] for letter in letters if letter}
        assert len(letters_top_level) >= 3, (
            f"grade-band distribution too flat for a good demo donut: {letters}"
        )
