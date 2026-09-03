"""Phase 28 — student fees + payments.

Read scope:
  * Admin: any student.
  * Student: their own fees only.
  * Linked parent: any linked child's fees.

Write scope:
  * All CRUD is admin-only (create/update/delete fee items; log
    payments). No student or parent write path here.

Trust-core: fee state is orthogonal to grades / certificates. Nothing
in this file joins across those tables.
"""
from __future__ import annotations

from datetime import date as _date
from decimal import Decimal

from flask import Blueprint, current_app, jsonify, request

from models import FeeItem, FeePayment, ParentStudentLink, User, db
from routes.auth import current_user, login_required, require_admin
from utils.notifications import enqueue as enqueue_notification
from utils.permissions import is_admin, is_linked_parent_of, is_student
from utils.validation import (
    ValidationError,
    as_str,
    require_fields,
    require_json,
)

fees_bp = Blueprint("fees", __name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _can_read_student_fees(caller: User, student: User) -> bool:
    if caller is None or student is None:
        return False
    if is_admin(caller):
        return True
    if is_student(caller) and caller.id == student.id:
        return True
    if is_linked_parent_of(caller, student):
        return True
    return False


def _parse_amount(raw) -> Decimal:
    try:
        d = Decimal(str(raw))
    except Exception:
        raise ValidationError("amount must be a decimal number.") from None
    if d < 0:
        raise ValidationError("amount must be non-negative.")
    # Enforce two-decimal presentation to avoid float drift.
    return d.quantize(Decimal("0.01"))


def _notify_targets(student_id: str) -> list[str]:
    """Return every user_id who should be alerted on a fee event for
    this student — the student themselves + every linked parent."""
    targets = [student_id]
    parent_rows = ParentStudentLink.query.filter_by(
        student_id=student_id,
    ).all()
    for r in parent_rows:
        targets.append(r.parent_id)
    return targets


def _fmt_money(amount, currency: str = "USD") -> str:
    try:
        return f"{currency} {float(amount):,.2f}"
    except (TypeError, ValueError):
        return f"{currency} {amount}"


def _parse_date(raw) -> _date:
    try:
        return _date.fromisoformat(str(raw))
    except Exception:
        raise ValidationError("date must be YYYY-MM-DD.") from None


# ---------------------------------------------------------------------------
# GET /api/students/<sid>/fees
# ---------------------------------------------------------------------------
@fees_bp.route("/students/<string:sid>/fees", methods=["GET"])
@login_required
def list_student_fees(sid: str):
    student = db.session.get(User, sid)
    if student is None or student.role != "student":
        return jsonify({"error": "Student not found."}), 404
    caller = current_user()
    if not _can_read_student_fees(caller, student):
        return jsonify({"error": "You do not have permission."}), 403
    rows = (
        FeeItem.query
        .filter_by(student_id=sid)
        .order_by(FeeItem.due_date.is_(None), FeeItem.due_date.asc(),
                  FeeItem.created_at.asc())
        .all()
    )
    items = [r.to_dict() for r in rows]
    total_owed = sum(i["amount"] for i in items)
    total_paid = sum(i["paidAmount"] for i in items)
    return jsonify({
        "studentId": sid,
        "items": items,
        "totalAmount": total_owed,
        "totalPaid": total_paid,
        "totalBalance": total_owed - total_paid,
    }), 200


# ---------------------------------------------------------------------------
# GET /api/fees/mine — shortcut for student caller
# ---------------------------------------------------------------------------
@fees_bp.route("/fees/mine", methods=["GET"])
@login_required
def my_fees():
    caller = current_user()
    if not is_student(caller):
        return jsonify({
            "studentId": None, "items": [],
            "totalAmount": 0, "totalPaid": 0, "totalBalance": 0,
        }), 200
    return list_student_fees(caller.id)


# ---------------------------------------------------------------------------
# Phase 30 · T2 — GET /api/fees/summary
#
# Compact rollup for the student "My classes" AppBar chip: outstanding
# balance + overdue count in one round-trip. Silent shape for
# non-students so the client can call it unconditionally.
# ---------------------------------------------------------------------------
def _compute_summary(student_id: str) -> dict:
    from datetime import date as _d
    today = _d.today()
    rows = FeeItem.query.filter_by(student_id=student_id).all()
    outstanding = 0.0
    overdue = 0
    currency = "USD"
    for r in rows:
        currency = r.currency or currency
        bal = float(r.balance())
        if bal > 0:
            outstanding += bal
            if r.due_date is not None and r.due_date < today:
                overdue += 1
    return {
        "outstanding": round(outstanding, 2),
        "overdueCount": overdue,
        "currency": currency,
    }


@fees_bp.route("/fees/summary", methods=["GET"])
@login_required
def my_fee_summary():
    caller = current_user()
    if not is_student(caller):
        return jsonify({
            "outstanding": 0.0,
            "overdueCount": 0,
            "currency": "USD",
        }), 200
    return jsonify(_compute_summary(caller.id)), 200


# ---------------------------------------------------------------------------
# Phase 31 · T2 — GET /api/students/<sid>/fees/summary
#
# Same shape as `/fees/summary` but for a specific student — used by
# the parent portal's per-child chip and admin drilldowns. Read scope
# reuses the same rule as `list_student_fees`: admin, the student
# themselves, or a linked parent.
# ---------------------------------------------------------------------------
@fees_bp.route("/students/<string:sid>/fees/summary", methods=["GET"])
@login_required
def student_fee_summary(sid: str):
    student = db.session.get(User, sid)
    if student is None or student.role != "student":
        return jsonify({"error": "Student not found."}), 404
    caller = current_user()
    if not _can_read_student_fees(caller, student):
        return jsonify({"error": "You do not have permission."}), 403
    return jsonify(_compute_summary(sid)), 200


# ---------------------------------------------------------------------------
# Phase 31 · T1 — POST /api/fees/send-overdue-reminders
#
# Admin trigger for the overdue-fee reminder sweep. Idempotent by the
# day (enqueue()'s same-day dedupe suppresses duplicates), so hooking
# this to a cron / scheduled task at any cadence is safe.
# Returns the enqueue count (may include suppressed same-day dedupes).
# ---------------------------------------------------------------------------
@fees_bp.route("/fees/send-overdue-reminders", methods=["POST"])
@require_admin
def send_overdue_reminders():
    from utils.fees import run_overdue_reminders
    count = run_overdue_reminders()
    return jsonify({"reminded": count}), 200


# ---------------------------------------------------------------------------
# POST /api/students/<sid>/fees   (admin adds a fee item)
# ---------------------------------------------------------------------------
@fees_bp.route("/students/<string:sid>/fees", methods=["POST"])
@require_admin
def create_fee(sid: str):
    student = db.session.get(User, sid)
    if student is None or student.role != "student":
        return jsonify({"error": "Student not found."}), 404
    try:
        payload = require_json(request.get_json(silent=True))
        require_fields(payload, ("label", "amount"))
        label = as_str(payload["label"], "label", max_len=200)
        amount = _parse_amount(payload["amount"])
        currency = as_str(payload.get("currency") or "USD", "currency", max_len=8)
        due_date = None
        if payload.get("dueDate") not in (None, ""):
            due_date = _parse_date(payload["dueDate"])
        notes = payload.get("notes")
        if notes is not None:
            notes = as_str(notes, "notes", max_len=500) or None
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400
    caller = current_user()
    fee = FeeItem(
        student_id=sid,
        label=label,
        amount=amount,
        currency=currency,
        due_date=due_date,
        notes=notes,
        created_by_id=caller.id,
    )
    db.session.add(fee)
    db.session.commit()
    # Phase 30 · T1 — bell + push notification to student + parents.
    # Silent on failure (enqueue catches internally); never break the
    # 201 response on a notification hiccup.
    try:
        due_txt = f" due {due_date.isoformat()}" if due_date else ""
        body = f"{_fmt_money(amount, currency)}{due_txt}"
        for uid in _notify_targets(sid):
            enqueue_notification(
                uid,
                kind="fee_created",
                title=f"New fee: {label}",
                body=body,
                ref_type="fee",
                ref_id=fee.id,
            )
        db.session.commit()
    except Exception:  # pragma: no cover - purely defensive
        pass
    return jsonify(fee.to_dict()), 201


# ---------------------------------------------------------------------------
# PUT/PATCH /api/fees/<fid>
# ---------------------------------------------------------------------------
@fees_bp.route("/fees/<string:fid>", methods=["PUT", "PATCH"])
@require_admin
def update_fee(fid: str):
    fee = db.session.get(FeeItem, fid)
    if fee is None:
        return jsonify({"error": "Fee not found."}), 404
    try:
        payload = require_json(request.get_json(silent=True))
        if "label" in payload:
            fee.label = as_str(payload["label"], "label", max_len=200)
        if "amount" in payload:
            fee.amount = _parse_amount(payload["amount"])
        if "currency" in payload:
            fee.currency = as_str(payload["currency"], "currency", max_len=8)
        if "dueDate" in payload:
            raw = payload["dueDate"]
            fee.due_date = None if raw in (None, "") else _parse_date(raw)
        if "notes" in payload:
            raw = payload["notes"]
            fee.notes = None if raw in (None, "") else as_str(
                raw, "notes", max_len=500) or None
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400
    db.session.commit()
    return jsonify(fee.to_dict()), 200


# ---------------------------------------------------------------------------
# DELETE /api/fees/<fid>
# ---------------------------------------------------------------------------
@fees_bp.route("/fees/<string:fid>", methods=["DELETE"])
@require_admin
def delete_fee(fid: str):
    fee = db.session.get(FeeItem, fid)
    if fee is None:
        return jsonify({"error": "Fee not found."}), 404
    db.session.delete(fee)
    db.session.commit()
    return jsonify({"ok": True}), 200


# ---------------------------------------------------------------------------
# POST /api/fees/<fid>/payments   (log a payment against a fee)
# ---------------------------------------------------------------------------
@fees_bp.route("/fees/<string:fid>/payments", methods=["POST"])
@require_admin
def log_payment(fid: str):
    # Phase 33 fix #3 — take a row-level lock on the FeeItem so the
    # balance check + insert can't race. Two admins hitting Log
    # payment simultaneously used to both see the pre-write balance
    # and both succeed, ending the fee with a negative balance.
    # `with_for_update()` is a no-op on SQLite (the whole DB is
    # already single-writer) but honors row locks on Postgres/MySQL.
    fee = (
        FeeItem.query
        .filter_by(id=fid)
        .with_for_update()
        .first()
    )
    if fee is None:
        return jsonify({"error": "Fee not found."}), 404
    try:
        payload = require_json(request.get_json(silent=True))
        require_fields(payload, ("amount",))
        amount = _parse_amount(payload["amount"])
        if amount == 0:
            raise ValidationError("amount must be greater than zero.")
        # Guard: don't allow paying more than the outstanding balance —
        # overpayments are a data-entry error, not a feature. Compute
        # inside the locked transaction so a peer INSERT can't sneak in.
        current_balance = fee.balance()
        if amount > current_balance:
            raise ValidationError(
                f"amount {amount} exceeds outstanding balance {current_balance}.")
        method = payload.get("method")
        if method is not None:
            method = as_str(method, "method", max_len=40) or None
        note = payload.get("note")
        if note is not None:
            note = as_str(note, "note", max_len=500) or None
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400
    caller = current_user()
    pay = FeePayment(
        fee_item_id=fid,
        amount=amount,
        method=method,
        note=note,
        logged_by_id=caller.id,
    )
    db.session.add(pay)
    db.session.commit()
    # Phase 30 · T1 — bell + push receipt.
    try:
        remaining = fee.balance()
        remaining_txt = (
            "Paid in full." if remaining <= 0
            else f"Balance now {_fmt_money(remaining, fee.currency or 'USD')}."
        )
        title = f"Payment received: {fee.label}"
        body = f"{_fmt_money(amount, fee.currency or 'USD')} · {remaining_txt}"
        for uid in _notify_targets(fee.student_id):
            enqueue_notification(
                uid,
                kind="fee_payment",
                title=title,
                body=body,
                ref_type="fee",
                ref_id=fee.id,
            )
        db.session.commit()
    except Exception as _notif_err:  # pragma: no cover
        # Phase 33 fix #22 — narrow the swallow. A commit failure
        # here would previously mask a real DB error alongside the
        # intended "push transport hiccup" cases; now we log so ops
        # notices, but still don't 500 the primary write.
        from flask import current_app as _app
        _app.logger.warning("fee notification enqueue failed: %r", _notif_err)
        db.session.rollback()
    return jsonify({
        "payment": pay.to_dict(),
        "fee": fee.to_dict(),
    }), 201


# ---------------------------------------------------------------------------
# DELETE /api/fee-payments/<pid>
# ---------------------------------------------------------------------------
@fees_bp.route("/fee-payments/<string:pid>", methods=["DELETE"])
@require_admin
def delete_payment(pid: str):
    p = db.session.get(FeePayment, pid)
    if p is None:
        return jsonify({"error": "Payment not found."}), 404
    db.session.delete(p)
    db.session.commit()
    return jsonify({"ok": True}), 200


# ---------------------------------------------------------------------------
# GET /api/students/<sid>/fees.pdf   (receipt PDF via utils/pdf.py)
# ---------------------------------------------------------------------------
@fees_bp.route("/students/<string:sid>/fees.pdf", methods=["GET"])
@login_required
def student_fees_pdf(sid: str):
    student = db.session.get(User, sid)
    if student is None or student.role != "student":
        return jsonify({"error": "Student not found."}), 404
    caller = current_user()
    if not _can_read_student_fees(caller, student):
        return jsonify({"error": "You do not have permission."}), 403
    from utils.pdf import render_fees_pdf
    from flask import Response
    fees = FeeItem.query.filter_by(student_id=sid).order_by(
        FeeItem.due_date.is_(None), FeeItem.due_date.asc(),
        FeeItem.created_at.asc(),
    ).all()
    try:
        pdf_bytes = render_fees_pdf(student=student, fees=fees)
    except Exception as e:  # pragma: no cover - reportlab breakage
        current_app.logger.warning("fees pdf failed: %r", e)
        return jsonify({"error": "Could not render receipt."}), 500
    return Response(
        pdf_bytes,
        mimetype="application/pdf",
        headers={
            "Content-Disposition":
                f'inline; filename="fees-{sid}.pdf"',
        },
    )
