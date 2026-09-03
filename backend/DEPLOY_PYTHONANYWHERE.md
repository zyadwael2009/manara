# Deploy Manara backend to PythonAnywhere

Target: `https://manaralms.pythonanywhere.com/api/...`
Free tier. Everything below assumes you're signed into PA as **`manaralms`**.

## 0. Prerequisites

- PA account (`manaralms`) — sign up at pythonanywhere.com
- Local shell with `git` — used once to push the repo to a public
  git host (GitHub, GitLab, Bitbucket), which PA then clones
- Free-tier caveat: outbound HTTP requests only reach hosts on PA's
  whitelist. Web Push (mozilla / chrome push servers) is not whitelisted,
  so the bell will still work but browser push notifications will
  silently fail. Everything else — grades, certs, PDFs, seeded content
  — works. Upgrade to the $5/mo Hacker plan later to lift this.

## 1. Push the code to GitHub (or any public git host)

From `D:/Programming/erp systems/lms`:

```bash
git init
git remote add origin https://github.com/zyadwael2009/manara.git
git add .
git commit -m "Initial Manara release"
git push -u origin main
```

PA free tier can only clone from public repos over HTTPS. If you'd
rather keep the code private, upgrade to Hacker and use PA's SSH-key
support.

## 2. Clone the repo on PA

Open a bash console on PA (`Consoles → Bash`).

```bash
cd ~
git clone https://github.com/zyadwael2009/manara.git
```

The tree ends up at `/home/manaralms/manara/backend/...`.

## 3. Create a Python 3.12 virtualenv

```bash
mkvirtualenv --python=/usr/bin/python3.12 manaralms
pip install -r ~/manara/backend/requirements.txt
```

`mkvirtualenv` puts it at `~/.virtualenvs/manaralms`. If you get
"command not found," `pip install virtualenvwrapper` first.

## 4. Database — SQLite on free tier (no setup)

PA free tier no longer includes MySQL. Leave `DATABASE_URL` unset and
the backend falls back to SQLite at
`~/manara/backend/instance/lms.db`. PA's `~/` filesystem is persistent
across reloads and app-shutdowns, so this DB survives.

If you later upgrade to Hacker+ ($5/mo) and want MySQL:
- PA dashboard → **Databases** tab → set MySQL password → create db
  called `default` (full name: `manaralms$default`).
- Uncomment the `DATABASE_URL` line in `~/.pythonanywhere.env` (step 5)
  with the password.
- Reload the web app.

Nothing else changes — SQLite and MySQL run the same code path.

## 5. Create the env file

Copy `backend/.env.pythonanywhere.example` → `~/.pythonanywhere.env`
and fill in the two required placeholders:

```bash
cp ~/manara/backend/.env.pythonanywhere.example ~/.pythonanywhere.env
nano ~/.pythonanywhere.env
```

- `SECRET_KEY` — generate with:
  ```bash
  python -c "import secrets; print(secrets.token_urlsafe(64))"
  ```
- `CORS_ORIGINS` — leave as `https://manaralms.pythonanywhere.com` for now.
- `DATABASE_URL` — leave commented out on free tier (SQLite kicks in
  automatically). Uncomment + fill only if you upgraded to a paid tier.

## 6. Configure the Web tab

- PA dashboard → **Web** tab → **Add a new web app**.
- Manual configuration → Python 3.12.
- On the app config page:
  - **Source code:** `/home/manaralms/manara/backend`
  - **Working directory:** `/home/manaralms/manara/backend`
  - **Virtualenv:** `/home/manaralms/.virtualenvs/manaralms`
  - **WSGI configuration file:** click the link to edit the auto-generated
    file (path is `/var/www/manaralms_pythonanywhere_com_wsgi.py`).

Replace its entire contents with:

```python
import os, sys

# Load .env from ~/.pythonanywhere.env
from pathlib import Path
env_path = Path.home() / ".pythonanywhere.env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip())

project_home = "/home/manaralms/manara/backend"
if project_home not in sys.path:
    sys.path.insert(0, project_home)

from wsgi_pythonanywhere import application  # noqa: F401
```

## 7. Seed the admin

Back in the bash console:

```bash
workon manaralms
cd ~/manara/backend
export MANARA_ENV=production
export SECRET_KEY='<same 64-char string you put in .env>'
# Skip DATABASE_URL on free tier — SQLite is the default.
# On paid MySQL:
# export DATABASE_URL='mysql+pymysql://manaralms:<db-password>@manaralms.mysql.pythonanywhere-services.com/manaralms$default'
python seed_prod.py
```

Copy the printed admin password. `_ensure_schema_updates` in `app.py`
creates every table on first import via `db.create_all()`, so no
manual migrations. On SQLite this materialises `instance/lms.db` the
first time you run any code against it.

## 8. Reload the app

PA Web tab → green **Reload** button.

Verify with:

```bash
curl https://manaralms.pythonanywhere.com/api/health
```

Expected: `{"status": "ok", "phase": 2}`

## 9. Point the mobile app at production

In `lms_app/lib/core/constants/app_constants.dart` — the default
already picks up `--dart-define=API_BASE_URL=…` at build time. When
you build the release APK (see `DEPLOY_GOOGLE_PLAY.md`), pass:

```
flutter build appbundle --release \
    --dart-define=API_BASE_URL=https://manaralms.pythonanywhere.com/api
```

## Ongoing updates

For every code change you push to git:

```bash
# on PA bash
cd ~/manara
git pull
workon manaralms
pip install -r backend/requirements.txt  # only when deps changed
# PA Web tab → Reload
```

`_ensure_schema_updates` handles additive column adds on the next
request. Model deletes / non-additive changes still need a manual
Alembic-style migration.

## SQLite backup + restore (free tier)

The whole DB is one file at `~/manara/backend/instance/lms.db`.
Regular backup:

```bash
cd ~/manara/backend/instance
cp lms.db "lms.db.$(date +%F).bak"
# Or download it via PA's Files tab and keep a copy locally.
```

Restore = drop the .db back in place and hit the Web tab Reload.

## Troubleshooting

- **502 Bad Gateway** — Check the error log at the top of the Web tab.
  Common cause: a mis-copied env var or a missing dep.
- **500 on every request** — Usually `DATABASE_URL` typo. On free
  tier, the safest fix is comment `DATABASE_URL` out entirely
  (falls back to SQLite). On MySQL, the `$` between username and DB
  name is mandatory in the URL.
- **"database is locked" errors under load** — SQLite's single-writer
  limit surfacing. Fine for a demo school; upgrade to Hacker + MySQL
  once you have real concurrent traffic.
- **Fresh reload, no schema** — Hit the health endpoint once; the
  first request is what boots `create_app` and runs `db.create_all`.
- **"Locked account" on first sign-in** — The failed-login lockout
  kicks in on 5 wrong tries. Wait 15 minutes or manually clear the
  `token_version` on the User row.
- **Media uploads 413** — Free tier caps request bodies at 100 MB;
  the app config allows 200 MB but PA overrides at the proxy.
