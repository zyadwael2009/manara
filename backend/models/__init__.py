"""The Manara data model.

This was one 2,600-line module holding 54 models. It is now a package split
by domain, and this file re-exports every public name so the ~60
`from models import ...` call sites across routes, utils, the seed scripts
and the tests keep working unchanged.

Importing this package imports every submodule, which matters: SQLAlchemy
resolves relationship("Foo") by class name against a registry that is only
complete once every model has been imported.
"""
from models.base import (
    db,
    generate_uuid,
    utc_now,
    _iso,
    password_hash_kwargs,
    datetime,
    Decimal,
    Any,
    check_password_hash,
    generate_password_hash,
    USER_ROLES,
    PARENT_RELATIONSHIPS,
    COURSE_STATUSES,
    LESSON_TYPES,
    ENROLLMENT_STATUSES,
    ENROLLED_VIA,
    COMMON_ELECTIVE_GROUPS,
    COMMON_DEPARTMENTS,
)
from models.school import (
    Section,
    Grade,
    SchoolClass,
    ClassCourseTeacher,
    DepartmentLeader,
)
from models.people import (
    User,
    ParentStudentLink,
    WithdrawalLog,
)
from models.catalog import (
    Course,
    Module,
    Lesson,
    VideoCheckpoint,
    ANNOUNCEMENT_AUDIENCES,
)
from models.enrollment import (
    Enrollment,
    LessonProgress,
)
from models.grading import (
    GRADE_ENTRY_MAX,
    SchoolYear,
    Term,
    GradeCategory,
    CourseRubric,
    GradeEntry,
    GradeEntryHistory,
    GradingScaleBand,
    GradeHistoryPoint,
)
from models.quizzes import (
    QUIZ_QUESTION_TYPES,
    QUIZ_SCORING_MODES,
    Quiz,
    QuizQuestion,
    QuizOption,
    QuizAcceptableAnswer,
    QuizAttempt,
    QuizAnswerEntry,
    AttemptScoreOverride,
    QuestionBankItem,
    QuestionBankOption,
)
from models.assignments import (
    Assignment,
    AssignmentSubmission,
    AssignmentGroup,
    AssignmentGroupMember,
)
from models.attendance import (
    ATTENDANCE_STATUSES,
    AttendanceMark,
)
from models.timetable import (
    TIMETABLE_OVERRIDE_KINDS,
    TimetablePeriod,
    TimetableOverride,
)
from models.comms import (
    Announcement,
    NOTIFICATION_KINDS,
    Notification,
    MessageThread,
    Message,
    LessonComment,
    HomeworkPost,
    PushSubscription,
    NotificationPreference,
)
from models.credentials import (
    Certificate,
    DIPLOMA_HONORS,
    Diploma,
)
from models.fees import (
    FeeItem,
    FeePayment,
)
from models.standards import (
    STANDARD_TAGGABLE_TYPES,
    Standard,
    StandardTag,
)
from models.engagement import (
    StudentStreak,
)
from models.uploads import (
    UploadedFile,
)

__all__ = [
    "db",
    "generate_uuid",
    "utc_now",
    "_iso",
    "password_hash_kwargs",
    "datetime",
    "Decimal",
    "Any",
    "check_password_hash",
    "generate_password_hash",
    "USER_ROLES",
    "PARENT_RELATIONSHIPS",
    "COURSE_STATUSES",
    "LESSON_TYPES",
    "ENROLLMENT_STATUSES",
    "ENROLLED_VIA",
    "COMMON_ELECTIVE_GROUPS",
    "COMMON_DEPARTMENTS",
    "Section",
    "Grade",
    "SchoolClass",
    "ClassCourseTeacher",
    "DepartmentLeader",
    "User",
    "ParentStudentLink",
    "WithdrawalLog",
    "Course",
    "Module",
    "Lesson",
    "VideoCheckpoint",
    "ANNOUNCEMENT_AUDIENCES",
    "Enrollment",
    "LessonProgress",
    "GRADE_ENTRY_MAX",
    "SchoolYear",
    "Term",
    "GradeCategory",
    "CourseRubric",
    "GradeEntry",
    "GradeEntryHistory",
    "GradingScaleBand",
    "GradeHistoryPoint",
    "QUIZ_QUESTION_TYPES",
    "QUIZ_SCORING_MODES",
    "Quiz",
    "QuizQuestion",
    "QuizOption",
    "QuizAcceptableAnswer",
    "QuizAttempt",
    "QuizAnswerEntry",
    "AttemptScoreOverride",
    "QuestionBankItem",
    "QuestionBankOption",
    "Assignment",
    "AssignmentSubmission",
    "AssignmentGroup",
    "AssignmentGroupMember",
    "ATTENDANCE_STATUSES",
    "AttendanceMark",
    "TIMETABLE_OVERRIDE_KINDS",
    "TimetablePeriod",
    "TimetableOverride",
    "Announcement",
    "NOTIFICATION_KINDS",
    "Notification",
    "MessageThread",
    "Message",
    "LessonComment",
    "HomeworkPost",
    "PushSubscription",
    "NotificationPreference",
    "Certificate",
    "DIPLOMA_HONORS",
    "Diploma",
    "FeeItem",
    "FeePayment",
    "STANDARD_TAGGABLE_TYPES",
    "Standard",
    "StandardTag",
    "StudentStreak",
    "UploadedFile",
]
