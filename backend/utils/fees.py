"""Phase 31 · T1 — fee-related helpers that live outside the route
layer so they can be called from a cron script, a scheduled task, or a
manual admin trigger endpoint (see `routes/fees.py::send_overdue_reminders`).

`enqueue()`'s same-day dedupe on (user_id, kind, ref_type, ref_id)
means calling `run_overdue_reminders()` multiple times per day is a
harmless no-op after the first — safe to hook into any cadence.
"""
from __future__ import annotations

from datetime import date as _date


def run_overdue_reminders() -> int:
    """Walk every fee item with `due_date < today` and balance > 0,
    enqueue one "N days overdue" bell + push per fee to the student
    and every linked parent.

    Returns the number of reminders enqueued (before dedupe). The
    same-day dedupe inside `enqueue()` means the second call today
    returns the same count but writes no new rows.
    """
    from models import FeeItem, ParentStudentLink, db
    from utils.notifications import enqueue

    today = _date.today()
    fees = (
        FeeItem.query
        .filter(FeeItem.due_date.isnot(None))
        .filter(FeeItem.due_date < today)
        .all()
    )
    sent = 0
    for fee in fees:
        balance = float(fee.balance())
        if balance <= 0:
            continue
        days = (today - fee.due_date).days
        title = f"Fee overdue: {fee.label}"
        body = (
            f"{days} day{'s' if days != 1 else ''} past due — "
            f"{fee.currency or 'USD'} {balance:.2f} outstanding."
        )
        targets = [fee.student_id]
        for p in ParentStudentLink.query.filter_by(
            student_id=fee.student_id
        ).all():
            targets.append(p.parent_id)
        for uid in targets:
            enqueue(
                uid,
                kind="fee_overdue",
                title=title,
                body=body,
                ref_type="fee",
                ref_id=fee.id,
            )
            sent += 1
    try:
        db.session.commit()
    except Exception:  # pragma: no cover - defensive
        db.session.rollback()
    return sent
