"""Payments: single payments, bulk settlement, and payment deadlines.

Every movement of money is written to the `payments` ledger with its date,
on top of raising `amount_paid` on the document. The ledger is what the
business-health score reads to tell on-time from late.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.utils import round2
from ..models import Business, Party, Payment, Purchase, Sale
from ..schemas import SettleResult
from ..workflow import payment_status_for

#: Used when neither the party nor the business says otherwise.
DEFAULT_CREDIT_DAYS = 30


@dataclass(frozen=True, slots=True)
class PaymentMode:
    label: str
    #: What the `reference` field holds, or None when the mode needs nothing.
    reference: str | None
    #: The `details` keys this mode may carry; anything else is dropped.
    details: tuple[str, ...] = ()


#: What a payment can say about how the money moved. The frontend mirrors this
#: list in `lib/payments.ts`; the server is the one that enforces it.
PAYMENT_MODES: dict[str, PaymentMode] = {
    "cash": PaymentMode("Cash", None),
    "upi": PaymentMode("UPI", "transaction ID", ("upiId",)),
    "card": PaymentMode("Card", "last four digits of the card", ("cardType", "approvalCode")),
    "cheque": PaymentMode("Cheque", "cheque number", ("bank", "chequeDate")),
    "bank_transfer": PaymentMode("Bank transfer", "UTR or reference number", ("bank",)),
    "other": PaymentMode("Other", "description", ()),
}
CARD_TYPES = ("credit", "debit")
_REFERENCE_MAX = 64


def clean_payment_mode(
    mode: str | None, reference: str | None, details: dict | None
) -> tuple[str | None, str | None, dict | None]:
    """Validate how a payment was made. Returns what to store.

    A missing mode means "not recorded" and stores nothing. A card payment
    may carry only the last four digits: a full card number is refused, not
    truncated, so nobody learns that typing it in works.
    """
    if mode is None or not str(mode).strip():
        return None, None, None
    key = str(mode).strip().lower()
    spec = PAYMENT_MODES.get(key)
    if spec is None:
        raise ValueError("Unknown payment mode.")

    ref = (reference or "").strip()
    if spec.reference is None:
        ref = ""
    elif not ref:
        raise ValueError(f"{spec.label} payments need the {spec.reference}.")
    elif len(ref) > _REFERENCE_MAX:
        raise ValueError(f"The {spec.reference} is too long.")
    if key == "card" and not re.fullmatch(r"\d{4}", ref):
        raise ValueError(
            "Enter only the last four digits of the card. The full number is never recorded."
        )
    if key == "cheque" and not re.fullmatch(r"[A-Za-z0-9-]{1,20}", ref):
        raise ValueError("A cheque number is letters, digits and dashes only.")

    kept: dict[str, str] = {}
    for name in spec.details:
        value = str((details or {}).get(name) or "").strip()
        if not value:
            continue
        if len(value) > _REFERENCE_MAX:
            raise ValueError(f"{name} is too long.")
        if name == "cardType" and value.lower() not in CARD_TYPES:
            raise ValueError("Card type must be credit or debit.")
        if name == "chequeDate":
            try:
                datetime.strptime(value, "%Y-%m-%d")
            except ValueError as err:
                raise ValueError("Cheque date must be a date (yyyy-mm-dd).") from err
        kept[name] = value.lower() if name == "cardType" else value
    return key, ref or None, kept or None


def credit_days_for(db: Session, business: Business, party_id: uuid.UUID | None) -> int:
    """How long this party has to pay: their own terms, else the business default."""
    if party_id is not None:
        days = db.scalar(select(Party.credit_days).where(Party.id == party_id))
        if days is not None:
            return days
    return business.credit_days if business.credit_days is not None else DEFAULT_CREDIT_DAYS


def deadline_for(date: datetime, credit_days: int) -> datetime:
    return date + timedelta(days=credit_days)


def record_document_payment(
    db: Session,
    doc: Sale | Purchase,
    amount: float,
    how: tuple[str | None, str | None, dict | None] = (None, None, None),
) -> None:
    """Money taken on the day of the document itself. Not committed here.

    `how` is the cleaned (mode, reference, details) from `clean_payment_mode`,
    validated by the caller before the document was written.
    """
    if amount <= 0:
        return
    is_sale = isinstance(doc, Sale)
    mode, reference, details = how
    db.add(
        Payment(
            business_id=doc.business_id,
            sale_id=doc.id if is_sale else None,
            purchase_id=None if is_sale else doc.id,
            amount=round2(amount),
            reason="sale" if is_sale else "purchase",
            date=doc.date,
            mode=mode,
            reference=reference,
            details=details,
        )
    )


def _apply_to_document(doc: Sale | Purchase, amount: float) -> float:
    """Raise `amount_paid`, snapping to the total once the document settles so
    the party balance never keeps a sub-cent residual that `payment_status_for`
    already calls "paid". Returns the amount actually applied."""
    paid = round2(min(doc.amount_paid + amount, doc.total))
    status = payment_status_for(paid, doc.total)
    if status == "paid":
        paid = doc.total
    applied = round2(paid - doc.amount_paid)
    doc.amount_paid = paid
    doc.payment_status = status
    return applied


def record_payment(
    db: Session,
    business_id: uuid.UUID,
    *,
    sale_id: uuid.UUID | None = None,
    purchase_id: uuid.UUID | None = None,
    amount: float,
    date: datetime | None = None,
    mode: str | None = "cash",
    reference: str | None = None,
    details: dict | None = None,
) -> None:
    """Record money in (sale) or money out (purchase), reducing the party balance.

    `date` is when the money moved; it defaults to now and can be back-dated
    for a payment that was logged late, but never to before the document.
    `mode`, `reference` and `details` say how: see `PAYMENT_MODES`.
    """
    amt = round2(amount)
    if not amt > 0:
        raise ValueError("Amount must be greater than zero.")
    how = clean_payment_mode(mode, reference, details)

    if sale_id is not None:
        # Scoped to the caller's business, so a payment can never be recorded
        # against another tenant's invoice.
        doc = db.scalar(select(Sale).where(Sale.id == sale_id, Sale.business_id == business_id))
        noun = "sale"
    elif purchase_id is not None:
        doc = db.scalar(
            select(Purchase).where(Purchase.id == purchase_id, Purchase.business_id == business_id)
        )
        noun = "purchase"
    else:
        raise ValueError("Nothing to pay against.")

    if doc is None:
        raise ValueError(f"{noun.capitalize()} not found.")
    if doc.status == "cancelled":
        raise ValueError(f"Cannot record a payment on a cancelled {noun}.")

    when = date or datetime.now()
    if when < doc.date:
        raise ValueError(f"A payment cannot be dated before the {noun} itself.")

    applied = _apply_to_document(doc, amt)
    if applied > 0:
        db.add(
            Payment(
                business_id=business_id,
                sale_id=sale_id,
                purchase_id=purchase_id,
                amount=applied,
                reason="payment",
                date=when,
                mode=how[0],
                reference=how[1],
                details=how[2],
            )
        )
        if doc.party_id:
            party = db.scalar(select(Party).where(Party.id == doc.party_id))
            if party:
                party.balance = round2(party.balance - applied)

    db.commit()


def _settle_rows(db: Session, business_id: uuid.UUID, rows, when: datetime) -> SettleResult:
    applied = 0.0
    count = 0
    for row in rows:
        due = round2(row.total - row.amount_paid)
        if due <= 0:
            continue
        row.amount_paid = row.total
        row.payment_status = "paid"
        is_sale = isinstance(row, Sale)
        db.add(
            Payment(
                business_id=business_id,
                sale_id=row.id if is_sale else None,
                purchase_id=None if is_sale else row.id,
                amount=due,
                reason="settlement",
                date=when,
            )
        )
        applied = round2(applied + due)
        count += 1
    return SettleResult(count=count, total=applied)


def settle_party(db: Session, business_id: uuid.UUID, party_id: uuid.UUID) -> SettleResult:
    """Settle every outstanding document for one party, then clear its balance.

    The balance is set to zero rather than only reduced by document dues,
    because it may also hold an opening balance with no invoice/bill row.
    """
    party = db.scalar(select(Party).where(Party.id == party_id, Party.business_id == business_id))
    if party is None:
        raise ValueError("Party not found.")

    model = Purchase if party.type == "supplier" else Sale
    rows = list(
        db.scalars(
            select(model).where(
                model.business_id == business_id,
                model.party_id == party_id,
                model.status != "cancelled",
            )
        )
    )
    result = _settle_rows(db, business_id, rows, datetime.now())
    party.balance = 0
    db.commit()
    return result


def settle_all_outstanding(db: Session, business_id: uuid.UUID, kind: str) -> SettleResult:
    """Mark every outstanding document of one kind as paid across the business.

    Walk-in documents with no linked party are settled too; the matching
    customer or supplier balances are then cleared, including opening balances.
    """
    if kind == "payable":
        model, party_type = Purchase, "supplier"
    else:
        model, party_type = Sale, "customer"

    rows = list(
        db.scalars(
            select(model).where(model.business_id == business_id, model.status != "cancelled")
        )
    )
    result = _settle_rows(db, business_id, rows, datetime.now())

    for party in db.scalars(
        select(Party).where(Party.business_id == business_id, Party.type == party_type)
    ):
        party.balance = 0

    db.commit()
    return result
