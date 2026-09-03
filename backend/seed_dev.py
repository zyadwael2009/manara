"""Manara demo school seed — Phase 15 full K-12.

Idempotent. Deterministic (Random(42)). Every write goes through the same
helpers the runtime uses — no back-door inserts for grades or certificates.

Rough numbers at end of run:
  * 8 grades in 3 sections (Elementary K-6, Middle 7-9, High 10-12)
  * 9 classes (Grade 9 has 2: 9-A + 9-B)
  * ~140 students, ~10 teachers, 5 parents, 1 admin
  * ~40 courses, ~120 modules, ~500 lessons
  * ~24 quizzes, ~1500 quiz attempts, ~40 certificates
  * ~36 assignments, ~800 submissions
  * ~8400 attendance marks (60 school days)
  * ~200 timetable periods

Run: `python seed_dev.py` — targets ≤ 45 s on a fresh SQLite DB.
"""
from __future__ import annotations

import random
from datetime import date as _date, datetime, time as _time, timedelta
from decimal import Decimal

from app import create_app
from models import (
    Assignment,
    AssignmentGroup,
    AssignmentGroupMember,
    AssignmentSubmission,
    AttendanceMark,
    Certificate,
    ClassCourseTeacher,
    Course,
    CourseRubric,
    DepartmentLeader,
    Diploma,
    Enrollment,
    FeeItem,
    FeePayment,
    Grade,
    GradeCategory,
    GradeEntry,
    GradingScaleBand,
    Lesson,
    LessonProgress,
    Module,
    NotificationPreference,
    ParentStudentLink,
    Quiz,
    QuizAttempt,
    QuizOption,
    QuizQuestion,
    SchoolClass,
    SchoolYear,
    Section,
    Standard,
    StandardTag,
    Term,
    TimetableOverride,
    TimetablePeriod,
    User,
    VideoCheckpoint,
    db,
)
from utils.time import utc_now


# =============================================================================
# Small upsert helpers (idempotent building blocks)
# =============================================================================
def _upsert_user(email: str, name: str, role: str, password: str) -> User:
    u = User.query.filter_by(email=email).first()
    if u:
        return u
    u = User(name=name, email=email, role=role)
    u.set_password(password)
    db.session.add(u)
    db.session.commit()
    return u


def _upsert_section(name: str, order_index: int) -> Section:
    s = Section.query.filter_by(name=name).first()
    if s:
        return s
    s = Section(name=name, order_index=order_index)
    db.session.add(s)
    db.session.commit()
    return s


def _upsert_grade(name: str, section: Section, order_index: int) -> Grade:
    g = Grade.query.filter_by(name=name).first()
    if g:
        return g
    g = Grade(name=name, section_id=section.id, order_index=order_index)
    db.session.add(g)
    db.session.commit()
    return g


def _upsert_class(name: str, grade: Grade, homeroom: User | None) -> SchoolClass:
    sc = SchoolClass.query.filter_by(grade_id=grade.id, name=name).first()
    if sc:
        return sc
    sc = SchoolClass(
        grade_id=grade.id,
        name=name,
        homeroom_teacher_id=homeroom.id if homeroom else None,
    )
    db.session.add(sc)
    db.session.commit()
    return sc


def _upsert_course(*, title: str, grade: Grade, category: str,
                   elective_group: str | None = None,
                   description: str = "") -> Course:
    c = Course.query.filter_by(title=title, grade_id=grade.id).first()
    if c:
        return c
    c = Course(
        title=title,
        description=description or f"{title} — auto-seeded demo content.",
        grade_id=grade.id,
        category=category,
        elective_group=elective_group,
        status="published",
    )
    db.session.add(c)
    db.session.commit()
    return c


def _assign_class_course_teacher(
    course: Course, cls: SchoolClass, teacher: User,
) -> None:
    if teacher is None:
        return
    row = ClassCourseTeacher.query.filter_by(
        course_id=course.id, class_id=cls.id).first()
    if row:
        return
    db.session.add(ClassCourseTeacher(
        course_id=course.id, class_id=cls.id, teacher_id=teacher.id))
    db.session.commit()


def _place_student_in_class(student: User, cls: SchoolClass) -> None:
    if student.class_id == cls.id:
        return
    student.class_id = cls.id
    db.session.commit()
    from routes.students import _auto_enroll_mandatory_for_grade
    _auto_enroll_mandatory_for_grade(student, cls.grade_id, student)


def _seed_school_year_and_terms() -> Term:
    year = SchoolYear.query.filter_by(name="2025-2026").first()
    if year is None:
        for other in SchoolYear.query.filter_by(is_current=True).all():
            other.is_current = False
        year = SchoolYear(name="2025-2026", is_current=True)
        db.session.add(year)
        db.session.commit()
    for i, name in enumerate(["Q1", "Q2", "Q3", "Q4"]):
        if Term.query.filter_by(school_year_id=year.id, name=name).first() is None:
            db.session.add(Term(school_year_id=year.id, name=name, order_index=i))
    db.session.commit()
    return Term.query.filter_by(school_year_id=year.id, name="Q1").first()


_CATEGORY_SEED = [
    ("commitment", "Commitment", False),
    ("class_projects", "Class projects", False),
    ("participation", "Participation", False),
    ("class_work", "Class work", False),
    ("assignments", "Assignments", False),
    ("quizzes", "Quizzes", True),
    ("subject_projects", "Subject projects", False),
    ("oral", "Oral", False),
    ("writing", "Writing", False),
    ("practical", "Practical", False),
    ("final_exam", "Final Exam", False),
]


def _seed_grade_categories() -> dict[str, GradeCategory]:
    for i, (slug, name, is_system) in enumerate(_CATEGORY_SEED):
        if GradeCategory.query.filter_by(slug=slug).first() is None:
            db.session.add(GradeCategory(
                slug=slug, name=name, order_index=i, is_system=is_system))
    db.session.commit()
    return {s: GradeCategory.query.filter_by(slug=s).first()
            for s, _, _ in _CATEGORY_SEED}


_SCALE_SEED = [
    (98, 100, "A+", 4.00), (93, 97, "A", 4.00), (90, 92, "A-", 3.75),
    (87, 89, "B+", 3.25), (83, 86, "B", 3.00), (80, 82, "B-", 2.75),
    (77, 79, "C+", 2.25), (73, 76, "C", 2.00), (70, 72, "C-", 1.75),
    (67, 69, "D+", 1.25), (63, 66, "D", 1.00), (60, 62, "D-", 0.75),
    (0, 59, "F", 0.00),
]


def _seed_grading_scale() -> None:
    for i, (mn, mx, letter, gpa) in enumerate(_SCALE_SEED):
        if GradingScaleBand.query.filter_by(letter=letter).first() is None:
            db.session.add(GradingScaleBand(
                min_percent=mn, max_percent=mx, letter=letter,
                gpa_value=gpa, order_index=i))
    db.session.commit()


def _seed_rubric(course: Course, cats: dict[str, GradeCategory]) -> None:
    """Standard 100-point rubric matching the reference report card weights."""
    if CourseRubric.query.filter_by(course_id=course.id).count() > 0:
        return
    items = [
        (cats["commitment"], 15, 0),
        (cats["class_projects"], 5, 1),
        (cats["participation"], 10, 2),
        (cats["class_work"], 10, 3),
        (cats["assignments"], 10, 4),
        (cats["quizzes"], 5, 5),
        (cats["subject_projects"], 5, 6),
        (cats["final_exam"], 40, 7),
    ]
    for cat, max_score, order in items:
        db.session.add(CourseRubric(
            course_id=course.id, grade_category_id=cat.id,
            max_score=max_score, order_index=order))
    db.session.commit()


# =============================================================================
# The demo school data — 8 grades, ~140 students, ~40 courses
# =============================================================================
# One human-readable key per grade. Order matters for rendering + promotion.
_GRADE_KEYS = ["G1", "G3", "G6", "G7", "G9-A", "G9-B", "G10", "G11", "G12"]

# (section, grade-name, order_index) per key.
_GRADE_META: dict[str, tuple[str, str, int]] = {
    "G1":  ("Elementary", "Grade 1", 1),
    "G3":  ("Elementary", "Grade 3", 3),
    "G6":  ("Elementary", "Grade 6", 6),
    "G7":  ("Middle",     "Grade 7", 7),
    "G9-A":("Middle",     "Grade 9", 9),
    "G9-B":("Middle",     "Grade 9", 9),   # same grade, second class
    "G10": ("High",       "Grade 10", 10),
    "G11": ("High",       "Grade 11", 11),
    "G12": ("High",       "Grade 12", 12),
}
_CLASS_NAMES = {
    "G1":  "1-A", "G3":  "3-A", "G6":  "6-A", "G7":  "7-A",
    "G9-A": "9-A", "G9-B": "9-B",
    "G10": "10-A", "G11": "11-A", "G12": "12-A",
}

# Teacher pool (email-local, full name). Homeroom assignments below.
_TEACHERS: list[tuple[str, str]] = [
    ("rivera",   "Ms. Rivera"),        # 9-A homeroom + math middle
    ("chen",     "Mr. Chen"),           # 9-B homeroom + science
    ("okonkwo",  "Ms. Okonkwo"),        # english middle + dept-leader
    ("hassan",   "Mr. Hassan"),         # 7-A homeroom + geography/history
    ("morales",  "Ms. Morales"),        # languages middle + dept-leader
    ("bianchi",  "Ms. Bianchi"),        # 10-A homeroom + math high + dept-leader
    ("kaur",     "Mrs. Kaur"),          # 11-A homeroom + english high
    ("tanaka",   "Mr. Tanaka"),         # 12-A homeroom + science high + dept-leader
    ("perez",    "Ms. Perez"),          # elementary generalist (G6)
    ("brooks",   "Mr. Brooks"),         # elementary generalist (G3)
    ("nasser",   "Ms. Nasser"),         # elementary generalist (G1) + arts
    ("laurent",  "Mr. Laurent"),        # PE all grades
]

# key -> teacher email-local for homeroom
_HOMEROOMS: dict[str, str] = {
    "G1":   "nasser",
    "G3":   "brooks",
    "G6":   "perez",
    "G7":   "hassan",
    "G9-A": "rivera",
    "G9-B": "chen",
    "G10":  "bianchi",
    "G11":  "kaur",
    "G12":  "tanaka",
}


# Course spec = (title, category, elective_group|None, teacher_email_local).
# Teacher is the SAME across every class at that grade (small school demo);
# admin can rebalance from the UI.
_COURSES_BY_GRADE: dict[str, list[tuple[str, str, str | None, str]]] = {
    "G1": [
        ("Reading & Writing 1", "english",  None, "nasser"),
        ("Arithmetic 1",        "math",     None, "nasser"),
        ("Discovery Science 1", "science",  None, "nasser"),
        ("Art & Music 1",       "arts",     None, "nasser"),
        ("Movement 1",          "pe",       None, "laurent"),
    ],
    "G3": [
        ("Reading & Writing 3", "english",  None, "brooks"),
        ("Arithmetic 3",        "math",     None, "brooks"),
        ("Discovery Science 3", "science",  None, "brooks"),
        ("Art & Music 3",       "arts",     None, "nasser"),
        ("Movement 3",          "pe",       None, "laurent"),
    ],
    "G6": [
        ("English 6",           "english",  None, "perez"),
        ("Pre-algebra",         "math",     None, "perez"),
        ("Science 6",           "science",  None, "perez"),
        ("World Cultures 6",    "social_studies", None, "hassan"),
        ("Physical Education 6","pe",       None, "laurent"),
    ],
    "G7": [
        ("English 7",           "english",  None, "okonkwo"),
        ("Algebra Foundations", "math",     None, "rivera"),
        ("Life Science",        "science",  None, "chen"),
        ("Geography 7",         "social_studies", None, "hassan"),
        ("PE 7",                "pe",       None, "laurent"),
        ("French I (7)",        "languages","language", "morales"),
        ("Spanish I (7)",       "languages","language", "morales"),
    ],
    # Both 9-A and 9-B share the same Grade 9 curriculum.
    "G9-A": [
        ("English 9",           "english",  None, "okonkwo"),
        ("Algebra 1",           "math",     None, "rivera"),
        ("Biology",             "science",  None, "chen"),
        ("World History",       "social_studies", None, "hassan"),
        ("PE 9",                "pe",       None, "laurent"),
        ("French I",            "languages","language", "morales"),
        ("German I",            "languages","language", "morales"),
        ("Spanish I",           "languages","language", "morales"),
    ],
    "G9-B": [],  # inherits from G9-A (same grade shares curriculum)
    "G10": [
        ("English 10",          "english",  None, "kaur"),
        ("Geometry",            "math",     None, "bianchi"),
        ("Chemistry",           "science",  None, "tanaka"),
        ("Modern History",      "social_studies", None, "hassan"),
        ("PE 10",               "pe",       None, "laurent"),
        ("French II",           "languages","language", "morales"),
        ("German II",           "languages","language", "morales"),
    ],
    "G11": [
        ("English 11",          "english",  None, "kaur"),
        ("Algebra 2",           "math",     None, "bianchi"),
        ("Physics 11",          "science",  None, "tanaka"),
        ("Government",          "social_studies", None, "hassan"),
        ("Astronomy",           "science",  "science_track", "tanaka"),
        ("Environmental Sci.",  "science",  "science_track", "chen"),
        ("Computer Science 1",  "computer_science", None, "bianchi"),
    ],
    "G12": [
        ("AP English",          "english",  None, "kaur"),
        ("Calculus",            "math",     None, "bianchi"),
        ("Physics 12",          "science",  None, "tanaka"),
        ("Economics",           "social_studies", None, "hassan"),
        ("Advanced CS",         "computer_science", None, "bianchi"),
    ],
}


# Student roster: dict key -> list of (email-local, full-name, archetype).
# Archetypes: top / mid_high / mid_low / at_risk. Grade 9 keeps the
# original 9-A roster from Phase 8 so existing "Amira has cert" flows survive.
_ROSTERS: dict[str, list[tuple[str, str, str]]] = {
    "G1": [
        ("liam",   "Liam O'Brien",   "top"),
        ("mia",    "Mia Chen",       "top"),
        ("sofia",  "Sofia Rossi",    "mid_high"),
        ("hamza",  "Hamza Aziz",     "mid_high"),
        ("olivia", "Olivia Johnson", "mid_high"),
        ("noah1",  "Noah Kim",       "mid_high"),
        ("emma",   "Emma Novak",     "mid_low"),
        ("aya",    "Aya Bakr",       "mid_low"),
        ("theo",   "Theo Weber",     "mid_low"),
        ("zoe",    "Zoe Marchand",   "mid_low"),
        ("kai",    "Kai Nakamura",   "mid_low"),
        ("leen",   "Leen Nabulsi",   "mid_low"),
        ("ivan",   "Ivan Krylov",    "at_risk"),
        ("nora1",  "Nora Adebayo",   "at_risk"),
    ],
    "G3": [
        ("sara3",  "Sara Kirsch",    "top"),
        ("adam3",  "Adam Zabala",    "top"),
        ("iris",   "Iris Papadaki",  "top"),
        ("dev",    "Dev Patel",      "mid_high"),
        ("mila",   "Mila Sokolova",  "mid_high"),
        ("omar3",  "Omar Hakim",     "mid_high"),
        ("chloe",  "Chloe Turner",   "mid_high"),
        ("finn",   "Finn Doyle",     "mid_low"),
        ("layla3", "Layla Nassar",   "mid_low"),
        ("jonas",  "Jonas Schwarz",  "mid_low"),
        ("aria",   "Aria Bianchi",   "mid_low"),
        ("elias3", "Elias Voss",     "mid_low"),
        ("nadia",  "Nadia Farouk",   "at_risk"),
        ("max3",   "Max Petrov",     "at_risk"),
    ],
    "G6": [
        ("hiro",   "Hiro Suzuki",    "top"),
        ("elena",  "Elena Ionescu",  "top"),
        ("yusuf",  "Yusuf Amin",     "top"),
        ("clara",  "Clara Meier",    "mid_high"),
        ("saul",   "Saul Ortega",    "mid_high"),
        ("aya6",   "Aya Sadiq",      "mid_high"),
        ("erik",   "Erik Larsen",    "mid_high"),
        ("naima",  "Naima Cissé",    "mid_high"),
        ("owen",   "Owen Rhys",      "mid_low"),
        ("dara",   "Dara Kumar",     "mid_low"),
        ("elif",   "Elif Yilmaz",    "mid_low"),
        ("jack6",  "Jack Delaney",   "mid_low"),
        ("beth",   "Bethan Price",   "at_risk"),
    ],
    "G7": [
        ("hana7",  "Hana Ali",       "top"),
        ("noor7",  "Noor Habib",     "top"),
        ("simon",  "Simon Blake",    "mid_high"),
        ("lucia",  "Lucia Ferrari",  "mid_high"),
        ("ravi7",  "Ravi Iyer",      "mid_high"),
        ("emre",   "Emre Aslan",     "mid_high"),
        ("julia7", "Julia Novak",    "mid_low"),
        ("noor2",  "Noor Karimi",    "mid_low"),
        ("felipe", "Felipe Alvarez", "mid_low"),
        ("anna7",  "Anna Kruk",      "mid_low"),
        ("samir",  "Samir Bassam",   "at_risk"),
        ("lea",    "Léa Blanchet",   "at_risk"),
    ],
    # 9-A: original Phase 8 roster preserved so "Amira has a cert" survives.
    "G9-A": [
        ("layla",    "Layla Haddad",     "top"),
        ("noor",     "Noor El-Sayed",    "top"),
        ("ethan",    "Ethan Alvarez",    "top"),
        ("yara",     "Yara Mansour",     "mid_high"),
        ("omar",     "Omar Farouk",      "mid_high"),
        ("hana",     "Hana Okafor",      "mid_high"),
        ("kaveh",    "Kaveh Rahimi",     "mid_high"),
        ("sara",     "Sara Klein",       "mid_high"),
        ("tariq",    "Tariq Nasser",     "mid_high"),
        ("maya",     "Maya Bernstein",   "mid_high"),
        ("khalid",   "Khalid Osman",     "mid_high"),
        ("rania",    "Rania Boutros",    "mid_low"),
        ("dario",    "Dario Fontana",    "mid_low"),
        ("adam",     "Adam Kowalski",    "mid_low"),
        ("zainab",   "Zainab Al-Rashid", "mid_low"),
        ("nina",     "Nina Petrov",      "mid_low"),
        ("hassan-s", "Hassan Mahmoud",   "mid_low"),
        ("elias",    "Elias Vardanyan",  "mid_low"),
        ("mira",     "Mira Solano",      "at_risk"),
        ("junaid",   "Junaid Bhatti",    "at_risk"),
        ("tessa",    "Tessa O'Connor",   "at_risk"),
        ("ravi",     "Ravi Deshmukh",    "at_risk"),
        ("aisha",    "Aisha Bello",      "at_risk"),
    ],
    # 9-B: parallel class, smaller.
    "G9-B": [
        ("miguel",   "Miguel Torres",    "top"),
        ("selin",    "Selin Demir",      "top"),
        ("henry",    "Henry Walsh",      "mid_high"),
        ("dana",     "Dana Rahal",       "mid_high"),
        ("koray",    "Koray Aksoy",      "mid_high"),
        ("aria9",    "Aria Ferraro",     "mid_high"),
        ("ivo",      "Ivo Muller",       "mid_low"),
        ("nina9",    "Nina Wojcik",      "mid_low"),
        ("kojo",     "Kojo Boateng",     "mid_low"),
        ("marta",    "Marta Silva",      "mid_low"),
        ("darius",   "Darius Petrescu",  "mid_low"),
        ("safi",     "Safi Chaudhry",    "at_risk"),
        ("juno",     "Juno Yamada",      "at_risk"),
    ],
    "G10": [
        ("isla",     "Isla Fitzpatrick", "top"),
        ("kenji",    "Kenji Ito",        "top"),
        ("amina",    "Amina Sadiq",      "top"),
        ("mateus",   "Mateus Costa",     "mid_high"),
        ("hana10",   "Hana Bekri",       "mid_high"),
        ("felix10",  "Felix Grüber",     "mid_high"),
        ("lena10",   "Lena Novotný",     "mid_high"),
        ("sami10",   "Sami Rahman",      "mid_low"),
        ("carla",    "Carla Vidal",      "mid_low"),
        ("teo",      "Teo Lindqvist",    "mid_low"),
        ("mira10",   "Mira Kapoor",      "at_risk"),
    ],
    "G11": [
        ("julian",   "Julian Perez",     "top"),
        ("rania11",  "Rania Habib",      "top"),
        ("aiden",    "Aiden Cho",        "mid_high"),
        ("ines",     "Inés García",      "mid_high"),
        ("cyrus",    "Cyrus Bakhtiar",   "mid_high"),
        ("dana11",   "Dana Kowalska",    "mid_low"),
        ("hugo",     "Hugo Fischer",     "mid_low"),
        ("nour",     "Nour Ali",         "at_risk"),
    ],
    "G12": [
        ("yara12",   "Yara Al-Sayed",    "top"),          # senior with cert
        ("beatrice", "Beatrice Romano",  "top"),
        ("marcus",   "Marcus Reyes",     "mid_high"),
        ("tomas",    "Tomas Havel",      "mid_high"),
        ("jian",     "Jian Wu",          "mid_low"),
    ],
}

# Grade 9 kept "amira" + "bilal" as separate always-there students in
# Phase 8. Preserve those.
_G9A_EXTRAS: list[tuple[str, str, str]] = [
    ("amira", "Amira Al-Farsi", "top"),
    ("bilal", "Bilal Karim",    "at_risk"),
]


# =============================================================================
# Orchestrators
# =============================================================================
def _seed_school_hierarchy() -> tuple[
    dict[str, Section], dict[str, Grade], dict[str, SchoolClass],
]:
    """Sections + grades + classes. Homeroom assignments require teachers,
    which are seeded first — but we register empty homeroom here and
    backfill in `_seed_all_teachers`."""
    sections: dict[str, Section] = {}
    for name, order in [("Elementary", 0), ("Middle", 1), ("High", 2)]:
        sections[name] = _upsert_section(name, order)

    grades: dict[str, Grade] = {}
    classes: dict[str, SchoolClass] = {}
    # Distinct grade rows (Grade 9 shared by 9-A + 9-B — same grade row).
    grade_row_by_name: dict[str, Grade] = {}
    for key in _GRADE_KEYS:
        section_name, grade_name, order = _GRADE_META[key]
        if grade_name not in grade_row_by_name:
            grade_row_by_name[grade_name] = _upsert_grade(
                grade_name, sections[section_name], order)
        grades[key] = grade_row_by_name[grade_name]
        # Class row (no homeroom yet — filled in by `_wire_homerooms`).
        classes[key] = _upsert_class(_CLASS_NAMES[key], grades[key], None)
    return sections, grades, classes


def _seed_all_teachers() -> dict[str, User]:
    teachers: dict[str, User] = {}
    for local, name in _TEACHERS:
        teachers[local] = _upsert_user(
            f"{local}@school.local", name, "instructor", "teacher1")
    return teachers


def _wire_homerooms(
    classes: dict[str, SchoolClass], teachers: dict[str, User],
) -> None:
    for key, cls in classes.items():
        teacher = teachers.get(_HOMEROOMS[key])
        if teacher is None:
            continue
        if cls.homeroom_teacher_id != teacher.id:
            cls.homeroom_teacher_id = teacher.id
    db.session.commit()


def _seed_all_curricula(
    grades: dict[str, Grade], teachers: dict[str, User],
    cats: dict[str, GradeCategory],
) -> dict[str, list[Course]]:
    """Courses per grade (one row per Grade — 9-A/9-B share). Rubric on each."""
    by_key: dict[str, list[Course]] = {}
    seen_grade_ids: set[str] = set()
    for key in _GRADE_KEYS:
        specs = _COURSES_BY_GRADE.get(key)
        if not specs:
            # 9-B inherits 9-A's curriculum — copy references.
            if key == "G9-B":
                by_key[key] = list(by_key["G9-A"])
                continue
            by_key[key] = []
            continue
        grade = grades[key]
        if grade.id in seen_grade_ids:
            # Already created for this Grade row.
            by_key[key] = [
                c for c in Course.query.filter_by(grade_id=grade.id).all()
            ]
            continue
        seen_grade_ids.add(grade.id)
        courses: list[Course] = []
        for title, category, elective_group, _teacher_local in specs:
            desc = _COURSE_DESCRIPTIONS.get(title, "")
            c = _upsert_course(
                title=title, grade=grade, category=category,
                elective_group=elective_group, description=desc)
            _seed_rubric(c, cats)
            courses.append(c)
        by_key[key] = courses
    return by_key


def _assign_all_class_course_teachers(
    classes: dict[str, SchoolClass],
    curricula: dict[str, list[Course]],
    teachers: dict[str, User],
) -> None:
    for key, cls in classes.items():
        # For 9-B, use 9-A's teacher assignments (shared curriculum, same faculty).
        source_key = "G9-A" if key == "G9-B" else key
        specs = _COURSES_BY_GRADE.get(source_key, [])
        for title, _cat, _eg, teacher_local in specs:
            course = next(
                (c for c in curricula[key] if c.title == title), None)
            if course is None:
                continue
            teacher = teachers.get(teacher_local)
            if teacher is not None:
                _assign_class_course_teacher(course, cls, teacher)


def _seed_dept_leaders(
    sections: dict[str, Section], teachers: dict[str, User], admin: User,
) -> None:
    """4 dept-leader slots demonstrated: math × High (bianchi),
    science × High (tanaka), english × Middle (okonkwo),
    languages × Middle (morales)."""
    slots = [
        ("math",     "High",   "bianchi"),
        ("science",  "High",   "tanaka"),
        ("english",  "Middle", "okonkwo"),
        ("languages","Middle", "morales"),
    ]
    for dept, section_name, teacher_local in slots:
        teacher = teachers.get(teacher_local)
        section = sections.get(section_name)
        if teacher is None or section is None:
            continue
        existing = DepartmentLeader.query.filter_by(
            department=dept, section_id=section.id).first()
        if existing is None:
            db.session.add(DepartmentLeader(
                department=dept, section_id=section.id,
                teacher_id=teacher.id, assigned_by_id=admin.id))
    db.session.commit()


# ---- Course descriptions (used at course creation) ---------------------------
_COURSE_DESCRIPTIONS: dict[str, str] = {
    "English 9": "English 9 introduces close reading of literary fiction, thesis-driven writing, and grammar review. Students read one novel per unit, write two essays per term, and practice oral response.",
    "Algebra 1": "Foundational algebra: variables, linear equations, factoring, systems of equations, and quadratic functions. Emphasis on symbolic manipulation and word-problem translation.",
    "Biology": "Introduction to life sciences: cell biology, genetics, ecology, and human physiology. Weekly labs where lab-availability permits.",
    "World History": "A survey from ancient civilizations to the modern era. Focus on primary sources and historical argument.",
    "PE 9": "Physical education for Grade 9. Individual + team activities, fitness benchmarks, sports skills.",
    "French I": "Introduction to French: pronunciation, present tense verbs, everyday vocabulary, basic conversation.",
    "German I": "Introduction to German: alphabet, present tense, cases nominative + accusative, everyday phrases.",
    "Spanish I": "Introduction to Spanish: sounds, present tense, ser/estar, everyday conversation.",
    "Algebra 2": "Advanced algebra: functions, logarithms, trigonometry basics, sequences and series, complex numbers.",
    "Geometry": "Euclidean geometry, proofs, congruence and similarity, area, volume, coordinate geometry.",
    "Chemistry": "Matter and energy, atomic structure, chemical bonding, reactions, stoichiometry, acids and bases.",
    "Physics 11": "Kinematics, forces, energy, waves, and electricity. Weekly problem sets.",
    "Physics 12": "Continuation of Physics 11: electromagnetism, modern physics, applied problems.",
    "Calculus": "Limits, derivatives, integrals, and applications to real-world problems. Preparation for university-level calculus.",
    "AP English": "Advanced composition, literary analysis, and rhetorical strategies. AP exam preparation in the spring term.",
    "Advanced CS": "Data structures, algorithms, project-based programming in Python and JavaScript.",
    "Computer Science 1": "Introduction to programming: variables, control flow, functions, basic data structures. Uses Python.",
}


# ---- Student placement + auto-enrollment ------------------------------------
def _seed_students_across_classes(
    classes: dict[str, SchoolClass],
) -> dict[str, list[User]]:
    """Create every student user + place them (auto-enrolls mandatory)."""
    students_by_key: dict[str, list[User]] = {k: [] for k in _GRADE_KEYS}
    for key in _GRADE_KEYS:
        cls = classes[key]
        entries = list(_ROSTERS.get(key, []))
        if key == "G9-A":
            entries = _G9A_EXTRAS + entries
        for local, name, _archetype in entries:
            u = _upsert_user(
                f"{local}@school.local", name, "student", "student1")
            _place_student_in_class(u, cls)
            students_by_key[key].append(u)
    return students_by_key


def _archetype_of(student: User) -> str:
    """Lookup — archetype per student stays constant across seeds."""
    local = student.email.split("@")[0]
    for _key, roster in _ROSTERS.items():
        for l, _n, arch in roster:
            if l == local:
                return arch
    for l, _n, arch in _G9A_EXTRAS:
        if l == local:
            return arch
    return "mid_high"


def _pick_electives_for(student: User, admin: User, rnd: random.Random) -> None:
    """For each elective group in the student's grade, assign the first
    option. Idempotent."""
    if student.class_id is None:
        return
    sc = db.session.get(SchoolClass, student.class_id)
    if sc is None:
        return
    grade_id = sc.grade_id
    # Every distinct elective_group in the grade's curriculum.
    groups: set[str] = set()
    for c in Course.query.filter_by(grade_id=grade_id).all():
        if c.elective_group:
            groups.add(c.elective_group)
    for group in groups:
        # Existing pick?
        picked = (
            db.session.query(Enrollment)
            .join(Course, Course.id == Enrollment.course_id)
            .filter(
                Enrollment.student_id == student.id,
                Enrollment.status == "active",
                Course.elective_group == group,
                Course.grade_id == grade_id,
            )
            .first()
        )
        if picked is not None:
            continue
        options = Course.query.filter_by(
            grade_id=grade_id, elective_group=group,
        ).order_by(Course.title).all()
        if not options:
            continue
        chosen = rnd.choice(options)
        db.session.add(Enrollment(
            student_id=student.id, course_id=chosen.id,
            status="active", enrolled_via="elective_choice",
            enrolled_by_id=admin.id,
        ))
    db.session.commit()


# ---- Course content: modules + lessons per mandatory course -----------------
_MODULE_TEMPLATES = [
    ("Unit 1: Foundations",  ["Introduction & syllabus", "Core concepts", "Terminology", "Practice set A", "Practice set B", "Formative check"]),
    ("Unit 2: Applications", ["Real-world contexts", "Case study", "Skill drill", "Group activity", "Formative check"]),
    ("Unit 3: Deeper Dive",  ["Advanced concepts", "Extended reading", "Applied project", "Formative check"]),
    ("Unit 4: Review",       ["Consolidation", "Practice exam", "Reflection & goals"]),
]


def _seed_course_content_deep(course: Course, rnd: random.Random) -> None:
    """3-4 modules per course, 4-6 lessons each. Idempotent — the check is
    against the module count so re-runs skip. Mostly text lessons with real
    markdown content; one PDF placeholder and one video placeholder per
    course so admins can test the mixed-media flow.
    """
    if course.modules.count() > 1:
        return  # already deep-seeded

    # Wipe the single seed module if it's still there.
    for m in course.modules.all():
        db.session.delete(m)
    db.session.commit()

    for i, (title, lesson_titles) in enumerate(_MODULE_TEMPLATES):
        m = Module(course_id=course.id, title=title, order_index=i)
        db.session.add(m)
        db.session.commit()
        for j, ltitle in enumerate(lesson_titles):
            lesson_type = "text"
            content_url = None
            if j == len(lesson_titles) - 1 and i == 0:
                # One PDF placeholder in the first module's last lesson.
                lesson_type = "pdf"
                content_url = ""  # empty URL — admin uploads later
            elif j == 0 and i == 1:
                # One video placeholder in Module 2's first lesson.
                lesson_type = "video"
                content_url = ""
            db.session.add(Lesson(
                module_id=m.id,
                title=ltitle,
                type=lesson_type,
                content_text=(_lesson_body(course.title, title, ltitle)
                              if lesson_type == "text" else None),
                content_url=content_url,
                duration_minutes=rnd.choice([15, 20, 25, 30, 45]),
                order_index=j,
            ))
        db.session.commit()


def _lesson_body(course_title: str, module_title: str, lesson_title: str) -> str:
    return f"""# {lesson_title}

_{course_title} · {module_title}_

## Overview

This lesson covers the core ideas of **{lesson_title.lower()}** in the
context of {module_title.lower()}. By the end you should be able to
describe the main concept, work through one worked example, and answer
the formative question at the bottom.

## Key ideas

- First idea — briefly explain
- Second idea — how it connects to the first
- Third idea — the exception worth knowing

## Worked example

> A short worked example lives here in a real deployment. For the demo,
> imagine the teacher has typed a problem, walked through the solution
> step by step, and provided a hint for the trickier step.

## Try it yourself

- Question 1: ...
- Question 2: ...
- Question 3: ...

## Recap

- Core concept: ✓
- Applied example: ✓
- Practice: three items above

_(Auto-seeded lesson body. Edit or replace via the course editor.)_
"""


# ---- Progress + grades per archetype ----------------------------------------
def _grade_targets(archetype: str, rnd: random.Random) -> dict[str, int]:
    """Concrete per-category scores for one enrollment. Cats sum to 100."""
    caps = {
        "commitment": 15, "class_projects": 5, "participation": 10,
        "class_work": 10, "assignments": 10, "subject_projects": 5,
        "final_exam": 40,
    }
    target = {
        "top": rnd.uniform(90, 98),
        "mid_high": rnd.uniform(78, 88),
        "mid_low": rnd.uniform(65, 77),
        "at_risk": rnd.uniform(45, 58),
    }[archetype]
    frac = target / 100.0
    out: dict[str, int] = {}
    for slug, cap in caps.items():
        jitter = rnd.uniform(-0.10, 0.10) * cap
        out[slug] = max(0, min(cap, int(round(cap * frac + jitter))))
    return out


def _progress_target(archetype: str, rnd: random.Random) -> float:
    return {
        "top": 1.00,
        "mid_high": rnd.uniform(0.60, 0.90),
        "mid_low": rnd.uniform(0.30, 0.55),
        "at_risk": rnd.uniform(0.00, 0.20),
    }[archetype]


def _seed_all_progress_grades(
    students_by_key: dict[str, list[User]],
    curricula: dict[str, list[Course]],
    q1: Term, cats: dict[str, GradeCategory],
    rnd: random.Random,
) -> None:
    for key, students in students_by_key.items():
        for stu in students:
            arch = _archetype_of(stu)
            for course in curricula[key]:
                enrollment = Enrollment.query.filter_by(
                    student_id=stu.id, course_id=course.id).first()
                if enrollment is None:
                    continue

                # Progress via lesson completions.
                for module in course.modules.all():
                    lessons = list(module.lessons.order_by(Lesson.order_index).all())
                    target_frac = _progress_target(arch, rnd)
                    target_count = round(len(lessons) * target_frac)
                    for i, lesson in enumerate(lessons):
                        if i >= target_count:
                            break
                        if LessonProgress.query.filter_by(
                            enrollment_id=enrollment.id, lesson_id=lesson.id
                        ).first() is None:
                            db.session.add(LessonProgress(
                                enrollment_id=enrollment.id,
                                lesson_id=lesson.id, completed=True,
                                completed_at=utc_now(),
                                last_visited_at=utc_now(),
                            ))
                db.session.commit()

                # Grade entries.
                for slug, score in _grade_targets(arch, rnd).items():
                    cat = cats.get(slug)
                    if cat is None:
                        continue
                    if GradeEntry.query.filter_by(
                        enrollment_id=enrollment.id,
                        grade_category_id=cat.id, term_id=q1.id,
                    ).first() is None:
                        db.session.add(GradeEntry(
                            enrollment_id=enrollment.id,
                            grade_category_id=cat.id, term_id=q1.id,
                            score=score,
                        ))
                db.session.commit()


# ---- Quizzes -----------------------------------------------------------------
def _seed_all_quizzes(
    curricula: dict[str, list[Course]],
    students_by_key: dict[str, list[User]],
    admin: User, rnd: random.Random,
) -> tuple[int, int]:
    """Two quizzes per mandatory course. Q1 = 5 mc_single; Q2 = mixed
    (mc_multi + true_false + short_answer). Attempts scripted per archetype."""
    quizzes_added = 0
    attempts_added = 0
    seen_courses: set[str] = set()
    for key, courses in curricula.items():
        students = students_by_key.get(key, [])
        for course in courses:
            if course.id in seen_courses:
                continue
            seen_courses.add(course.id)
            if course.elective_group is not None:
                continue  # electives keep it simple — no quizzes
            module = course.modules.order_by(Module.order_index).first()
            if module is None:
                continue
            q1 = _make_quiz_mc(module, admin, title=f"{course.title} — Quiz 1", n=5)
            q2 = _make_quiz_mixed(module, admin, title=f"{course.title} — Quiz 2")
            quizzes_added += (int(bool(q1)) + int(bool(q2)))
            for quiz in filter(None, [q1, q2]):
                for stu in students:
                    enrollment = Enrollment.query.filter_by(
                        student_id=stu.id, course_id=course.id).first()
                    if enrollment is None:
                        continue
                    arch = _archetype_of(stu)
                    if arch == "at_risk":
                        continue  # no attempt at all
                    passed = arch in ("top", "mid_high")
                    if QuizAttempt.query.filter_by(
                        quiz_id=quiz.id, student_id=stu.id).count() > 0:
                        continue
                    _script_attempt(quiz, stu, enrollment, passed=passed,
                                    attempt_number=1)
                    attempts_added += 1
            db.session.commit()
    return quizzes_added, attempts_added


def _make_quiz_mc(module: Module, admin: User, *, title: str, n: int) -> Quiz | None:
    if Quiz.query.filter_by(module_id=module.id, title=title).first():
        return Quiz.query.filter_by(module_id=module.id, title=title).first()
    q = Quiz(
        module_id=module.id, title=title,
        description="Auto-seeded practice quiz. 60% to pass.",
        passing_score=60, is_published=True, created_by_id=admin.id,
    )
    db.session.add(q)
    db.session.commit()
    for i in range(n):
        qq = QuizQuestion(
            quiz_id=q.id, order_index=i, type="mc_single",
            prompt=f"Question {i+1}: which is the correct choice?",
            points=1, required=True,
        )
        db.session.add(qq)
        db.session.commit()
        for j, letter in enumerate(["A", "B", "C", "D"]):
            db.session.add(QuizOption(
                question_id=qq.id, order_index=j,
                text=f"Option {letter}", is_correct=(j == 0),
            ))
    db.session.commit()
    return q


def _make_quiz_mixed(module: Module, admin: User, *, title: str) -> Quiz | None:
    if Quiz.query.filter_by(module_id=module.id, title=title).first():
        return Quiz.query.filter_by(module_id=module.id, title=title).first()
    q = Quiz(
        module_id=module.id, title=title,
        description="Auto-seeded mixed-format quiz. 60% to pass.",
        passing_score=60, is_published=True, created_by_id=admin.id,
    )
    db.session.add(q)
    db.session.commit()
    # 2 mc_multi
    for i in range(2):
        qq = QuizQuestion(
            quiz_id=q.id, order_index=i, type="mc_multi",
            prompt=f"Multi-select Q{i+1}: pick every applicable option.",
            points=2, required=True,
        )
        db.session.add(qq)
        db.session.commit()
        for j, (label, is_c) in enumerate([
            ("Option A", True), ("Option B", False),
            ("Option C", True), ("Option D", False),
        ]):
            db.session.add(QuizOption(
                question_id=qq.id, order_index=j, text=label, is_correct=is_c))
    # 2 true_false
    for i in range(2):
        qq = QuizQuestion(
            quiz_id=q.id, order_index=2 + i, type="true_false",
            prompt=f"True/False Q{i+1}: this statement is true.",
            points=1, required=True,
        )
        db.session.add(qq)
        db.session.commit()
        db.session.add(QuizOption(
            question_id=qq.id, order_index=0, text="True", is_correct=True))
        db.session.add(QuizOption(
            question_id=qq.id, order_index=1, text="False", is_correct=False))
    # 1 short_answer
    qq = QuizQuestion(
        quiz_id=q.id, order_index=4, type="short_answer",
        prompt="Short answer: name one key concept.",
        points=1, required=False,
    )
    db.session.add(qq)
    db.session.commit()
    return q


def _script_attempt(
    quiz: Quiz, student: User, enrollment: Enrollment,
    *, passed: bool, attempt_number: int,
) -> None:
    max_score = Decimal(str(quiz.total_points() or 0))
    final = max_score * (Decimal("0.85") if passed else Decimal("0.35"))
    final = final.quantize(Decimal("0.01"))
    now = utc_now()
    db.session.add(QuizAttempt(
        quiz_id=quiz.id, student_id=student.id, enrollment_id=enrollment.id,
        started_at=now - timedelta(minutes=6),
        submitted_at=now - timedelta(minutes=5),
        attempt_number=attempt_number,
        auto_score=final, final_score=final, max_score=max_score,
        passed=passed, needs_manual_review=False,
    ))


# ---- Assignments -------------------------------------------------------------
def _seed_all_assignments(
    curricula: dict[str, list[Course]],
    students_by_key: dict[str, list[User]],
    admin: User, q1: Term, rnd: random.Random,
) -> tuple[int, int, int]:
    """Three assignments per mandatory course:
      A1 — past-due, all graded
      A2 — current (due in 3 days), 60% submitted (30% graded)
      A3 — future (due in 10 days), 0% submitted
    """
    now = utc_now()
    a_added = s_added = g_added = 0
    seen_courses: set[str] = set()
    for key, courses in curricula.items():
        students = students_by_key.get(key, [])
        for course in courses:
            if course.id in seen_courses:
                continue
            seen_courses.add(course.id)
            if course.elective_group is not None:
                continue
            module = course.modules.order_by(Module.order_index).first()
            if module is None:
                continue

            specs = [
                ("A1: Reflection essay",  now - timedelta(days=7),  1.00, 1.00),   # 100% submitted, 100% graded
                ("A2: Applied problem",   now + timedelta(days=3),  0.60, 0.50),   # 60% submitted, of which 50% graded
                ("A3: Final project",     now + timedelta(days=10), 0.00, 0.00),   # 0% submitted
            ]
            for title, due, submit_frac, grade_frac in specs:
                assn_title = f"{title} — {course.title}"
                if Assignment.query.filter_by(
                    module_id=module.id, title=assn_title).first() is not None:
                    continue
                a = Assignment(
                    module_id=module.id, title=assn_title,
                    description="Write a 200-word reflection or upload a PDF.",
                    due_at=due, max_points=100,
                    allow_text=True, allow_file=True,
                    is_published=True, created_by_id=admin.id,
                )
                db.session.add(a)
                db.session.commit()
                a_added += 1

                for stu in students:
                    if rnd.random() > submit_frac:
                        continue  # this student didn't submit
                    enrollment = Enrollment.query.filter_by(
                        student_id=stu.id, course_id=course.id).first()
                    if enrollment is None:
                        continue
                    sub_at = due - timedelta(hours=rnd.randint(1, 48))
                    is_late = sub_at > (a.due_at or sub_at)
                    sub = AssignmentSubmission(
                        assignment_id=a.id, student_id=stu.id,
                        enrollment_id=enrollment.id,
                        submitted_at=sub_at, is_late=is_late,
                        response_text=f"[Seeded submission by {stu.name}.]",
                    )
                    if rnd.random() < grade_frac:
                        arch = _archetype_of(stu)
                        base = {
                            "top": rnd.uniform(85, 100),
                            "mid_high": rnd.uniform(72, 88),
                            "mid_low": rnd.uniform(60, 75),
                            "at_risk": rnd.uniform(35, 55),
                        }[arch]
                        sub.graded_score = Decimal(str(round(base, 2)))
                        sub.graded_max = Decimal("100")
                        sub.graded_feedback = "Auto-seeded feedback."
                        sub.graded_by_id = admin.id
                        sub.graded_at = sub_at + timedelta(hours=6)
                        g_added += 1
                    db.session.add(sub)
                    s_added += 1
                db.session.commit()
    return a_added, s_added, g_added


# ---- Attendance -------------------------------------------------------------
def _seed_all_attendance(
    classes: dict[str, SchoolClass],
    teachers: dict[str, User],
    rnd: random.Random, days: int = 60,
) -> int:
    """60 school days of attendance across every class. Same 92/4/3/1
    distribution as Phase 12. One student per class gets a chronic-absentee
    rate so the at-risk list has content."""
    today = _date.today()
    school_days: list[_date] = []
    d = today
    while len(school_days) < days:
        if d.weekday() < 5:
            school_days.append(d)
        d -= timedelta(days=1)

    written = 0
    for key, cls in classes.items():
        homeroom = teachers.get(_HOMEROOMS[key])
        students = list(cls.students.all())
        if not students or homeroom is None:
            continue
        chronic_id = students[min(2, len(students) - 1)].id
        for day in school_days:
            for stu in students:
                if AttendanceMark.query.filter_by(
                    student_id=stu.id, date=day).first() is not None:
                    continue
                roll = rnd.random()
                if stu.id == chronic_id:
                    status = ("absent" if roll < 0.20 else
                              "late" if roll < 0.25 else
                              "excused" if roll < 0.28 else "present")
                else:
                    status = ("absent" if roll < 0.04 else
                              "late" if roll < 0.07 else
                              "excused" if roll < 0.08 else "present")
                reason = None
                if status == "excused":
                    reason = rnd.choice([
                        "Doctor's appointment", "Family event", "Illness"])
                elif status == "late":
                    reason = rnd.choice(["Bus late", "Traffic", None])
                db.session.add(AttendanceMark(
                    student_id=stu.id, class_id=cls.id, date=day,
                    status=status, reason=reason,
                    marked_by_id=homeroom.id,
                ))
                written += 1
        db.session.commit()
    return written


# ---- Timetables ------------------------------------------------------------
def _seed_all_timetables(
    classes: dict[str, SchoolClass],
    curricula: dict[str, list[Course]],
    rnd: random.Random,
) -> tuple[int, int]:
    """One 5×5 weekly schedule per class. Rotates the class's mandatory
    courses; if the class has fewer than 5 mandatory courses, the schedule
    repeats them. One custom override per class next week (assembly)."""
    slots = [
        (_time(9, 0),  _time(9, 45)),
        (_time(9, 50), _time(10, 35)),
        (_time(10, 40), _time(11, 25)),
        (_time(11, 30), _time(12, 15)),
        (_time(13, 0), _time(13, 45)),
    ]
    periods_added = 0
    overrides_added = 0
    for key, cls in classes.items():
        if TimetablePeriod.query.filter_by(class_id=cls.id).count() > 0:
            continue
        mand = [c for c in curricula[key] if c.elective_group is None]
        if not mand:
            continue
        # Rotate mand across (5 days × 5 slots).
        idx = 0
        for day in range(5):
            for i, (st, et) in enumerate(slots):
                course = mand[idx % len(mand)]
                idx += 1
                db.session.add(TimetablePeriod(
                    class_id=cls.id, course_id=course.id,
                    day_of_week=day, start_time=st, end_time=et,
                    room=cls.name, order_index=i,
                ))
                periods_added += 1
        db.session.commit()

        # Custom override: next Friday's period 1 → assembly.
        today = _date.today()
        days_to_fri = (4 - today.weekday()) % 7 or 7
        next_fri = today + timedelta(days=days_to_fri)
        if TimetableOverride.query.filter_by(
            class_id=cls.id, date=next_fri, kind="custom").first() is None:
            db.session.add(TimetableOverride(
                class_id=cls.id, date=next_fri, kind="custom",
                start_time=_time(9, 0), end_time=_time(9, 45),
                room="Auditorium", note="All-school assembly",
            ))
            overrides_added += 1
        db.session.commit()
    return periods_added, overrides_added


# ---- Parents + links --------------------------------------------------------
def _seed_all_parent_links(admin: User) -> tuple[int, int]:
    def _p(email: str, name: str) -> User:
        return _upsert_user(email, name, "parent", "parent12")

    fatima = _p("parent@school.local", "Fatima Al-Farsi")
    karim = _p("parent2@school.local", "Karim Haddad")
    aisha_p = _p("parent3@school.local", "Aisha Chen")           # G3 + G9
    yara_p = _p("parent4@school.local", "Yasmin Al-Sayed")       # G12 senior
    sami_p = _p("parent5@school.local", "Sami Bakr")             # split guardianship w/ Fatima

    def link(parent: User, student_email: str, rel: str = "guardian") -> int:
        stu = User.query.filter_by(email=student_email).first()
        if stu is None:
            return 0
        if ParentStudentLink.query.filter_by(
            parent_id=parent.id, student_id=stu.id).first() is not None:
            return 0
        db.session.add(ParentStudentLink(
            parent_id=parent.id, student_id=stu.id, relationship_type=rel))
        return 1

    added_links = 0
    added_links += link(fatima, "amira@school.local")
    added_links += link(fatima, "bilal@school.local")
    added_links += link(karim, "layla@school.local")
    added_links += link(aisha_p, "mia@school.local", "guardian")           # G1 in reality — G3-adjacent
    added_links += link(aisha_p, "hana@school.local", "guardian")          # 9-A student
    added_links += link(yara_p, "yara12@school.local", "guardian")         # G12
    added_links += link(sami_p, "bilal@school.local", "parent")            # co-parent of Bilal
    db.session.commit()
    return 5, added_links


# ---- Final cascade — run rollups + cert gate on every enrollment ------------
def _final_cascade(q1: Term) -> None:
    from utils.attendance import roll_up_to_commitment
    from utils.assignments import roll_up_assignment_category
    from utils.certificates import maybe_issue_certificate
    from utils.grading import recompute_enrollment_cache, recompute_progress_percent
    from utils.quizzes import roll_up_quiz_category

    students = User.query.filter_by(role="student", is_active=True).all()
    for stu in students:
        roll_up_to_commitment(stu, q1.id)
        for e in Enrollment.query.filter_by(student_id=stu.id).filter(
            Enrollment.status.in_(("active", "completed"))
        ).all():
            recompute_progress_percent(e)
            roll_up_quiz_category(e, term_id=q1.id)
            roll_up_assignment_category(e, term_id=q1.id)
            recompute_enrollment_cache(e, term_id=q1.id)
            maybe_issue_certificate(e)
    db.session.commit()


# =============================================================================
# main — orchestrates the whole seed
# =============================================================================
# =============================================================================
# Phase 27 · seed a handful of video-lesson checkpoints
# =============================================================================
def _seed_video_checkpoints(rnd: random.Random) -> int:
    """Pick every video lesson in the seeded content and tack on one or
    two "pause the video and answer" checkpoints. Idempotent — we skip
    any lesson that already has ≥1 checkpoint.
    """
    import json
    added = 0
    video_lessons = Lesson.query.filter_by(type="video").all()
    for lesson in video_lessons:
        if VideoCheckpoint.query.filter_by(lesson_id=lesson.id).count() > 0:
            continue
        # Two checkpoints per video: one near the start, one near the middle.
        for pos in (45, 180):
            opts = [
                {"id": "a", "text": "The main concept just shown"},
                {"id": "b", "text": "A completely unrelated topic"},
                {"id": "c", "text": "Something from last week"},
            ]
            cp = VideoCheckpoint(
                lesson_id=lesson.id,
                position_seconds=pos,
                prompt=f"What did the video just cover at {pos // 60}m?",
                correct_option_id="a",
                options_json=json.dumps(opts),
            )
            db.session.add(cp)
            added += 1
    db.session.commit()
    return added


# =============================================================================
# Phase 27 · seed one group assignment per course + join a couple of students
# =============================================================================
def _seed_group_assignments(
    students_by_key: dict[str, list[User]],
    admin: User,
    rnd: random.Random,
) -> tuple[int, int]:
    """Convert one assignment per course to `is_group=True` (max size 3)
    and wire two-student groups where enough students exist. Idempotent:
    skip if a group already exists for that assignment.

    Returns (assignments_flipped, groups_created).
    """
    flipped = 0
    groups_created = 0
    # One assignment per course — the first published one.
    for course in Course.query.filter_by(status="published").all():
        assignment = (
            Assignment.query
            .join(Module, Module.id == Assignment.module_id)
            .filter(Module.course_id == course.id,
                    Assignment.is_published.is_(True))
            .first()
        )
        if assignment is None or assignment.is_group:
            continue
        assignment.is_group = True
        assignment.max_group_size = 3
        flipped += 1
        # Pair two students who are enrolled in this course.
        enrolled = (
            Enrollment.query.filter_by(
                course_id=course.id, status="active",
            ).limit(2).all()
        )
        if len(enrolled) >= 2:
            existing = AssignmentGroup.query.filter_by(
                assignment_id=assignment.id,
            ).first()
            if existing is None:
                grp = AssignmentGroup(
                    assignment_id=assignment.id,
                    name=f"Team {course.title[:20]}",
                    created_by_id=enrolled[0].student_id,
                )
                db.session.add(grp)
                db.session.flush()
                for e in enrolled:
                    db.session.add(AssignmentGroupMember(
                        group_id=grp.id, student_id=e.student_id,
                    ))
                groups_created += 1
    db.session.commit()
    return (flipped, groups_created)


# =============================================================================
# Phase 27 · sprinkle Meet URLs onto a subset of periods
# =============================================================================
def _seed_period_meeting_urls(rnd: random.Random) -> int:
    """~30% of periods pick up a placeholder Meet URL so the Join button
    in Now/Next actually renders in the demo.
    """
    added = 0
    for period in TimetablePeriod.query.all():
        if period.meeting_url:
            continue
        if rnd.random() < 0.30:
            period.meeting_url = (
                f"https://meet.example.com/{period.class_id[:8]}-"
                f"{period.course_id[:6] if period.course_id else 'gen'}"
            )
            added += 1
    db.session.commit()
    return added


# =============================================================================
# Phase 28 · seed fees + payments per student
# =============================================================================
def _seed_fees(students_by_key: dict[str, list[User]], admin: User,
               rnd: random.Random) -> tuple[int, int]:
    """Every active student gets 2-3 fee items: term tuition, activity
    fee, one situational (uniform / trip / library fine). ~60% have at
    least one payment logged (mix of partial + full). Idempotent —
    skip if the student already has fees.
    """
    fees_added = 0
    payments_added = 0
    today = _date.today()
    for students in students_by_key.values():
        for stu in students:
            if FeeItem.query.filter_by(student_id=stu.id).count() > 0:
                continue
            # Tuition — always present, quarter-based due date.
            tuition = FeeItem(
                student_id=stu.id,
                label="Term 1 tuition",
                amount=Decimal("450.00"),
                currency="USD",
                due_date=today - timedelta(days=15),
                created_by_id=admin.id,
            )
            db.session.add(tuition)
            fees_added += 1
            # Activity fee.
            activity = FeeItem(
                student_id=stu.id,
                label="Activity fee",
                amount=Decimal("75.00"),
                currency="USD",
                due_date=today + timedelta(days=20),
                created_by_id=admin.id,
            )
            db.session.add(activity)
            fees_added += 1
            # Third fee — a situational one.
            extra_label, extra_amt = rnd.choice([
                ("Uniform", Decimal("60.00")),
                ("Field trip: Museum", Decimal("30.00")),
                ("Library fine", Decimal("5.50")),
                ("Yearbook", Decimal("40.00")),
            ])
            extra = FeeItem(
                student_id=stu.id,
                label=extra_label,
                amount=extra_amt,
                currency="USD",
                created_by_id=admin.id,
            )
            db.session.add(extra)
            fees_added += 1
            db.session.flush()

            # Payments — ~60% of students. Mix partial + full.
            roll = rnd.random()
            if roll < 0.30:
                # Full payment on tuition + activity.
                for fee in (tuition, activity):
                    db.session.add(FeePayment(
                        fee_item_id=fee.id,
                        amount=fee.amount,
                        method=rnd.choice(["cash", "card", "bank"]),
                        logged_by_id=admin.id,
                    ))
                    payments_added += 1
            elif roll < 0.60:
                # Partial payment on tuition only.
                db.session.add(FeePayment(
                    fee_item_id=tuition.id,
                    amount=Decimal("200.00"),
                    method="bank",
                    note="Partial · first installment",
                    logged_by_id=admin.id,
                ))
                payments_added += 1
    db.session.commit()
    return (fees_added, payments_added)


# =============================================================================
# Phase 28 · seed browser push subscriptions (a couple per role)
# =============================================================================
def _seed_push_subscriptions(admin: User) -> int:
    """Not a real endpoint — placeholder rows so /api/dashboard/admin's
    "N users with push" counter has something to report.
    """
    from models import PushSubscription
    added = 0
    picks = User.query.filter_by(is_active=True).limit(6).all()
    for u in picks:
        endpoint = f"https://push.example/{u.id[:12]}"
        if PushSubscription.query.filter_by(
            user_id=u.id, endpoint=endpoint,
        ).first():
            continue
        db.session.add(PushSubscription(
            user_id=u.id,
            endpoint=endpoint,
            p256dh="seedp256dh" + u.id[:8],
            auth="seedauth" + u.id[:8],
            user_agent="Seed script (demo)",
            platform="web",
        ))
        added += 1
    db.session.commit()
    return added


# =============================================================================
# Phase 32 · seed notification preferences (mostly defaults + one opt-out)
# =============================================================================
def _seed_notification_preferences(
    students_by_key: dict[str, list[User]],
) -> int:
    """Give ~20% of students a "streak_reminder: off" pref so the
    prefs screen has visible non-default state on first render.
    """
    added = 0
    for students in students_by_key.values():
        for stu in students:
            if NotificationPreference.query.filter_by(
                user_id=stu.id,
            ).count() > 0:
                continue
            # Use a deterministic hash so the same students opt out on
            # each re-seed.
            if int(stu.id[:8], 16) % 5 == 0:
                db.session.add(NotificationPreference(
                    user_id=stu.id,
                    kind="streak_reminder",
                    enabled=False,
                ))
                added += 1
    db.session.commit()
    return added


# =============================================================================
# Phase 32 · seed diplomas for the Grade-12 seniors
# =============================================================================
def _seed_diplomas(students_by_key: dict[str, list[User]]) -> int:
    """Every seeded senior (Grade 12) gets a diploma. Uses the same
    `issue_diploma` helper the graduate endpoint uses — no back-door
    diploma inserts.
    """
    from utils.diplomas import issue_diploma
    added = 0
    seniors = students_by_key.get("G12", [])
    for stu in seniors:
        # Resolve the student's Grade row so the diploma carries the
        # grade snapshot. Chase class_id → SchoolClass.grade_id.
        grade_id = None
        if stu.class_id:
            sc = db.session.get(SchoolClass, stu.class_id)
            grade_id = sc.grade_id if sc else None
        dip = issue_diploma(stu.id, grade_id=grade_id)
        if dip is not None:
            added += 1
    db.session.commit()
    # Sprinkle honors on a couple of them.
    top_seniors = seniors[:3] if seniors else []
    for i, stu in enumerate(top_seniors):
        dip = Diploma.query.filter_by(student_id=stu.id).first()
        if dip is None or dip.honors is not None:
            continue
        dip.honors = ["valedictorian", "salutatorian", "cum_laude"][i]
    db.session.commit()
    return added


# =============================================================================
# Phase 32 · seed a small curriculum-standards library + a few tags
# =============================================================================
def _seed_standards() -> tuple[int, int]:
    """Ship 6 standards across math + english + science, then tag a
    handful of lessons/quizzes/assignments so the mastery view has
    something to show.
    """
    library = [
        ("MATH.6.EE.1", "Whole-number exponents", "math",
         "Write and evaluate numerical expressions involving whole-number exponents."),
        ("MATH.7.NS.2", "Rational-number multiplication", "math",
         "Apply and extend previous understandings of multiplication and division to rational numbers."),
        ("ELA.6.RL.1", "Cite textual evidence", "english",
         "Cite textual evidence to support analysis of what the text says explicitly."),
        ("ELA.7.W.3", "Narrative writing", "english",
         "Write narratives to develop real or imagined experiences using effective technique."),
        ("SCI.6.LS.1", "Structure and function", "science",
         "All living things are made up of cells; multicellular organisms have specialized cells."),
        ("SCI.8.PS.1", "Structure of matter", "science",
         "Develop models to describe the atomic composition of simple molecules."),
    ]
    standards_added = 0
    for code, name, subject, desc in library:
        if Standard.query.filter_by(code=code).first():
            continue
        db.session.add(Standard(
            code=code, name=name, subject=subject, description=desc,
        ))
        standards_added += 1
    db.session.commit()

    # Tag content: for each standard, pick 1-2 lessons in matching-
    # subject courses + 1 quiz + 1 assignment.
    tags_added = 0
    for std in Standard.query.all():
        courses = Course.query.filter_by(category=std.subject).all()
        for c in courses[:2]:
            lesson = (
                Lesson.query.join(Module, Module.id == Lesson.module_id)
                .filter(Module.course_id == c.id)
                .first()
            )
            if lesson is not None:
                if not StandardTag.query.filter_by(
                    standard_id=std.id,
                    taggable_type="lesson",
                    taggable_id=lesson.id,
                ).first():
                    db.session.add(StandardTag(
                        standard_id=std.id,
                        taggable_type="lesson",
                        taggable_id=lesson.id,
                    ))
                    tags_added += 1
            quiz = (
                Quiz.query.join(Module, Module.id == Quiz.module_id)
                .filter(Module.course_id == c.id,
                        Quiz.is_published.is_(True))
                .first()
            )
            if quiz is not None:
                if not StandardTag.query.filter_by(
                    standard_id=std.id,
                    taggable_type="quiz",
                    taggable_id=quiz.id,
                ).first():
                    db.session.add(StandardTag(
                        standard_id=std.id,
                        taggable_type="quiz",
                        taggable_id=quiz.id,
                    ))
                    tags_added += 1
            assignment = (
                Assignment.query.join(Module, Module.id == Assignment.module_id)
                .filter(Module.course_id == c.id,
                        Assignment.is_published.is_(True))
                .first()
            )
            if assignment is not None:
                if not StandardTag.query.filter_by(
                    standard_id=std.id,
                    taggable_type="assignment",
                    taggable_id=assignment.id,
                ).first():
                    db.session.add(StandardTag(
                        standard_id=std.id,
                        taggable_type="assignment",
                        taggable_id=assignment.id,
                    ))
                    tags_added += 1
    db.session.commit()
    return (standards_added, tags_added)


def main() -> None:
    import time as _timer
    started = None
    try:
        started = _timer.perf_counter()
    except Exception:
        pass

    app = create_app()
    with app.app_context():
        rnd = random.Random(42)

        # 1. Admin (always the root user).
        admin = _upsert_user(
            "admin@school.local", "School Admin", "admin", "adminadmin")

        # 2. Teachers (idempotent).
        teachers = _seed_all_teachers()
        print(f"[1/9] Teachers ({len(teachers)}): OK")

        # 3. Sections + grades + classes.
        sections, grades, classes = _seed_school_hierarchy()
        _wire_homerooms(classes, teachers)
        print(f"[2/9] Hierarchy ({len(classes)} classes across "
              f"{len({g.id for g in grades.values()})} grades): OK")

        # 4. Grading infra + curricula.
        q1 = _seed_school_year_and_terms()
        cats = _seed_grade_categories()
        _seed_grading_scale()
        curricula = _seed_all_curricula(grades, teachers, cats)
        _assign_all_class_course_teachers(classes, curricula, teachers)
        _seed_dept_leaders(sections, teachers, admin)
        distinct_courses = {c.id for cs in curricula.values() for c in cs}
        print(f"[3/9] Curriculum ({len(distinct_courses)} courses, "
              f"grading + dept-leaders): OK")

        # 5. Students + elective picks.
        students_by_key = _seed_students_across_classes(classes)
        total_students = sum(len(v) for v in students_by_key.values())
        for _key, students in students_by_key.items():
            for stu in students:
                _pick_electives_for(stu, admin, rnd)
        print(f"[4/9] Students ({total_students} placed + electives): OK")

        # 6. Deep course content.
        for c in Course.query.all():
            if c.elective_group is None:
                _seed_course_content_deep(c, rnd)
        mand_courses = [
            c for c in Course.query.all() if c.elective_group is None]
        print(f"[5/9] Course content (mods+lessons on "
              f"{len(mand_courses)} mandatory courses): OK")

        # 7. Progress + grades.
        _seed_all_progress_grades(students_by_key, curricula, q1, cats, rnd)
        print(f"[6/9] Progress + grades: OK")

        # 8. Quizzes.
        quizzes_added, attempts_added = _seed_all_quizzes(
            curricula, students_by_key, admin, rnd)
        print(f"[7/9] Quizzes (+{quizzes_added} quizzes, "
              f"+{attempts_added} attempts): OK")

        # 9. Assignments + attendance + timetables + parents.
        a_added, s_added, g_added = _seed_all_assignments(
            curricula, students_by_key, admin, q1, rnd)
        print(f"[8/9] Assignments (+{a_added} assignments, "
              f"+{s_added} subs, {g_added} graded): OK")

        att_written = _seed_all_attendance(classes, teachers, rnd)
        periods_added, overrides_added = _seed_all_timetables(
            classes, curricula, rnd)
        parents_added, links_added = _seed_all_parent_links(admin)
        print(f"[9/9] Attendance (+{att_written}), "
              f"timetables (+{periods_added} periods / +{overrides_added} overrides), "
              f"parents ({parents_added}, +{links_added} links): OK")

        # Final cascade — makes cumulative % + certs reflect all seeded state.
        _final_cascade(q1)

        # -------------------------------------------------------------
        # Phase 27-32 additive seeds — mock data for the newer surfaces
        # so the demo shows every feature. Each helper is idempotent.
        # -------------------------------------------------------------
        cps = _seed_video_checkpoints(rnd)
        gflipped, gcreated = _seed_group_assignments(
            students_by_key, admin, rnd,
        )
        meets = _seed_period_meeting_urls(rnd)
        print(f"[+27]  Video checkpoints (+{cps}), group assignments "
              f"({gflipped} flipped / {gcreated} groups), Meet URLs (+{meets})")

        fees_n, pays_n = _seed_fees(students_by_key, admin, rnd)
        subs_n = _seed_push_subscriptions(admin)
        print(f"[+28]  Fees (+{fees_n} items / +{pays_n} payments), "
              f"push subs (+{subs_n})")

        prefs_n = _seed_notification_preferences(students_by_key)
        dip_n = _seed_diplomas(students_by_key)
        std_n, tag_n = _seed_standards()
        print(f"[+32]  Notif prefs (+{prefs_n}), diplomas (+{dip_n}), "
              f"standards (+{std_n} / +{tag_n} tags)")

    # ----- Report -----
    with app.app_context():
        total_users = User.query.count()
        total_students = User.query.filter_by(role="student", is_active=True).count()
        total_teachers = User.query.filter_by(role="instructor").count()
        total_parents = User.query.filter_by(role="parent").count()
        total_courses = Course.query.count()
        total_modules = Module.query.count()
        total_lessons = Lesson.query.count()
        total_enrollments = Enrollment.query.filter(
            Enrollment.status.in_(("active", "completed"))).count()
        total_certs = Certificate.query.filter(
            Certificate.revoked.is_(False)).count()
        total_periods = TimetablePeriod.query.count()
        total_attendance = AttendanceMark.query.count()
        total_assignments = Assignment.query.count()
        total_submissions = AssignmentSubmission.query.count()
        total_quizzes = Quiz.query.count()
        total_attempts = QuizAttempt.query.count()
        # Phase 27-32 additions.
        total_checkpoints = VideoCheckpoint.query.count()
        total_groups = AssignmentGroup.query.count()
        total_meet_periods = TimetablePeriod.query.filter(
            TimetablePeriod.meeting_url.isnot(None)).count()
        total_fees = FeeItem.query.count()
        total_payments = FeePayment.query.count()
        total_diplomas = Diploma.query.count()
        total_standards = Standard.query.count()
        total_standard_tags = StandardTag.query.count()

    elapsed = None
    try:
        elapsed = _timer.perf_counter() - started
    except Exception:
        pass

    print("\n" + "-" * 68)
    print("Manara demo school ready.")
    print("-" * 68)
    print(f"  Users        {total_users:>4}   "
          f"(1 admin · {total_teachers} teachers · "
          f"{total_students} students · {total_parents} parents)")
    print(f"  Courses      {total_courses:>4}   Modules {total_modules:>4}   "
          f"Lessons {total_lessons:>4}")
    print(f"  Enrollments  {total_enrollments:>4}   Certificates {total_certs:>4}")
    print(f"  Quizzes      {total_quizzes:>4}   Attempts {total_attempts:>4}")
    print(f"  Assignments  {total_assignments:>4}   Submissions {total_submissions:>4}")
    print(f"  Timetable periods {total_periods:>4}   "
          f"Attendance marks {total_attendance:>4}")
    print(f"  Video checkpoints {total_checkpoints:>4}   "
          f"Group assignments {total_groups:>4}   "
          f"Meet periods {total_meet_periods:>4}")
    print(f"  Fees        {total_fees:>4}   Payments {total_payments:>4}   "
          f"Diplomas {total_diplomas:>4}")
    print(f"  Standards   {total_standards:>4}   "
          f"Tags {total_standard_tags:>4}")
    if elapsed is not None:
        print(f"  Seeded in {elapsed:.1f}s.")
    print("\nOne-tap logins:")
    print("  admin    : admin@school.local     / adminadmin")
    print("  teacher  : rivera@school.local    / teacher1  (9-A homeroom)")
    print("  teacher  : bianchi@school.local   / teacher1  (10-A homeroom + math dept)")
    print("  student  : amira@school.local     / student1  (9-A, has certificate)")
    print("  student  : yara12@school.local    / student1  (Grade 12 senior)")
    print("  parent   : parent@school.local    / parent12  (Amira + Bilal)")
    print("  parent   : parent3@school.local   / parent12  (multi-grade household)")
    print("-" * 68)


if __name__ == "__main__":
    main()
