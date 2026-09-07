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

from typing import Type

from flask import Flask, jsonify
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
    media_bp,
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


# Bumped by hand on release. Surfaced by `/` and `/api/health` so a deploy
# can be identified without shelling in — the old hard-coded `"phase": 2` had
# been stale since Phase 2 and told an operator nothing.
APP_VERSION = "1.0.0"


def _column_ddl(column) -> str:
    """Render a model column as the type half of an `ADD COLUMN` clause."""
    type_sql = column.type.compile(dialect=db.engine.dialect)
    ddl = f"{column.name} {type_sql}"
    # A NOT NULL column can only be added to a populated table if it carries a
    # default, so emit one when the model declares a literal default. Anything
    # more (a callable default, a backfill) needs a real migration.
    default = getattr(column.default, "arg", None)
    if default is not None and not callable(default):
        literal = default
        if isinstance(default, bool):
            literal = "1" if default else "0"
        elif isinstance(default, str):
            literal = f"'{default}'"
        ddl += f" DEFAULT {literal}"
    if not column.nullable:
        ddl += " NOT NULL" if default is not None else ""
    return ddl


def _ensure_schema_updates(app: Flask) -> None:
    """Create missing tables, then add any model column the DB is missing.

    This used to be a hand-maintained list of 16 `(table, column, type)`
    tuples, which meant every new model column silently failed to reach an
    existing database until someone remembered to append to it. The additions
    are now *derived* by diffing `db.metadata` against a live inspector, so a
    new column is picked up the moment it is declared on the model.

    What this deliberately does NOT do — and what still needs a real migration
    tool if the schema ever demands it:

      * renaming or retyping a column
      * dropping a column
      * backfilling values into a new NOT NULL column
      * anything that has to run in a specific order relative to a data change

    See DEPLOY_PYTHONANYWHERE.md for the manual procedure in those cases.
    """
    # `create_app()` is called twice on PythonAnywhere (once at the bottom of
    # this module, once from wsgi_pythonanywhere.py). Reflecting the whole
    # schema twice per boot is pure waste, so latch it — keyed on the database
    # URI, because the test suite builds several apps per process and each new
    # database still needs its tables created.
    done = getattr(_ensure_schema_updates, "_done", None)
    if done is None:
        done = _ensure_schema_updates._done = set()
    uri = app.config.get("SQLALCHEMY_DATABASE_URI")
    if uri in done:
        return

    with app.app_context():
        db.create_all()

        inspector = inspect(db.engine)
        try:
            live_tables = set(inspector.get_table_names())
        except Exception:
            live_tables = set()

        from sqlalchemy import text as _sql_text

        for table_name, table in db.metadata.tables.items():
            if table_name not in live_tables:
                continue  # create_all() just made it — it is already current.
            try:
                existing = {c["name"] for c in inspector.get_columns(table_name)}
            except Exception:
                continue

            for column in table.columns:
                if column.name in existing:
                    continue
                if column.primary_key:
                    continue  # can't bolt a PK on after the fact
                try:
                    db.session.execute(
                        _sql_text(
                            f"ALTER TABLE {table_name} "
                            f"ADD COLUMN {_column_ddl(column)}"
                        )
                    )
                    db.session.commit()
                except Exception:
                    # Another worker won the race, or the dialect refuses the
                    # clause. Roll back so the session stays usable; a genuine
                    # mismatch surfaces on first use of the column.
                    db.session.rollback()

    done.add(uri)


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
    # Mounted at the root: `/media/<path>` URLs are persisted inside
    # lesson + submission rows, so the prefix can't move under /api.
    app.register_blueprint(media_bp)

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

    # --- Health / root ---
    @app.route("/api/health", methods=["GET"])
    def health():
        return jsonify({"status": "ok", "version": APP_VERSION}), 200

    @app.route("/", methods=["GET"])
    def root():
        return (
            jsonify(
                {"service": "lms-api", "version": APP_VERSION, "docs": "/api/health"}
            ),
            200,
        )

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
