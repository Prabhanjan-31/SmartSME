"""The payment ledger: every rupee that changed hands, with the day it did."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Index, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, business_fk, fk, money, pk, timestamp


class Payment(Base):
    """Money received against a sale or paid against a purchase.

    `sales.amount_paid` says how much has been paid; this says *when*. The
    `reason` separates money taken on the day of the document ("sale",
    "purchase") from money that arrived later ("payment", "settlement"), which
    is the part that tells us whether credit is being paid on time.
    """

    __tablename__ = "payments"
    __table_args__ = (Index("ix_payments_business_date", "business_id", "date"),)

    id: Mapped[uuid.UUID] = pk()
    business_id: Mapped[uuid.UUID] = business_fk()
    sale_id: Mapped[uuid.UUID | None] = fk("sales.id", nullable=True)
    purchase_id: Mapped[uuid.UUID | None] = fk("purchases.id", nullable=True)
    amount: Mapped[float] = money()
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    #: When the money moved. Back-datable, like a document's business date.
    date: Mapped[datetime] = timestamp()
    #: How: one of `domain.payments.PAYMENT_MODES`. Null means not recorded:
    #: rows older than this column, settlements, and documents published from
    #: Smart Input or an inbound order.
    mode: Mapped[str | None] = mapped_column(Text)
    #: The identifier for that mode: UPI transaction ID, the last four digits
    #: of the card (never more), cheque number, bank UTR, or a description.
    reference: Mapped[str | None] = mapped_column(Text)
    #: The rest, per mode: bank, chequeDate, cardType, approvalCode, upiId.
    details: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = timestamp()
