# Manara — Privacy Policy

*Last updated: 2026-09-03*

Manara is a school-managed K-12 learning management app. This policy
explains what data the app collects, how it's used, and what rights
you have. If you're a parent whose child uses Manara, this policy
applies to the data you and your child share with the app.

## Who is Manara for

Manara is deployed by a single school. The account you sign in with was
issued by that school — you can't self-register as a student or
teacher. Parents receive an invitation from the school office to link
their existing account to their child's records.

## What we collect

### From every user
- **Account info** — name, email address, role (student / teacher /
  parent / admin), and a securely hashed password. Passwords are never
  stored in plaintext or reversible form.
- **Session data** — a signed session token stored on the device so you
  don't sign in every time. The token expires after 90 days of inactivity.
- **Device metadata for push notifications** (opt-in) — a browser or
  device token needed to deliver notifications. No advertising
  identifiers are collected.

### From students specifically
- **Academic records created by the school** — class assignment, grade
  category rubric, quiz attempts, assignment submissions (text +
  optional files you upload), attendance marks, lesson progress
  percentages, certificates, diplomas.
- **Fee records** entered by the school office.
- **Optional student-authored content** — comments on lesson pages
  and direct messages to teachers.

### From teachers
- Class + course assignments created by the school admin, plus content
  you author (quizzes, assignments, lesson bodies, homework posts,
  attendance marks, grades).

### From parents
- The parent-child link the school created, and any direct messages you
  send teachers through the in-app inbox.

## What we do NOT collect

- We do not collect location.
- We do not collect device sensor data (camera, mic, contacts).
- We do not use advertising identifiers.
- We do not run third-party analytics or ad SDKs.
- We do not sell any data to anyone. Ever.

## How we use it

- **Authentication + access control** — email + password sign you in;
  role determines what you can see or edit.
- **Rendering the app** — everything you see is derived from data the
  school has explicitly authorised your role to see.
- **Notifications** — bell notifications and (opt-in) browser push for
  grades posted, assignments graded, announcements, fees, and messages.
  Disable any category under **Notification preferences**.
- **PDF exports** — report cards, transcripts, certificates, diplomas,
  and fee statements are rendered on demand and streamed back to your
  device.

## Where the data lives

Manara is hosted on PythonAnywhere (a shared web-hosting provider) in a
MySQL database owned by your school. Uploaded files (assignment
submissions, lesson media) live on the same server's disk.

## Sharing

Your data is visible ONLY to:
- Yourself.
- Your school's admin(s).
- Teachers you're academically connected to (your course teachers, your
  homeroom teacher).
- Parents you've been linked to (parents see only their linked child's
  records).

The public verification endpoints
`/api/verify/<certificate-number>` and `/api/verify-diploma/<number>`
return only the student's name, the certificate/diploma title, and
whether it's been revoked. These endpoints are rate-limited to prevent
enumeration.

## Retention + deletion

- **Student records** are retained for as long as the school considers
  them academically relevant. On graduation, the account is soft-deleted
  (marked inactive) but grade + attendance history stays for transcript
  purposes.
- **Withdrawal** — the school admin can withdraw a student, which
  soft-deletes their account. Historical grade / cert data is retained
  so the school can still print a transcript.
- **Delete-my-data requests** — email the school admin. The admin
  processes the request through the Manara admin panel; where
  applicable, the school retains what the school district requires for
  compliance (typically 7 years for grade records).

## Children's privacy

Manara is intended for students aged 13+. For younger students, the
school obtains parental consent under the school's own COPPA-compliant
consent policy — Manara does not solicit consent directly from students.

## Security

- Passwords hashed with `werkzeug.security.generate_password_hash`
  (PBKDF2-SHA256, ~600k iterations).
- All traffic in production is served over HTTPS (TLS via
  PythonAnywhere's edge).
- Session cookies are HttpOnly, SameSite=Lax, and Secure in production.
- Certificate + diploma verification endpoints are rate-limited to 30
  requests / minute / IP.
- Failed logins are throttled: 5 wrong attempts locks the account for
  15 minutes.

## Changes to this policy

We'll update the "Last updated" date at the top when this policy
changes. Material changes will be surfaced as an in-app announcement
so you have a chance to review before continuing to use the app.

## Contact

Questions about this policy: email your school's admin (their address
is in the Manara admin panel), or contact us at
**admin@manara.school**.

---

## Data safety form (Google Play Console quick reference)

For the Play Console questionnaire, use these answers:

| Question | Answer |
|---|---|
| Does your app collect or share any of the required user data types? | **Yes** |
| Personal info — Name, Email | Collected (required, for account) / not shared |
| Personal info — User IDs | Collected (required, for account) / not shared |
| Financial info — Purchase history | Collected only if the school tracks fees (optional) / not shared |
| App activity — In-app messages | Collected (required, for teacher/parent messaging) / not shared |
| App activity — App interactions | Not collected |
| Web browsing — Web browsing history | Not collected |
| Device or other IDs | Collected only for push (optional) / not shared |
| Location | Not collected |
| Contacts | Not collected |
| All data collected in transit is encrypted | **Yes** (TLS) |
| Users can request their data be deleted | **Yes** (via school admin) |
