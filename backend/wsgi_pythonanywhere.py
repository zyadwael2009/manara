"""PythonAnywhere WSGI entry point.

Point PA's Web tab → "WSGI configuration file" at
    /home/manaralms/manara/backend/wsgi_pythonanywhere.py

by editing PA's default WSGI script to be just:

    import sys, os
    project_home = "/home/manaralms/manara/backend"
    if project_home not in sys.path:
        sys.path.insert(0, project_home)
    from wsgi_pythonanywhere import application  # noqa: F401

Everything else — DB URI, SECRET_KEY, CORS whitelist — is read from
the environment via `config.py`. Set those in `~/.pythonanywhere.env`
and load them in the same WSGI script (see DEPLOY_PYTHONANYWHERE.md
for the copy-paste block).
"""
from __future__ import annotations

import os

# --- Guardrails --------------------------------------------------------------
# `MANARA_ENV=production` flips SESSION_COOKIE_SECURE + tightens CORS defaults.
# Set it in the PA env-file, but assert it here so a mis-configured deploy
# never ships plaintext cookies.
os.environ.setdefault("MANARA_ENV", "production")

from app import create_app  # noqa: E402

application = create_app()
