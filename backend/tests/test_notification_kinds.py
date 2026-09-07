"""`NOTIFICATION_KINDS` must describe what the app actually sends.

`models.py` declared this constant twice with two different sets of names —
once beside the `Notification` model, once beside `NotificationPreference` —
and the second silently won at import time. The consequences were quiet:

  * The preferences screen listed `grade_posted`, `cert_issued`,
    `attendance_absent`, `quiz_due` and `streak_reminder`. Nothing in the
    codebase emits any of those, so switching them off did nothing.
  * `grade_updated`, `attendance_marked`, `certificate_issued` and
    `comment_reply` — four of the ten kinds that really are emitted — were
    absent from the list, so `POST /api/notifications/preferences` rejected
    them as unknown and there was no way to turn them off. `enqueue()` looks
    a preference up by the emitted kind, found no row, and fell open.

Nothing failed. The feature simply did not work, which is exactly the kind of
drift a test can hold still.
"""
from __future__ import annotations

import ast
import pathlib
import re

from models import NOTIFICATION_KINDS

BACKEND = pathlib.Path(__file__).resolve().parent.parent


def _kinds_passed_to_enqueue() -> set[str]:
    """Every literal `kind` argument at an `enqueue(...)` call site.

    Parsed rather than pattern-matched: the calls span one line to a dozen,
    and `routes/fees.py` imports the helper under an alias.
    """
    found: set[str] = set()
    for directory in ("routes", "utils"):
        for path in (BACKEND / directory).glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                name = (
                    func.id if isinstance(func, ast.Name)
                    else getattr(func, "attr", None)
                )
                # `routes/fees.py` calls it `enqueue_notification`.
                if not name or "enqueue" not in name:
                    continue
                for keyword in node.keywords:
                    if keyword.arg == "kind" and isinstance(keyword.value, ast.Constant):
                        found.add(keyword.value.value)
                # enqueue(user_id, kind, title, ...) — kind is 2nd positional.
                if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant):
                    found.add(node.args[1].value)
    return found


def test_every_emitted_kind_can_be_switched_off():
    emitted = _kinds_passed_to_enqueue()
    assert emitted, "found no enqueue() call sites — has the helper been renamed?"

    missing = sorted(emitted - set(NOTIFICATION_KINDS))
    assert not missing, (
        f"these kinds are sent but absent from NOTIFICATION_KINDS, so a user "
        f"cannot opt out of them: {missing}"
    )


def test_no_advertised_kind_is_a_phantom():
    """The preferences screen renders this list, so a name nobody emits is a
    switch that does nothing."""
    emitted = _kinds_passed_to_enqueue()
    phantom = sorted(set(NOTIFICATION_KINDS) - emitted)
    assert not phantom, (
        f"NOTIFICATION_KINDS advertises kinds nothing ever sends: {phantom}"
    )


def test_constant_is_declared_exactly_once():
    """Two declarations is how this broke in the first place, and the model
    package's re-exporting `__init__` would hide it just as effectively as one
    long module did."""
    declarations = [
        f"{path.name}:{i + 1}"
        for path in sorted((BACKEND / "models").glob("*.py"))
        if path.name != "__init__.py"
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines())
        if re.match(r"^NOTIFICATION_KINDS\s*=", line)
    ]
    assert len(declarations) == 1, (
        f"NOTIFICATION_KINDS is declared at {declarations}; a later declaration "
        "silently shadows the earlier one at import time"
    )


def test_preferences_endpoint_accepts_every_emitted_kind(client):
    """End-to-end: the API must take an opt-out for each kind it can send."""
    token = client.post(
        "/api/auth/register",
        json={
            "name": "S",
            "email": "s@t.local",
            "password": "password12",
            "role": "student",
        },
    ).get_json()["sessionToken"]
    headers = {"X-Session-Token": token}

    advertised = client.get(
        "/api/notifications/preferences", headers=headers,
    ).get_json()["kinds"]
    assert set(advertised) == set(NOTIFICATION_KINDS)

    for kind in NOTIFICATION_KINDS:
        r = client.put(
            "/api/notifications/preferences",
            json={"kind": kind, "enabled": False},
            headers=headers,
        )
        assert r.status_code == 200, f"{kind} was refused: {r.data}"
