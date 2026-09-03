"""WSGI entry point for PythonAnywhere (or any WSGI host).

On PythonAnywhere:
  1. Web tab → Add a new web app → Manual configuration → Python 3.12.
  2. Point the WSGI file (default: /var/www/<user>_pythonanywhere_com_wsgi.py)
     at THIS module by replacing its contents with something like:

       import sys
       sys.path.insert(0, '/home/<user>/manara/backend')
       from wsgi import application

  3. Under "Virtualenv", point at the venv you created with
     `pip install -r backend/requirements.txt`.
  4. Set env vars in the Web tab's "Environment variables" section:
       SECRET_KEY   - 40+ random chars
       DATABASE_URL - mysql+pymysql://<user>:<pw>@<user>.mysql.pythonanywhere-services.com/<user>$manara
       CORS_ORIGINS - https://<gh-user>.github.io
       MANARA_ENV   - production   (enables SESSION_COOKIE_SECURE + prod defaults)
  5. Reload the web app.

The very first time, open a Bash console on PythonAnywhere and run
`python seed_dev.py` once against the deployed DB to prime it.
"""
from app import app as application  # noqa: F401 — WSGI convention
