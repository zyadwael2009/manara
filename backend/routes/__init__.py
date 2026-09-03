"""Blueprint registry — imported by `app.create_app` and mounted under /api."""
from routes.auth import auth_bp
from routes.users import users_bp
from routes.sections import sections_bp
from routes.grades import grades_bp
from routes.classes import classes_bp
from routes.courses import courses_bp
from routes.modules import modules_bp
from routes.lessons import lessons_bp
from routes.enrollments import enrollments_bp
from routes.students import students_bp
from routes.department_leaders import department_leaders_bp
from routes.uploads import uploads_bp

# Phase 3 additions
from routes.progress import progress_bp
from routes.grading_admin import grading_admin_bp
from routes.rubrics import rubrics_bp
from routes.grade_reports import grade_reports_bp

# Phase 4 — quizzes
from routes.quizzes import quizzes_bp
from routes.quiz_take import quiz_take_bp
from routes.quiz_admin import quiz_admin_bp

# Phase 5 — certificates
from routes.certificates import certificates_bp

# Phase 7 — dashboards & reports
from routes.dashboards import dashboards_bp

# Phase 6 — parent portal
from routes.parents import parents_bp

# Phase 12 — attendance
from routes.attendance import attendance_bp

# Phase 13 — timetables
from routes.timetables import timetables_bp

# Phase 14 — assignments
from routes.assignments import assignments_bp

# Phase 18 — "Today" landing endpoint
from routes.today import today_bp

# Phase 19 — announcements (school / class / course)
from routes.announcements import announcements_bp

# Phase 20 — admin bulk CSV import
from routes.admin_import import admin_import_bp

# Phase 21 — notifications, DMs, lesson comments, homework board
from routes.notifications import notifications_bp
from routes.messages import messages_bp
from routes.comments import comments_bp
from routes.homework import homework_bp

# Phase 22 — insight & intervention
from routes.insight import insight_bp

# Phase 23 — PDF report card + transcript
from routes.report_cards import report_cards_bp

# Phase 24 — streak/badges, question bank, global search
from routes.streak import streak_bp
from routes.search import search_bp
from routes.question_bank import question_bank_bp

# Phase 25 — admin CSV export + ICS calendar feed
from routes.admin_export import admin_export_bp
from routes.calendar_feed import calendar_feed_bp

# Phase 27 — video checkpoints + group assignments
from routes.checkpoints import checkpoints_bp
from routes.assignment_groups import assignment_groups_bp

# Phase 28 — web push + fees
from routes.push import push_bp
from routes.fees import fees_bp

# Phase 32 — diplomas + standards
from routes.diplomas import diplomas_bp
from routes.standards import standards_bp

__all__ = [
    "auth_bp",
    "users_bp",
    "sections_bp",
    "grades_bp",
    "classes_bp",
    "courses_bp",
    "modules_bp",
    "lessons_bp",
    "enrollments_bp",
    "students_bp",
    "department_leaders_bp",
    "uploads_bp",
    "progress_bp",
    "grading_admin_bp",
    "rubrics_bp",
    "grade_reports_bp",
    "quizzes_bp",
    "quiz_take_bp",
    "quiz_admin_bp",
    "certificates_bp",
    "dashboards_bp",
    "parents_bp",
    "attendance_bp",
    "timetables_bp",
    "assignments_bp",
    "today_bp",
    "announcements_bp",
    "admin_import_bp",
    "notifications_bp",
    "messages_bp",
    "comments_bp",
    "homework_bp",
    "insight_bp",
    "report_cards_bp",
    "streak_bp",
    "search_bp",
    "question_bank_bp",
    "admin_export_bp",
    "calendar_feed_bp",
    "checkpoints_bp",
    "assignment_groups_bp",
    "push_bp",
    "fees_bp",
    "diplomas_bp",
    "standards_bp",
]
