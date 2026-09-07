"""Fee items and the payments against them."""
from __future__ import annotations

from models.base import (
    db,
    generate_uuid,
    utc_now,
    _iso,
    Decimal,
    Any,
)

# =============================================================================
# Phase 28 — Fee tracking + payments
#
# `FeeItem` = one line item owed by a student (tuition, activity fee,
# uniform, trip). Admin creates + updates; student + linked parents
# read only their own.
# `FeePayment` = one payment against a fee item. A fee can have multiple
# payments (partial payment support) — the balance is
# `amount - sum(payments.amount)`. Admin logs payments; students +
# parents read them (no write).
#
# Trust-core: fees do NOT gate grading, certificates, or enrollment.
# The read path never joins across those tables; the write path stays
# admin-only. Receipts render via `utils/pdf.py::render_fees_pdf`.
# =============================================================================
class FeeItem(db.Model):
    __tablename__ = "fee_items"

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    student_id = db.Column(
        db.String(36), db.ForeignKey("users.id"), nullable=False, index=True,
    )
    label = db.Column(db.String(200), nullable=False)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    currency = db.Column(db.String(8), nullable=False, default="USD")
    due_date = db.Column(db.Date, nullable=True)
    notes = db.Column(db.String(500), nullable=True)
    created_by_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=utc_now, onupdate=utc_now,
    )

    payments = db.relationship(
        "FeePayment", backref="fee_item", lazy="dynamic",
        cascade="all, delete-orphan",
    )

    def paid_amount(self) -> Decimal:
        total = Decimal("0")
        for p in self.payments.all():
            total += p.amount or Decimal("0")
        return total

    def balance(self) -> Decimal:
        return (self.amount or Decimal("0")) - self.paid_amount()

    def to_dict(self, *, include_payments: bool = True) -> dict[str, Any]:
        data: dict[str, Any] = {
            "id": self.id,
            "studentId": self.student_id,
            "label": self.label,
            "amount": float(self.amount) if self.amount is not None else 0.0,
            "currency": self.currency,
            "dueDate": self.due_date.isoformat() if self.due_date else None,
            "notes": self.notes,
            "createdAt": _iso(self.created_at),
            "updatedAt": _iso(self.updated_at),
            "paidAmount": float(self.paid_amount()),
            "balance": float(self.balance()),
        }
        if include_payments:
            data["payments"] = [p.to_dict() for p in self.payments.all()]
        return data


class FeePayment(db.Model):
    __tablename__ = "fee_payments"

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    fee_item_id = db.Column(
        db.String(36), db.ForeignKey("fee_items.id"), nullable=False, index=True,
    )
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    paid_at = db.Column(db.DateTime, nullable=False, default=utc_now)
    method = db.Column(db.String(40), nullable=True)  # cash / card / bank / etc.
    note = db.Column(db.String(500), nullable=True)
    logged_by_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "feeItemId": self.fee_item_id,
            "amount": float(self.amount) if self.amount is not None else 0.0,
            "paidAt": _iso(self.paid_at),
            "method": self.method,
            "note": self.note,
            "loggedById": self.logged_by_id,
            "createdAt": _iso(self.created_at),
        }
