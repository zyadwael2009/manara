# LMS (Learning Management System) — Staged Build Prompt for Claude Code

## How to use this file
Paste each phase into Claude Code **one at a time**, in order. Do not start
Phase N+1 until Phase N has been reviewed and approved.

---

## Database Schema (reference — Claude Code will build this across phases)

**users**
```
id, name, email, password_hash, role (student/instructor/admin/parent), created_at
```

**parent_student_links** (a parent can be linked to one or more children)
```
id, parent_id (FK -> users.id), student_id (FK -> users.id),
relationship (father/mother/guardian), created_at
```

**courses**
```
id, title, description, instructor_id (FK -> users.id),
price (0 = free), category, thumbnail_url,
status (draft/published), created_at
```

**modules** (sections within a course, ordered)
```
id, course_id (FK), title, order_index
```

**lessons** (content within a module)
```
id, module_id (FK), title, type (video/text/pdf),
content_url or content_text, duration_minutes, order_index
```

**enrollments**
```
id, student_id (FK -> users.id), course_id (FK),
enrolled_at, progress_percent, completed_at (nullable)
```

**lesson_progress** (tracks per-lesson completion — needed for "resume where I left off")
```
id, enrollment_id (FK), lesson_id (FK),
completed (bool), completed_at, last_position_seconds (for video resume)
```

**quizzes**
```
id, module_id (FK), title, passing_score
```

**quiz_questions**
```
id, quiz_id (FK), question_text, order_index
```

**quiz_options**
```
id, question_id (FK), option_text, is_correct
```

**quiz_attempts**
```
id, enrollment_id (FK), quiz_id (FK),
score, passed (bool), attempted_at
```

**certificates**
```
id, enrollment_id (FK), certificate_number, issued_at, pdf_url
```

---

## GLOBAL RULES (paste this once at the start of the project, before Phase 1)

You are building an LMS (Learning Management System) using Flask
(backend/API) and Flutter (mobile/web frontend), following the same
conventions I already use in my other projects (ClubHub, youthscores):
Flask + SQLAlchemy, JWT auth, MySQL in production / SQLite in dev, REST API
structure, PythonAnywhere-compatible deployment.

Follow these rules for the entire project, every phase, no exceptions:

1. **Always enter Plan Mode before ANY change, no matter how small.** Before
   writing or editing a single file — even a one-line fix, a style tweak, or
   a config change — first present a clear plan: what files you will
   create/modify, what the new database models/endpoints/UI will look like,
   and what could break. Wait for my explicit approval before writing any
   actual code. "It's a small change" is never a reason to skip this.
2. **Always give a full audit summary after ANY change**, not just at the
   end of a phase. Every time you finish implementing something — even a
   small fix — tell me: what was added/changed, exactly which files were
   touched, any assumptions you made, and anything you think needs my
   review. Plan → build → audit is the loop for every single change, not
   just every phase.
3. **One phase at a time.** Do not implement future-phase features early,
   even if it seems convenient.
4. **Ask before adding new dependencies/packages** not already used in my
   other projects — especially for video/file handling or animation
   libraries.
5. **Keep the code consistent with my existing style**: clear route naming,
   docstrings on non-trivial functions, no unexplained magic numbers.
6. **Never touch enrollment, progress-tracking, or certificate-issuance
   logic silently** — these are the "trust" core of the system (a
   certificate should only be issued if the student actually completed
   everything). Always flag changes to this logic explicitly in your plan.
7. **Parent accounts are read-access-plus-content-access, not full control.**
   A parent can view their linked child's progress, marks/quiz results, and
   can also open/consume the child's enrolled course content (e.g. to see
   what they're learning) — but a parent must never be able to submit
   quizzes on the child's behalf, mark lessons complete, or modify the
   child's account. Always flag any parent-related endpoint in your plan so
   I can confirm it's read/view-only where it should be.

Confirm you understand these rules before I give you Phase 1.

---

## UI/UX & DESIGN STANDARDS (applies to every phase with a UI component)

This app needs to look and feel premium — this is a CV centerpiece, not just
a functional demo. Functionality alone is not enough; the design must be
genuinely competitive with polished commercial apps. Apply these standards
in every Flutter screen you build, from Phase 1 onward — don't leave "make
it pretty" for the end:

1. **Modern, intentional visual design** — a clear color palette and type
   system (not default Flutter Material grey), consistent spacing/padding,
   real visual hierarchy. Avoid generic/templated-looking screens.
2. **Micro-animations and transitions** — smooth page transitions, animated
   progress bars, satisfying button/tap feedback, subtle loading states
   (skeleton loaders instead of plain spinners where reasonable), animated
   checkmarks on lesson/quiz completion, etc. Use Flutter's animation
   widgets (AnimatedContainer, Hero, implicit/explicit animations,
   Lottie if useful) rather than static screen swaps.
3. **Delightful small details** — things like a progress ring that fills
   smoothly, a confetti/celebration moment when a course is completed or a
   certificate is issued, hover/press states on cards, empty states that
   are illustrated rather than blank.
4. **Consistency** — one design system (colors, spacing, corner radius,
   font weights) used everywhere, not different styles per screen.
5. **Performance matters as much as looks** — animations should be smooth
   (60fps), not janky; don't sacrifice usability for decoration.
6. **When you reach a screen/UI step, include the design approach in your
   Plan Mode proposal** — show me what the layout/animation approach will
   be (even a rough description) before building it, same as you would for
   a database model.

Goal: when someone (a recruiter, my mentor, a friend) opens this app, their
first reaction should be "this looks like a real, professional product,"
not "this looks like a student project."

---

## PHASE 1 — Auth & Course Catalog (read-only)

Goal: authentication + instructors can create courses, students can browse them.

Build:
- `users` table (role: student/instructor/admin/parent)
- JWT login/register/me endpoints
- `parent_student_links` table (no UI needed yet — just the model; linking
  flow gets built in the dedicated parent-portal phase)
- `courses` table + CRUD (only instructor who owns a course, or admin, can edit it)
- `modules` and `lessons` tables + CRUD (nested under a course)
- Public endpoint: list published courses, view course detail (modules/lessons
  list, but not full content yet if course requires enrollment)
- Flutter: login, course catalog (browse/search), course detail screen,
  instructor "create course" screens

**Enter Plan Mode first.** Show me your planned models, endpoints, and
folder structure before writing code. Wait for my approval.

Audit summary at the end.

---

## PHASE 2 — Enrollment & Content Delivery

Goal: students can enroll and actually consume lesson content.

Build:
- `enrollments` table + endpoint to enroll in a course (handle free vs paid
  — for paid, just mark as "pending payment" for now, real payment comes
  later if you want it)
- Access control: lesson content only visible to enrolled students (or the
  owning instructor/admin)
- File/video handling: decide and implement a simple storage approach
  (local storage path or a free-tier cloud bucket — ask me which before
  implementing) for video/pdf uploads
- Flutter: "My Courses" screen, lesson viewer (video player / text / pdf
  viewer depending on lesson type)

**Enter Plan Mode first.** Explicitly show me your plan for file/video
storage before implementing it — I want to approve the approach (local vs
cloud) before you build around it.

Audit summary at the end.

---

## PHASE 3 — Progress Tracking

Goal: track what a student has actually completed, and let them resume.

Build:
- `lesson_progress` table
- Endpoint: mark a lesson as complete (or update last_position_seconds for
  video resume)
- Endpoint: recalculate `enrollments.progress_percent` whenever a lesson is
  marked complete (based on completed lessons / total lessons in course)
- "Continue learning" endpoint: returns the next incomplete lesson per
  enrolled course
- Flutter: progress bar on course detail + "My Courses", "Resume" button
  that jumps to the right lesson/position

**Enter Plan Mode first.** Show me exactly how progress_percent will be
calculated and when it gets recalculated (this logic gets used everywhere
downstream, so I want to sanity check it early).

Audit summary at the end.

---

## PHASE 4 — Quizzes & Assessments

Goal: auto-graded quizzes tied to modules.

Build:
- `quizzes`, `quiz_questions`, `quiz_options` tables + instructor CRUD
  (build quiz, add multiple-choice questions, mark correct option)
- `quiz_attempts` table + submit-quiz endpoint (auto-grade against
  is_correct options, compare to passing_score, store result)
- Decide: can a student retake a quiz? (Ask me before implementing —
  affects the attempts logic.)
- Flutter: quiz-taking screen, result screen (score, pass/fail, review
  answers)

**Enter Plan Mode first.** Confirm the retake policy and grading logic with
me before writing the submit-quiz endpoint.

Audit summary at the end.

---

## PHASE 5 — Certificates

Goal: issue a certificate when a student legitimately completes a course.

Build:
- `certificates` table
- Certificate-issuance logic, triggered ONLY when:
  - `enrollments.progress_percent` = 100, AND
  - all quizzes in the course have a passing `quiz_attempts` entry (if the
    course has quizzes)
- Generate a PDF certificate (student name, course title, completion date,
  unique certificate number)
- Public verification endpoint: given a certificate_number, confirm it's
  real (for employers/others to verify — nice CV talking point)
- Flutter: "Download certificate" button on completed courses

**Enter Plan Mode first — this is a sensitive phase per the global rules.**
Explicitly show me the exact conditions that trigger certificate issuance
before writing the logic. I want to make sure it can't be gamed or
triggered incorrectly.

Audit summary at the end.

---

## PHASE 6 — Parent Portal

Goal: let a parent monitor and view (not control) their child's learning.

Build:
- Linking flow: either (a) parent registers and enters a child's
  email/student-ID to request a link, and the child/admin approves it, or
  (b) admin/instructor creates the link manually — decide which with me
  before building, since it affects the trust model
- Parent-facing endpoints (all read-only regarding the child's own actions):
  - List linked children
  - View a child's enrolled courses + progress_percent per course
  - View a child's quiz_attempts (scores/pass-fail per quiz)
  - View a child's earned certificates
  - Open/view a child's enrolled course CONTENT (lessons) so the parent can
    see what the child is learning — but no "mark complete," no quiz
    submission, no editing anything, from the parent's session
- Enforce at the API level (not just hidden in the UI) that a parent token
  can only ever GET data for linked children, never POST/PUT actions on
  their behalf
- Flutter: parent dashboard — list of linked children, tap into a child to
  see their courses/progress/marks/certificates, and a "view course content"
  mode that reuses the student lesson viewer but strips out any
  interactive/completion controls

**Enter Plan Mode first — this is a sensitive phase per the global rules.**
Show me exactly which endpoints are exposed to the parent role and confirm
each one is read-only before writing any code. I want to explicitly approve
the linking flow (option a or b above) before you build it.

Audit summary at the end.

---

## PHASE 7 — Dashboards & Reports

Goal: give instructors and admins visibility.

Build:
- Instructor dashboard: enrollment count per course, average completion
  rate, quiz pass rate
- Admin dashboard: total users, total courses, most popular courses,
  overall completion rate across the platform
- Flutter: dashboard screens with simple charts

**Enter Plan Mode first.** Show me which queries you'll use for each metric
before building charts on top of them.

Audit summary at the end.

---

## PHASE 8 — Polish for CV/Portfolio

Goal: make it presentable to a hiring manager.

Build:
- Seed script: fake instructors, courses, modules, lessons, and a few
  demo students with realistic progress/certificates already generated,
  PLUS at least one demo parent account already linked to a demo student
  with realistic progress/marks to show off in the demo
- README: problem statement, architecture overview, tech stack, how to run
  locally, screenshots, and a note on the certificate-verification feature
  (good talking point)
- Input validation + error handling pass across all endpoints
- Deploy to PythonAnywhere/Railway with a live demo link
- Optional: guest/demo login (one demo student, one demo instructor, one
  demo parent) so reviewers can explore without signing up — the parent
  demo login is a good one to highlight, since it's a distinctive feature

**Enter Plan Mode first**, even for this phase — confirm with me what goes
in the README and what the seed data should look like before generating it.

Audit summary at the end, plus the final live demo link.
