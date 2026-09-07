"""One-time production bootstrap — creates the root admin only.

Unlike `seed_dev.py` (which populates a demo school with 133 users +
720 lessons), this creates exactly one admin account so you can sign in
on a fresh production DB and start real data entry.

Run ONCE on PythonAnywhere from a bash console:

    cd ~/manara/backend
    source ~/.virtualenvs/manaralms/bin/activate
    export MANARA_ENV=production
    export SECRET_KEY='<64+ char random string>'
    export CORS_ORIGINS='https://<gh-user>.github.io'
    # DATABASE_URL is left unset on the PythonAnywhere free tier, which no
    # longer includes MySQL — the backend falls back to SQLite at
    # instance/lms.db. On a paid tier, export the mysql+pymysql:// URL here.
    python seed_prod.py

Idempotent — running twice is safe; the admin row is upserted.

Credentials are printed once. Change the password immediately after
first login via the Admin → Account screen.
"""
from __future__ import annotations

import os
import secrets

from app import create_app
from models import User, db


def main() -> None:
    admin_email = os.environ.get("ADMIN_EMAIL", "admin@manara.school").strip()
    admin_name = os.environ.get("ADMIN_NAME", "School Admin").strip()
    admin_password = (
        os.environ.get("ADMIN_PASSWORD")
        or secrets.token_urlsafe(16)  # 22-char URL-safe password
    )

    app = create_app()
    with app.app_context():
        u = User.query.filter_by(email=admin_email).first()
        if u is None:
            u = User(name=admin_name, email=admin_email, role="admin")
            u.set_password(admin_password)
            db.session.add(u)
            db.session.commit()
            action = "created"
        else:
            u.role = "admin"
            u.name = admin_name
            if os.environ.get("ADMIN_PASSWORD"):
                u.set_password(admin_password)
            db.session.commit()
            action = "updated"

    print("-" * 60)
    print(f"Admin {action}.")
    print(f"  Email    : {admin_email}")
    if action == "created" or os.environ.get("ADMIN_PASSWORD"):
        print(f"  Password : {admin_password}")
    else:
        print("  Password : (unchanged — set ADMIN_PASSWORD to reset)")
    print("-" * 60)
    print("Change this password after first login — Account → Change password.")


if __name__ == "__main__":
    main()
