# Manara

> **Light every step of learning.**
> A K-12 school app — rosters, grading, quizzes, certificates, parent portal, dashboards.

<p align="center">
  <img src="lms_app/web/icons/Icon-192.png" alt="Manara logo" width="112" height="112" />
</p>

<p align="center">
  <a href="#live-demo"><b>Live demo</b></a> ·
  <a href="#feature-tour">Feature tour</a> ·
  <a href="#architecture">Architecture</a> ·
  <a href="#run-locally">Run locally</a> ·
  <a href="#trust-core">Trust core</a>
</p>

---

## Live demo

> **TODO — paste your GitHub Pages URL here after the first deploy runs.**
> Example: `https://<github-user>.github.io/manara/`

One-tap sign-in — every button just hits `/api/auth/login` with a
pre-seeded credential, no signup needed:

| Role | Direct link | Credentials |
|---|---|---|
| **Parent** (distinguishing feature) | `?demo=parent` | `parent@school.local` / `parent12` |
| Student | `?demo=student` | `amira@school.local` / `student1` |
| Teacher | `?demo=teacher` | `rivera@school.local` / `teacher1` |
| Admin | `?demo=admin` | `admin@school.local` / `adminadmin` |

The four pills at the bottom of the login screen do the same thing —
one tap and you're in the corresponding role.

---

## Why the parent portal is the interesting part

Most LMS side projects stop at student + teacher. Manara adds a real
fourth role — **parent** — with a strict server-enforced boundary:

- **Read-only.** Every non-`GET` from a parent session is refused at
  the blueprint's `@before_request` guard *and* the trust-core
  helpers in `utils/permissions.py` — belt-and-suspenders. No route
  exists anywhere that lets a parent submit lessons, grades, quizzes,
  or issue/revoke certificates on their child's behalf.
- **Content-view opens with one line.** Extending `can_view_content()`
  with a single `is_linked_parent_of_enrolled(user, course)` branch
  flips the whole content surface on for linked parents — no per-route
  edits, so no route was accidentally missed.
- **Cross-parent isolation is a hard error.** Parent A asking for
  Parent B's linked child returns 403 — verified by
  `tests/test_parent_portal.py::test_unlinked_parent_gets_403`.
- **Registration is closed.** Self-register with `role='parent'` is
  refused; parent accounts are created by the school office via
  `POST /api/users`.

The whole thing lands in ~1,200 lines split evenly between the
blueprint, the permission helpers, and the Flutter parent home + child
dashboard screens.

---

## Feature tour

| Area | What it does |
|---|---|
| **School hierarchy** | Section → Grade → Class → Student. Homeroom + per-course teacher assignments per class. |
| **Curriculum** | Grade = curriculum. Courses tagged mandatory or elective_group. Elective picks enforced server-side. |
| **Progress** | Per-lesson completion (video / PDF / text) with real progress writes; auto-completion on view. |
| **Grading** | Per-subject rubric of categories summing to 100. Per-term entries. Percentage → letter → GPA via an admin-editable scale. Cached columns kept fresh by `utils/grading.py`. |
| **Quizzes** | 5 question types (mc_single / mc_multi / true_false / short_answer / essay), per-quiz options (attempts / time / window), immediate feedback, manual override for essays. Roll-up into the Quizzes grade category. |
| **Certificates** | Auto-issued when the gate opens (`progress=100` + all quizzes passed + cumulative % ≥ threshold). Server-rendered PDF via reportlab. Public verify URL. Admin revoke with audit. |
| **Parent portal** | Read-only across enrollments, progress, quiz attempts, certificates, and full course content for linked children. |
| **Dashboards** | Instructor per-course (completion histogram, per-module bars, per-quiz pass rate, top 5, at-risk list). Admin platform-wide (KPI tiles, popular / highest-completion leaderboards, 6-month cert & user trends, grade-band donut). |
| **Year promotion** | Bulk class-level promotion with elective carry-forward via `courses.succeeds_course_id`. Grade 12 → graduated. |

---

## Certificate verification

Every certificate carries a number like `LMS-2026-3614A6CA`. Anyone with
the number can hit `/api/verify/<number>` (no auth) or the
`Verify a certificate` link on the login screen to confirm it's real —
useful for a hiring manager who wants to see the trust-core loop close:

1. Log in as parent → open Amira's certificate → **Copy verify link**.
2. Paste in a fresh incognito window → see the green ✓ card with
   student name + course + issued date.
3. Log in as admin → `POST /api/certificates/<id>/revoke` with a
   reason → refresh the incognito verify URL → red ✗ card with the
   reason.

---

## Architecture

```
Flutter (mobile + web) ──HTTP+X-Session-Token── Flask + SQLAlchemy
                                                       │
                                                       └── SQLite (dev + PA free tier)
                                                           MySQL/Postgres via DATABASE_URL
```

- **Backend** — Flask app factory (`backend/app.py`), a `models/`
  package split by domain (re-exported flat, so `from models import
  User` still works), one blueprint per feature (`routes/*.py`), single
  source of truth for trust-core in `utils/permissions.py` and
  `utils/certificates.py`. UUID primary keys, `to_dict()` camelCase
  JSON, signed-session auth.
- **Frontend** — Flutter (mobile + web) with Riverpod state
  management, hand-rolled `http` client (no dio / retrofit) whose
  endpoints live in `services/api_service_*.dart` parts. Design
  tokens live in `lib/core/theme/`. fl_chart for dashboards, confetti
  for the cert celebration, reportlab-generated PDFs opened via
  `url_launcher`.
- **Data model** — 20+ tables covering School / Grade / Class,
  Course / Module / Lesson, Enrollment / LessonProgress, GradeCategory /
  CourseRubric / GradeEntry / GradingScaleBand, Quiz / QuizQuestion /
  QuizAttempt / QuizAnswerEntry, Certificate, ParentStudentLink,
  DepartmentLeader, SchoolYear / Term.

### Tech stack

- Flask 3, Flask-SQLAlchemy, Flask-CORS, Werkzeug password hashing
- SQLAlchemy 2 with Numeric-typed grade columns; SQLite by default, MySQL/Postgres via `DATABASE_URL`
- reportlab for server-rendered certificate PDFs
- Flutter 3.11, Riverpod, http, url_launcher, fl_chart, confetti, syncfusion_flutter_pdfviewer, chewie
- pytest for the backend test suite (355 tests); `flutter test` for the app

---

## Trust core

Global rule: enrollment, progress, and certificate logic is
single-source-of-truth. Never re-implemented inline; every write path
routes through the helpers. Parent role is read-plus-content-view only.

Where the gates live:

- `backend/utils/permissions.py` — 40+ named predicates
  (`is_admin`, `teaches_course_in_any_class`, `is_linked_parent_of`,
  `can_view_content`, `can_edit_course_content`, `can_enter_grades_for`,
  `can_take_quiz`, `can_view_student_records`, …). Every route imports
  from here.
- `backend/utils/certificates.py` — `is_eligible()`,
  `maybe_issue_certificate()`, `render_certificate_pdf()`. Called from
  every write path that could open the gate (progress writes, grade
  writes, quiz submits/overrides, rubric changes). Idempotent.
- `backend/utils/grading.py` — cache recompute on every grade write
  or rubric change. Cached columns (`cached_percent`, `cached_letter`,
  `cached_gpa`) are what dashboards + report cards read from, so
  dashboard numbers always agree with the gradebook.
- `backend/routes/parents.py` — blueprint-level `@before_request`
  rejects every non-`GET` verb.

**Tests: 355 passing.** Trust-core negatives get named tests you can
grep for:

```
tests/test_certificates.py::test_low_grade_blocks_certificate
tests/test_certificates.py::test_no_grades_blocks_certificate
tests/test_certificates.py::test_failing_quiz_blocks_certificate
tests/test_parent_portal.py::test_self_register_as_parent_is_refused
tests/test_parent_portal.py::test_unlinked_parent_gets_403
tests/test_parent_portal.py::test_parent_cannot_complete_lessons
tests/test_parent_portal.py::test_parent_cannot_grade
tests/test_parent_portal.py::test_parent_bp_refuses_non_get
tests/test_parent_portal.py::test_parent_cannot_revoke_cert
tests/test_dashboards.py::test_instructor_cannot_see_others_drilldown
tests/test_dashboards.py::test_dashboard_endpoints_are_readonly
tests/test_seed_consistency.py::test_full_seed_is_self_consistent
```

The last one runs the demo seed against an in-memory DB and asserts
every cert was gate-eligible when issued — proves no back-door DB
inserts snuck in.

---

## Run locally

### Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate         # Windows
# source .venv/bin/activate     # macOS / Linux
pip install -r requirements.txt
python seed_dev.py              # creates dev DB + 25 students + 2 parents
python app.py                   # http://localhost:5000
```

### Flutter web

```bash
cd lms_app
flutter pub get
flutter run -d chrome --dart-define=API_BASE_URL=http://localhost:5000/api
```

### Backend tests

```bash
cd backend
python -m pytest -q      # 355 passing
```

---

## Deploy

### Backend → PythonAnywhere

1. Sign in to PythonAnywhere → **Consoles → Bash** → `git clone` the repo.
2. `mkvirtualenv --python=python3.12 manara-venv`, then
   `pip install -r backend/requirements.txt`.
3. **Web tab** → *Add a new web app* → **Manual configuration** → Python 3.12.
4. Replace the auto-generated WSGI file with the two lines shown in
   `backend/wsgi.py`'s docstring.
5. Point *Virtualenv* at `/home/<user>/.virtualenvs/manara-venv`.
6. **Environment variables**:
   - `SECRET_KEY` = 48 random chars (`python -c "import secrets; print(secrets.token_urlsafe(48))"`)
   - `DATABASE_URL` = `mysql+pymysql://<user>:<pw>@<user>.mysql.pythonanywhere-services.com/<user>$manara`
   - `CORS_ORIGINS` = `https://<gh-user>.github.io`
7. Open a Bash console once → `cd manara/backend && python seed_dev.py`.
8. Reload the web app.

Verify: `curl https://<user>.pythonanywhere.com/api/verify/LMS-2026-3614A6CA`
returns the Amira cert.

### Flutter web → GitHub Pages

**Option A — GitHub Actions (recommended).** Push `.github/workflows/pages.yml`
(committed at repo root) to `main`. First-run setup:

1. Repo → **Settings → Pages** → *Source: GitHub Actions*.
2. Repo → **Settings → Secrets and variables → Actions → Variables** →
   `BACKEND_URL` = `https://<user>.pythonanywhere.com`.
3. Push to `main`. The workflow builds Flutter web with the right
   `--dart-define` + `--base-href` and publishes automatically.

**Option B — one-shot from your machine.** Requires Node for `npx`:
```bash
make web-deploy BACKEND_URL=https://<user>.pythonanywhere.com
```

Verify: open `https://<gh-user>.github.io/manara/?demo=parent` in an
incognito window — you should land on the parent home with two children
listed.

---

## Roadmap

Explicitly out-of-scope for this build, listed here so a reviewer knows
the omissions were deliberate:

- Push notifications (grade posted, cert issued) — needs FCM/APNs setup.
- Parent ↔ teacher messaging — needs a whole messaging feature.
- Custom certificate templates per school / course — reportlab renderer
  is single-template.
- Bulk CSV export from dashboards — charts + PDF certs cover the demo story.
- SSO / OAuth — username+password is honest for a K-12 school app.

---

## Repository layout

```
manara/
├── backend/                    # Flask + SQLAlchemy
│   ├── app.py                  # app factory
│   ├── models/                 # 54 models, split by domain, re-exported flat
│   ├── wsgi.py                 # PythonAnywhere entry
│   ├── routes/                 # one blueprint per feature
│   ├── utils/                  # permissions, certificates, grading, quizzes, analytics
│   ├── tests/                  # 355 tests + shared conftest.py
│   └── seed_dev.py             # deterministic 25-student demo school
├── lms_app/                    # Flutter (mobile + web)
│   ├── lib/
│   │   ├── core/               # theme tokens, spacing, widgets, utils
│   │   ├── models/             # value types
│   │   ├── providers/          # Riverpod state
│   │   ├── services/           # ApiService (hand-rolled http)
│   │   └── screens/            # one folder per role: auth, student, instructor, admin, parent, public, catalog, splash
│   └── web/                    # PWA manifest + favicon + PWA icons
├── tooling/
│   └── gen_icons.py            # regenerate favicon + PWA icons from the lighthouse mark
├── .github/workflows/
│   └── pages.yml               # auto-deploy Flutter web to GH Pages
├── Makefile                    # make test / seed / web-demo / web-deploy
├── lms_claude_code_prompt.md   # the original build brief
└── README.md
```
