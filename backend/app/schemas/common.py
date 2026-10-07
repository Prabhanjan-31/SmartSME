"""Payload pieces shared by more than one part of the API.

Field names are camelCase because they are the wire contract with the React
client; the ORM layer keeps snake_case.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, BeforeValidator

from ..core.utils import parse_date_input


def _coerce_date(value: object) -> datetime | None:
    """Accept either a wire string (`yyyy-mm-dd`) or an already-parsed datetime.

    This is what lets one schema serve both the HTTP boundary and the internal
    callers (Smart Input, seeding) that already hold a datetime.
    """
    if value is None or isinstance(value, datetime):
        return value
    return parse_date_input(value)


#: An optional business date; unparseable input becomes None rather than a 422,
#: so a bad date falls back to "today" instead of rejecting the whole document.
BusinessDate = Annotated[datetime | None, BeforeValidator(_coerce_date)]


class LineInput(BaseModel):
    """One line of a sale or purchase.

    `productId` is null for a free-text line that matched no catalogue product.
    """

    productId: str | None = None
    description: str
    quantity: int
    unitPrice: float


class DocumentInput(BaseModel):
    """Fields shared by the sale and purchase create payloads.

    A sale and a purchase are the same document in opposite directions, so the
    payload is identical; only the meaning of `partyId` differs.
    """

    partyId: str | None = None
    items: list[LineInput] = []
    amountPaid: float = 0
    #: How any money paid at the time was taken: a key from
    #: `domain.payments.PAYMENT_MODES`, with its identifier and extras. Left
    #: out by Smart Input and inbound orders, which do not know.
    paymentMode: str | None = None
    paymentReference: str | None = None
    paymentDetails: dict[str, str] = {}
    discountType: str = "none"  # none | amount | percentage
    discountValue: float = 0
    notes: str | None = None
    #: Omit to use today; set to back-date a transaction that was logged late.
    date: BusinessDate = None
    #: Where the document came from: "form" or "smart-input".
    source: str = "form"


class DocumentTotals(BaseModel):
    """The computed money breakdown. Discount comes off the subtotal before tax."""

    subtotal: float
    discountAmount: float
    tax: float
    total: float


class PaymentInput(BaseModel):
    """A payment against an outstanding invoice or bill."""

    amount: float
    #: When the money moved. Omit for today; back-date a payment logged late.
    date: BusinessDate = None
    #: How it was paid: a key from `domain.payments.PAYMENT_MODES`, the
    #: identifier that mode needs, and any extras (bank, cheque date, ...).
    mode: str = "cash"
    reference: str | None = None
    details: dict[str, str] = {}


class DateInput(BaseModel):
    """A corrected business date for an already-recorded document."""

    date: str


class SettleResult(BaseModel):
    """Outcome of settling one party or every outstanding document."""

    #: Number of invoices/bills that had an outstanding balance and were settled.
    count: int
    #: Total amount marked as paid across all settled documents.
    total: float
