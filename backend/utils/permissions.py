"""Permission helpers — the single-source-of-truth for Rule #6 (trust core).

Every content-view / content-edit / roster-mutation check in the app routes
through one of the helpers here. Never re-implement these predicates inline
in a route handler.

See project memory files for the reasoning behind each rule:
  - lms-is-k12-school, school-hierarchy, curriculum-model, teacher-roles
"""
from __future__ import annotations

from models import (
    ClassCourseTeacher,
    Course,
    DepartmentLeader,
    Enrollment,
    Lesson,
    Module,
    ParentStudentLink,
    SchoolClass,
    User,
    db,
)

# Phase 4 imports are lazy inside functions to avoid a circular-import
# hazard (models.py imports permissions.py transitively via routes).


# =============================================================================
# Role predicates
# =============================================================================
def is_admin(user: User | None) -> bool:
    return user is not None and user.role == "admin"


def is_instructor(user: User | None) -> bool:
    return user is not None and user.role == "instructor"


def is_student(user: User | None) -> bool:
    return user is not None and user.role == "student"


def is_parent(user: User | None) -> bool:
    return user is not None and user.role == "parent"


# =============================================================================
# Teacher-relationship predicates
# =============================================================================
def teaches_course_in_any_class(user: User | None, course: Course) -> bool:
    """True if `user` is the assigned teacher of `course` in at least one class."""
    if user is None or not is_instructor(user):
        return False
    return (
        ClassCourseTeacher.query.filter_by(course_id=course.id, teacher_id=user.id).first()
        is not None
    )


def teaches_course_in_class(user: User | None, course: Course, school_class: SchoolClass) -> bool:
    """True if `user` teaches `course` specifically in `school_class`."""
    if user is None or not is_instructor(user):
        return False
    return (
        ClassCourseTeacher.query.filter_by(
            course_id=course.id, class_id=school_class.id, teacher_id=user.id
        ).first()
        is not None
    )


def homerooms_class(user: User | None, school_class: SchoolClass) -> bool:
    if user is None:
        return False
    return school_class.homeroom_teacher_id == user.id


def homerooms_student(user: User | None, student: User) -> bool:
    """True if `user` is the homeroom teacher of `student`'s class."""
    if user is None or not is_instructor(user) or student.class_id is None:
        return False
    sc = db.session.get(SchoolClass, student.class_id)
    return sc is not None and sc.homeroom_teacher_id == user.id


def can_view_class_timetable(user: User | None, sc: SchoolClass) -> bool:
    """Phase 13: who can read the class's weekly timetable.

    Superset of `can_view_class_roster` — extends to students placed in
    the class (they need their own schedule) and any parent linked to a
    student in the class. Timetables are less sensitive than roster
    emails, so the wider read scope is fine.
    """
    if user is None or sc is None:
        return False
    if can_view_class_roster(user, sc):
        return True
    if is_student(user) and user.class_id == sc.id:
        return True
    return False


def can_mark_attendance(user: User | None, student: User) -> bool:
    """Phase 12: who can mark a student present/absent/late/excused.

    Admin, or the homeroom teacher of the student's current class.
    Deliberately NOT any course teacher — a Math teacher shouldn't be able
    to mark the whole day; only the homeroom does morning check-in.
    """
    if user is None or student is None:
        return False
    if is_admin(user):
        return True
    return homerooms_student(user, student)


def homerooms_a_student_enrolled_in(user: User | None, course: Course) -> bool:
    """True if `user` homerooms ANY class whose student is enrolled in `course`.

    This is what lets a homeroom teacher see the content of every subject her
    students take — even subjects she doesn't teach herself.
    """
    if user is None or not is_instructor(user):
        return False
    # Class(es) this user homerooms.
    homeroom_classes = SchoolClass.query.filter_by(homeroom_teacher_id=user.id).all()
    if not homeroom_classes:
        return False
    homeroom_class_ids = {c.id for c in homeroom_classes}
    # Any active enrollment in `course` from a student whose class is one of ours.
    q = (
        db.session.query(Enrollment)
        .join(User, User.id == Enrollment.student_id)
        .filter(
            Enrollment.course_id == course.id,
            Enrollment.status.in_(("active", "completed")),
            User.class_id.in_(homeroom_class_ids),
        )
    )
    return db.session.query(q.exists()).scalar()


def is_department_leader(user: User | None, department: str, section_id: str | None) -> bool:
    """True if `user` heads the given (department, section) slot.

    `section_id` can be None — a course whose grade has no section yet has no
    dept leader; caller falls back to the vacancy rules.
    """
    if user is None or not is_instructor(user) or section_id is None:
        return False
    row = DepartmentLeader.query.filter_by(department=department, section_id=section_id).first()
    return row is not None and row.teacher_id == user.id


def department_leader_of(department: str, section_id: str | None) -> DepartmentLeader | None:
    if section_id is None:
        return None
    return DepartmentLeader.query.filter_by(department=department, section_id=section_id).first()


def teaches_any_course_in_dept_section(user: User | None, department: str, section_id: str | None) -> bool:
    """Vacancy-fallback predicate: user teaches at least one course in this
    dept-section. Used when the department leader slot is empty.
    """
    if user is None or not is_instructor(user) or section_id is None:
        return False
    q = (
        db.session.query(ClassCourseTeacher)
        .join(Course, Course.id == ClassCourseTeacher.course_id)
        .join(SchoolClass, SchoolClass.id == ClassCourseTeacher.class_id)
        .filter(
            ClassCourseTeacher.teacher_id == user.id,
            Course.category == department,
            SchoolClass.grade.has(section_id=section_id),
        )
    )
    return db.session.query(q.exists()).scalar()


# =============================================================================
# Phase 6 — Parent linkage predicates
# =============================================================================
def linked_children_ids(parent: User | None) -> set[str]:
    """Every student id currently linked to `parent`. Empty set for a
    non-parent or a parent with no links."""
    if parent is None or not is_parent(parent):
        return set()
    return {
        row.student_id
        for row in ParentStudentLink.query.filter_by(parent_id=parent.id).all()
    }


def is_linked_parent_of(parent: User | None, student: User) -> bool:
    """True if `parent` has a ParentStudentLink to `student`."""
    if parent is None or not is_parent(parent) or student is None:
        return False
    return (
        ParentStudentLink.query.filter_by(
            parent_id=parent.id, student_id=student.id
        ).first()
        is not None
    )


def is_linked_parent_of_enrolled(parent: User | None, course: Course) -> bool:
    """True if `parent` is linked to a student who has an active enrollment
    in `course`. Lets a parent view lesson content for what their child is
    actually studying — without ever appearing on the enrolment roster."""
    if parent is None or not is_parent(parent):
        return False
    kids = linked_children_ids(parent)
    if not kids:
        return False
    q = (
        db.session.query(Enrollment)
        .filter(
            Enrollment.course_id == course.id,
            Enrollment.student_id.in_(kids),
            Enrollment.status.in_(("active", "completed")),
        )
    )
    return db.session.query(q.exists()).scalar()


# =============================================================================
# Class-scoped read/enumeration helpers (Phase 9 audit fixes F1-F4)
# =============================================================================
def classes_user_teaches_for_course(
    user: User | None, course: Course
) -> set[str]:
    """Class IDs the user teaches THIS course in. Empty for non-teachers.

    Used to filter cross-class PII leaks on course-scoped reads (quiz
    attempts, dashboard drill-downs, course enrollments). Admin sees
    everything and is handled by the caller — this helper just returns
    the teacher's own slice.
    """
    if user is None or not is_instructor(user):
        return set()
    return {
        row.class_id
        for row in ClassCourseTeacher.query.filter_by(
            course_id=course.id, teacher_id=user.id
        ).all()
    }


def can_view_class_roster(user: User | None, school_class: SchoolClass) -> bool:
    """Who can see a class's full student roster (name + email).

    Admin, homeroom of the class, any teacher who teaches ANY course in
    the class, or a parent linked to at least one student in the class.
    Deliberately does NOT include unrelated students — a Grade 9 student
    should not be able to enumerate Grade 10 emails.
    """
    if user is None:
        return False
    if is_admin(user):
        return True
    if school_class is None:
        return False
    if homerooms_class(user, school_class):
        return True
    if is_instructor(user):
        row = ClassCourseTeacher.query.filter_by(
            class_id=school_class.id, teacher_id=user.id,
        ).first()
        if row is not None:
            return True
    if is_parent(user):
        # Linked to any student currently placed in this class?
        from models import ParentStudentLink
        q = (
            db.session.query(ParentStudentLink)
            .join(User, User.id == ParentStudentLink.student_id)
            .filter(
                ParentStudentLink.parent_id == user.id,
                User.class_id == school_class.id,
                User.is_active.is_(True),
            )
        )
        if db.session.query(q.exists()).scalar():
            return True
    return False


# =============================================================================
# Enrollment predicate
# =============================================================================
def has_active_enrollment(user: User | None, course: Course) -> bool:
    if user is None or not is_student(user):
        return False
    e = Enrollment.query.filter_by(student_id=user.id, course_id=course.id).first()
    return e is not None and e.status in ("active", "completed")


# =============================================================================
# The two big trust-core gates — content view + content edit
# =============================================================================
def can_view_content(user: User | None, course: Course) -> bool:
    """Who can see full lesson content (contentUrl / contentText) of a course."""
    if is_admin(user):
        return True
    if teaches_course_in_any_class(user, course):
        return True
    section_id = course.grade.section_id if course.grade else None
    if is_department_leader(user, course.category, section_id):
        return True
    if has_active_enrollment(user, course):
        return True
    if homerooms_a_student_enrolled_in(user, course):
        return True
    # Phase 6: a parent linked to a student who is enrolled here.
    if is_linked_parent_of_enrolled(user, course):
        return True
    return False


def can_edit_course_content(user: User | None, course: Course) -> bool:
    """Who can add/edit/delete modules and lessons on a course.

    Rule (per teacher-roles memory):
      - Admin always.
      - Department leader for the course's (dept × section) always.
      - If the leader slot is VACANT, any class-course teacher of that
        dept-section can edit — a fallback so courses don't dead-lock while
        a leader is being found.
    """
    if is_admin(user):
        return True
    section_id = course.grade.section_id if course.grade else None
    leader = department_leader_of(course.category, section_id)
    if leader is None:
        return teaches_any_course_in_dept_section(user, course.category, section_id)
    return leader.teacher_id == (user.id if user else None)


# Convenience wrappers around the two gates for module / lesson objects.
def can_view_module_content(user: User | None, module: Module) -> bool:
    return can_view_content(user, module.course)


def can_view_lesson_content(user: User | None, lesson: Lesson) -> bool:
    return can_view_content(user, lesson.module.course)


def can_edit_module(user: User | None, module: Module) -> bool:
    return can_edit_course_content(user, module.course)


def can_edit_lesson(user: User | None, lesson: Lesson) -> bool:
    return can_edit_course_content(user, lesson.module.course)


# =============================================================================
# Class-course assignment permission
# =============================================================================
def can_assign_class_course_teacher(user: User | None, course: Course) -> bool:
    """Admin OR the department leader for that course's (dept × section)."""
    if is_admin(user):
        return True
    section_id = course.grade.section_id if course.grade else None
    return is_department_leader(user, course.category, section_id)


# =============================================================================
# Elective picking permission
# =============================================================================
def can_pick_elective_for(user: User | None, student: User) -> bool:
    """Admin OR homeroom teacher of the student's class.

    A homeroom teacher can only pick electives for students in HER OWN
    homeroom — never students of another class.
    """
    if is_admin(user):
        return True
    return homerooms_student(user, student)


# =============================================================================
# Student-record visibility (progress, quiz attempts — used from Phase 3+)
# =============================================================================
def can_enter_grades_for(user: User | None, student: User, course: Course) -> bool:
    """Who can enter/edit a grade for `student` in `course`.

    Admin, or the department leader for the course's (dept × section), OR
    the specific class-course teacher for THIS student's class (via
    class_course_teachers).
    """
    if is_admin(user):
        return True
    if can_edit_course_content(user, course):
        return True  # dept leader / vacancy fallback
    if student.class_id is None:
        return False
    sc = db.session.get(SchoolClass, student.class_id)
    if sc is None:
        return False
    return teaches_course_in_class(user, course, sc)


def can_view_report_card(user: User | None, student: User) -> bool:
    """Same shape as can_view_student_records — student, admin, homeroom,
    any course teacher of the student's class, (later) linked parent."""
    return can_view_student_records(user, student)


# =============================================================================
# Phase 4 — Quiz permissions
# =============================================================================
def can_take_quiz(user: User | None, quiz) -> bool:
    """Only enrolled students, in the course the quiz's module belongs to."""
    if user is None or not is_student(user):
        return False
    course = quiz.module.course
    return has_active_enrollment(user, course)


def can_view_quiz_attempt(user: User | None, attempt) -> bool:
    """Own attempt (student), admin, or any staff who can see the student's
    records (homeroom teacher, class-course teacher, admin, later parent)."""
    if user is None:
        return False
    if is_admin(user):
        return True
    if attempt.student_id == user.id:
        return True
    student = attempt.student
    if student is None:
        return False
    return can_view_student_records(user, student)


def can_override_quiz_score(user: User | None, attempt) -> bool:
    """Admin, or the class-course teacher of the student's class, or the
    dept leader for the course. Homeroom-only readers cannot override."""
    if user is None:
        return False
    if is_admin(user):
        return True
    student = attempt.student
    course = attempt.quiz.module.course if attempt.quiz else None
    if student is None or course is None:
        return False
    return can_enter_grades_for(user, student, course)


def can_view_student_records(user: User | None, student: User) -> bool:
    """Who can see this student's progress / grades / quiz attempts.

    Admin, any course teacher of a class the student is in, the student's
    homeroom teacher, and (Phase 6) linked parent. Plus the student themself.
    """
    if user is None:
        return False
    if is_admin(user):
        return True
    if user.id == student.id:
        return True
    if homerooms_student(user, student):
        return True
    if is_instructor(user) and student.class_id is not None:
        # A course teacher of ANY class the student is in.
        has_class = (
            db.session.query(ClassCourseTeacher)
            .filter_by(class_id=student.class_id, teacher_id=user.id)
            .first()
            is not None
        )
        if has_class:
            return True
    # Phase 6: a linked parent can see the child's records.
    if is_linked_parent_of(user, student):
        return True
    return False
