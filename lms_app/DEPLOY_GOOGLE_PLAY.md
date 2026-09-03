# Deploy Manara to Google Play

Target package: **`com.manara.school`** (locked forever after first upload).
Target API base URL: **`https://manaralms.pythonanywhere.com/api`**

## 0. Prerequisites

- Google Play Console developer account — **$25 one-time fee**
  https://play.google.com/console/signup
- Java `keytool` on your PATH (comes with the JDK — already on your
  machine if `flutter doctor` is green)
- Backend already deployed and reachable at
  `https://manaralms.pythonanywhere.com/api/health`
  (see `backend/DEPLOY_PYTHONANYWHERE.md`)

## 1. Generate the upload keystore

**Do this exactly once, ever.** If you lose this keystore you cannot
update the Play Store listing — you'd have to publish a new app.
Store it in your password manager AND back it up to at least two
places (e.g. a USB drive + cloud storage encrypted).

```bash
keytool -genkey -v \
    -keystore ~/manara-upload-key.jks \
    -keyalg RSA -keysize 2048 -validity 10000 \
    -alias manara
```

It'll prompt for:
- A store password (remember this)
- Your name / org (any real-ish text — it's just for the cert subject)
- A key password (usually same as store password — accept the default)

## 2. Wire the keystore into the build

```bash
cd D:/Programming/erp\ systems/lms/lms_app/android
cp key.properties.example key.properties
# Edit key.properties — fill in the passwords + keystore path.
```

`android/.gitignore` already excludes `key.properties` and any
`.jks`/`.keystore` files so nothing sensitive lands in git.

## 3. Bump the version

Edit `lms_app/pubspec.yaml`:

```yaml
# Format: <marketing version>+<build number>
# Every Play Store upload needs a NEW build number.
# Marketing version is what users see; build number is what Play uses to
# order uploads.
version: 1.0.0+1
```

For every subsequent release, increment the number after `+`. Bump the
marketing part (`1.0.1`, `1.1.0`, `2.0.0`) whenever there's a
user-visible change worth calling out in the changelog.

## 4. Build the release AAB

```bash
cd D:/Programming/erp\ systems/lms/lms_app
flutter build appbundle --release \
    --dart-define=API_BASE_URL=https://manaralms.pythonanywhere.com/api
```

Output: `build/app/outputs/bundle/release/app-release.aab`

Google Play requires **AAB** (Android App Bundle), not APK — the AAB
lets Play generate optimised per-device APKs at install time.

Verify the AAB is really signed with your keystore (not the debug key):

```bash
jarsigner -verify -verbose -certs build/app/outputs/bundle/release/app-release.aab
```

Look for `CN=<the name you typed into keytool>` — if it shows
`CN=Android Debug`, you missed step 2.

## 5. Create the Play Console listing

Log into `play.google.com/console` → **Create app**.

Fill in:
- **App name:** Manara
- **Default language:** English (US) (or Arabic if you shipped the RTL locale)
- **App or game:** App
- **Free or paid:** Free
- **Declarations:** tick both boxes (developer program policies + US
  export laws)

## 6. Store listing

Under **Grow → Store presence → Main store listing**:

- **Short description** (80 chars):
  > K-12 learning: grades, homework, quizzes, and attendance — for
  > students, teachers, parents, and admins.

- **Full description** (4000 chars) — copy from `STORE_LISTING.md`.

- **Graphics:**
  - **App icon:** 512 × 512 PNG. Use `assets/icon.png` at 512 px.
    (Adaptive icon foreground + background already in
    `android/app/src/main/res/mipmap-*/`.)
  - **Feature graphic:** 1024 × 500 PNG. Any brand banner.
  - **Phone screenshots:** at least 2 (up to 8). 1080 × 1920 or larger.
    Suggested captures — home + course detail + grade report + calendar
    + fees. Use the seeded demo data (Amira / student1 · yara12 /
    student1 · admin@school.local / adminadmin).
  - **Category:** Education
  - **Contact details:** an email you monitor
  - **Privacy policy:** REQUIRED — see step 7.

## 7. Privacy policy

`PRIVACY_POLICY.md` in this repo has a starter draft. Host it as a
plain HTML/Markdown page anywhere reachable — a GitHub Pages site
under `<you>.github.io/manara-privacy/` works fine. Paste the URL into
the Play Console.

## 8. App content declarations

Under **App content**:

- **Privacy policy:** URL from step 7
- **App access:** All functionality is behind a login — set this + upload
  admin creds (email / password from `seed_prod.py`) so reviewers can
  sign in. Play won't approve without this.
- **Ads:** No
- **Content rating questionnaire:** answer honestly. For Manara the
  right answers give an "Everyone" rating.
- **Target audience:** Age 13+ (COPPA below 13 needs extra hoops)
- **News app:** No
- **Data safety:** Fill this in from the checklist in
  `PRIVACY_POLICY.md#data-safety-form`.

## 9. Upload the AAB

Under **Production → Create new release** (or **Internal testing** if
you want to soft-launch to a few devices first — recommended):

- **App bundle:** upload `build/app/outputs/bundle/release/app-release.aab`
- **Release name:** `1.0.0 (1)` (auto-filled from the AAB)
- **Release notes:** "Initial release."
- **Save → Review release → Start rollout**

## 10. Wait for review

- Internal testing releases: live in ~15 minutes
- Production: 1-3 days for first-time apps (Google reviews every new
  app on the store manually)
- If rejected, the "Publishing overview" page shows the reason. Most
  common first-time reject: missing/inaccessible reviewer login (step 8).

## Ongoing releases

For every update:

1. Bump `pubspec.yaml` build number.
2. `flutter build appbundle --release --dart-define=API_BASE_URL=...`
3. Upload the new AAB under **Production → Create new release**.
4. Fill in changelog.
5. Roll out.

Play Console remembers your signing config — you only upload the new
AAB and hit Publish.

## Troubleshooting

- **"Your APK/AAB is signed with the debug keystore"** — key.properties
  wasn't found. From `android/`, check the file exists and the paths
  inside resolve.
- **"Version code X has already been used"** — bump the `+N` part of
  `pubspec.yaml:version` again.
- **"Package name conflicts with an existing app"** — someone else took
  `com.manara.school`. Change `applicationId` in
  `android/app/build.gradle.kts` AND `namespace` on the same line, plus
  the `<manifest package="…">` if you had one.
- **App crashes on launch, no error visible** — connect a device and
  `flutter install --release && adb logcat *:E` to see the actual
  stack trace. Most common cause: missing `INTERNET` permission (we
  added it in step 0 of the manifest).
