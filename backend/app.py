"""Flask app factory for the Manara backend.

Layout mirrors ClubHub: `create_app(config_class=Config)` factory that ends
with `app = create_app()` at module bottom for gunicorn / PythonAnywhere.

Phase 2 additions:
  * New blueprints: sections, grades, classes, students (placement +
    electives), enrollments, department_leaders, uploads, users.
  * New static-serving route `/media/<path>` for uploaded lesson media.
  * Higher MAX_CONTENT_LENGTH for uploads (200 MB).
"""
from __future__ import annotations

from pathlib import Path
from typing import Type

from flask import Flask, current_app, jsonify, send_from_directory
from flask_cors import CORS
from sqlalchemy import inspect
from werkzeug.middleware.proxy_fix import ProxyFix

from config import Config
from models import db
from routes import (
    admin_export_bp,
    admin_import_bp,
    announcements_bp,
    assignment_groups_bp,
    calendar_feed_bp,
    checkpoints_bp,
    comments_bp,
    diplomas_bp,
    fees_bp,
    homework_bp,
    insight_bp,
    messages_bp,
    notifications_bp,
    push_bp,
    question_bank_bp,
    report_cards_bp,
    search_bp,
    standards_bp,
    streak_bp,
    assignments_bp,
    attendance_bp,
    today_bp,
    auth_bp,
    certificates_bp,
    classes_bp,
    courses_bp,
    dashboards_bp,
    department_leaders_bp,
    enrollments_bp,
    grade_reports_bp,
    grades_bp,
    grading_admin_bp,
    lessons_bp,
    modules_bp,
    parents_bp,
    progress_bp,
    quiz_admin_bp,
    quiz_take_bp,
    quizzes_bp,
    rubrics_bp,
    sections_bp,
    students_bp,
    timetables_bp,
    uploads_bp,
    users_bp,
)
from routes.auth import load_session_from_header


def _ensure_schema_updates(app: Flask) -> None:
    """Create-or-migrate the schema in a lightweight, additive way.

    Phase 1: `db.create_all()`.
    Phase 2: adds new tables (created automatically by create_all) AND adds
    new columns to existing tables via ALTER for developer databases that
    were created against the Phase-1 schema. Fresh DBs get everything from
    `db.create_all()` directly.

    The additive ALTERs are best-effort — if a column already exists (fresh
    DB, or previous run added it), the error is swallowed.
    """
    with app.app_context():
        db.create_all()

        inspector = inspect(db.engine)
        # Phase-2 additive columns on Phase-1 tables --------------------------
        additions = [
            ("users", "class_id", "VARCHAR(36)"),
            ("users", "graduated_at", "DATETIME"),
            ("courses", "grade_id", "VARCHAR(36)"),
            ("courses", "elective_group", "VARCHAR(80)"),
            ("courses", "succeeds_course_id", "VARCHAR(36)"),
            # Phase 3 grade cache
            ("enrollments", "cached_percent", "NUMERIC(5,2)"),
            ("enrollments", "cached_letter", "VARCHAR(8)"),
            ("enrollments", "cached_gpa", "NUMERIC(4,2)"),
            ("enrollments", "cached_computed_at", "DATETIME"),
            # Phase 5 certificate threshold
            ("courses", "min_certificate_percent", "INTEGER"),
            # Phase 23 — student withdrawal
            ("users", "withdrawn_at", "DATETIME"),
            # Phase 24 — quiz question-bank pool size
            ("quizzes", "pool_size", "INTEGER"),
            # Phase 25 — per-user opaque calendar feed token
            ("users", "calendar_token", "VARCHAR(64)"),
            # Phase 27 — group-mode assignments + video checkpoints +
            # Meet URL on recurring periods. All additive on existing
            # tables so dev DBs can pick them up on next boot.
            ("assignments", "is_group", "BOOLEAN"),
            ("assignments", "max_group_size", "INTEGER"),
            ("assignment_submissions", "group_id", "VARCHAR(36)"),
            ("timetable_periods", "meeting_url", "VARCHAR(1000)"),
        ]
        existing_cols = {}
        try:
            for table, _col, _typ in additions:
                cols = existing_cols.get(table)
                if cols is None:
                    try:
                        cols = {c["name"] for c in inspector.get_columns(table)}
                    except Exception:
                        cols = set()
                    existing_cols[table] = cols
        except Exception:
            existing_cols = {}

        # Phase 33 fix #16 — cross-DB safe: `inspector.get_columns()`
        # was already the primary gate; the string-sniff on
        # "duplicate column"/"already exists" was a Postgres/MySQL
        # error-text lottery. Drop the fallback and re-inspect after
        # each ALTER so a concurrent worker's write is visible.
        from sqlalchemy import text as _sql_text
        for table, col, typ in additions:
            cols = existing_cols.get(table)
            if cols is None:
                try:
                    cols = {c["name"] for c in inspector.get_columns(table)}
                except Exception:
                    cols = set()
                existing_cols[table] = cols
            if col in cols:
                continue
            # Re-check right before ALTER in case a peer worker won
            # the race between our earlier snapshot and now.
            try:
                fresh = {c["name"] for c in inspector.get_columns(table)}
                existing_cols[table] = fresh
                if col in fresh:
                    continue
            except Exception:
                pass
            db.session.execute(_sql_text(
                f"ALTER TABLE {table} ADD COLUMN {col} {typ}"
            ))
            db.session.commit()
            existing_cols[table].add(col)


def create_app(config_class: Type[Config] = Config) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Phase 2: allow uploads up to 200 MB.
    app.config["MAX_CONTENT_LENGTH"] = 200 * 1024 * 1024

    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)

    db.init_app(app)

    CORS(
        app,
        origins=app.config["CORS_ORIGINS"],
        supports_credentials=True,
        expose_headers=["X-Session-Token"],
    )

    _ensure_schema_updates(app)

    app.before_request(load_session_from_header)

    # Phase 8: small brand ping in the network tab.
    @app.after_request
    def _stamp(response):
        response.headers.setdefault("X-Powered-By", "Manara")
        return response

    # --- Blueprints ---
    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(users_bp, url_prefix="/api/users")
    app.register_blueprint(sections_bp, url_prefix="/api/sections")
    app.register_blueprint(grades_bp, url_prefix="/api/grades")
    app.register_blueprint(classes_bp, url_prefix="/api/classes")
    app.register_blueprint(courses_bp, url_prefix="/api/courses")
    # modules/lessons/enrollments blueprints declare full paths themselves.
    app.register_blueprint(modules_bp, url_prefix="/api")
    app.register_blueprint(lessons_bp, url_prefix="/api")
    app.register_blueprint(enrollments_bp, url_prefix="/api")
    # Students placement + electives lives at /api/users/<id>/{class,electives}.
    app.register_blueprint(students_bp, url_prefix="/api/users")
    app.register_blueprint(department_leaders_bp, url_prefix="/api/department-leaders")
    app.register_blueprint(uploads_bp, url_prefix="/api/uploads")

    # Phase 3 — progress + grading
    app.register_blueprint(progress_bp, url_prefix="/api")            # declares full paths itself
    app.register_blueprint(grading_admin_bp, url_prefix="/api")       # /api/school-years, /api/terms, etc.
    app.register_blueprint(rubrics_bp, url_prefix="/api")             # /api/courses/<id>/rubric
    app.register_blueprint(grade_reports_bp, url_prefix="/api")       # gradebook + reports

    # Phase 4 — quizzes
    app.register_blueprint(quizzes_bp, url_prefix="/api")             # author CRUD
    app.register_blueprint(quiz_take_bp, url_prefix="/api")           # student take flow
    app.register_blueprint(quiz_admin_bp, url_prefix="/api")          # attempts list + override

    # Phase 5 — certificates
    app.register_blueprint(certificates_bp, url_prefix="/api")        # reads + revoke + public /api/verify/<num>
    app.register_blueprint(dashboards_bp, url_prefix="/api")          # Phase 7 — instructor + admin dashboards
    app.register_blueprint(parents_bp, url_prefix="/api")             # Phase 6 — parent portal (read-only)
    app.register_blueprint(attendance_bp, url_prefix="/api")          # Phase 12 — daily attendance
    app.register_blueprint(timetables_bp, url_prefix="/api")          # Phase 13 — timetables
    app.register_blueprint(assignments_bp, url_prefix="/api")         # Phase 14 — assignments
    app.register_blueprint(today_bp, url_prefix="/api")               # Phase 18 — student "today" landing
    app.register_blueprint(announcements_bp, url_prefix="/api")       # Phase 19 — announcements
    app.register_blueprint(admin_import_bp, url_prefix="/api")        # Phase 20 — admin CSV import
    app.register_blueprint(notifications_bp, url_prefix="/api")       # Phase 21 — notifications
    app.register_blueprint(messages_bp, url_prefix="/api")            # Phase 21 — DMs
    app.register_blueprint(comments_bp, url_prefix="/api")            # Phase 21 — lesson comments
    app.register_blueprint(homework_bp, url_prefix="/api")            # Phase 21 — homework board
    app.register_blueprint(insight_bp, url_prefix="/api")             # Phase 22 — insight & intervention
    app.register_blueprint(report_cards_bp, url_prefix="/api")        # Phase 23 — PDF report cards + transcripts
    app.register_blueprint(streak_bp, url_prefix="/api")              # Phase 24 — streak + badges
    app.register_blueprint(search_bp, url_prefix="/api")              # Phase 24 — global search
    app.register_blueprint(question_bank_bp, url_prefix="/api")       # Phase 24 — question bank
    app.register_blueprint(admin_export_bp, url_prefix="/api")        # Phase 25 — admin CSV export
    app.register_blueprint(calendar_feed_bp, url_prefix="/api")       # Phase 25 — ICS calendar feed

    # Phase 27 — video-inline checkpoints + group assignments
    app.register_blueprint(checkpoints_bp, url_prefix="/api")
    app.register_blueprint(assignment_groups_bp, url_prefix="/api")

    # Phase 28 — web push subscriptions + fees + receipts
    app.register_blueprint(push_bp, url_prefix="/api")
    app.register_blueprint(fees_bp, url_prefix="/api")

    # Phase 32 — digital diplomas + curriculum standards
    app.register_blueprint(diplomas_bp, url_prefix="/api")
    app.register_blueprint(standards_bp, url_prefix="/api")

    # --- Static media serving --------------------------------------------------
    # Resolve the upload dir at request time (not register time) so tests
    # that swap `app.instance_path` after `create_app()` behave correctly.
    @app.route("/media/<path:filename>", methods=["GET"])
    def serve_media(filename: str):
        return send_from_directory(
            str(Path(current_app.instance_path) / "uploads"), filename
        )

    # --- Health / root ---
    @app.route("/api/health", methods=["GET"])
    def health():
        return jsonify({"status": "ok", "phase": 2}), 200

    @app.route("/", methods=["GET"])
    def root():
        return jsonify({"service": "lms-api", "phase": 2, "docs": "/api/health"}), 200

    # --- JSON error handlers ---
    @app.errorhandler(404)
    def _404(_e):
        return jsonify({"error": "Not found."}), 404

    @app.errorhandler(405)
    def _405(_e):
        return jsonify({"error": "Method not allowed."}), 405

    @app.errorhandler(413)
    def _413(_e):
        return jsonify({"error": "File too large. Max 200 MB."}), 413

    @app.errorhandler(500)
    def _500(_e):
        return jsonify({"error": "Internal server error."}), 500

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
