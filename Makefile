# Manara — one-shot deploy commands.
#
# Env vars you can override on the command line:
#   BACKEND_URL   the deployed backend origin (default: https://<user>.pythonanywhere.com)
#   BASE_HREF     the GitHub Pages sub-path (default: /manara/)
#
# Usage:
#   make test         run the backend test suite
#   make seed         seed the local dev DB
#   make web-demo     build Flutter web pointing at the deployed backend
#   make web-local    build Flutter web pointing at localhost:5000
#   make web-deploy   push build/web to the gh-pages branch (needs npx)

BACKEND_URL ?= https://zyadwael.pythonanywhere.com
BASE_HREF   ?= /manara/

.PHONY: test seed web-demo web-local web-deploy icons

test:
	cd backend && python -m pytest -q

seed:
	cd backend && python seed_dev.py

icons:
	python tooling/gen_icons.py

web-demo:
	cd lms_app && flutter build web \
	    --dart-define=API_BASE_URL=$(BACKEND_URL)/api \
	    --base-href $(BASE_HREF)

web-local:
	cd lms_app && flutter build web \
	    --dart-define=API_BASE_URL=http://localhost:5000/api \
	    --base-href /

# Push the built web bundle to the gh-pages branch (uses the `gh-pages`
# npm package via npx — no permanent Node dep).
web-deploy: web-demo
	cd lms_app && npx --yes gh-pages -d build/web -b gh-pages -m "deploy: $$(date -u +%Y-%m-%dT%H:%M:%SZ)"
