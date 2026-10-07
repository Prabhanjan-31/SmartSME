"""Payment modes on the ledger

How each payment was made (cash, UPI, card, cheque, bank transfer, other),
the identifier that goes with it (UPI transaction ID, last four card digits,
cheque number, UTR), and the rest per mode (bank, cheque date, card type,
approval code, payer's UPI ID) as a small JSON object.

Nullable on purpose: rows written before this existed, settlements, and
payments taken through Smart Input or an inbound order have no mode, and the
UI says "not recorded" rather than guessing "cash".

Revision ID: 0009_payment_modes
Revises: 0008_payments
Create Date: 2026-10-07
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009_payment_modes"
down_revision: str | None = "0008_payments"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("payments", sa.Column("mode", sa.Text(), nullable=True))
    op.add_column("payments", sa.Column("reference", sa.Text(), nullable=True))
    op.add_column("payments", sa.Column("details", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("payments", "details")
    op.drop_column("payments", "reference")
    op.drop_column("payments", "mode")
