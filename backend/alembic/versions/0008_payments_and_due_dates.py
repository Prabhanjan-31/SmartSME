"""Dated payments and payment deadlines

Until now a payment only raised `amount_paid` on its invoice or bill, so the
books could say how much had been paid but never when. The `payments` table is
the ledger: one row per movement of money, with its date. Money taken on the day
of the document is recorded with reason "sale" or "purchase"; money that came
later is "payment" (one invoice) or "settlement" (a party or everything cleared
at once).

Every sale and purchase gains a `due_date`, the day its unpaid part is expected.
It defaults to the business date plus the party's `credit_days`, or the
business's own `credit_days` (30 unless changed), and any one document can be
extended by hand.

Backfill: each existing document with money against it gets one ledger row
dated on the document itself, because that is the only date the old schema
kept. Existing due dates are set to the document date plus 30 days.

Revision ID: 0008_payments
Revises: 0007_claimed_at
Create Date: 2026-10-07
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008_payments"
down_revision: str | None = "0007_claimed_at"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "payments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "business_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("businesses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "sale_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sales.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "purchase_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("purchases.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("amount", sa.Float(), nullable=False, server_default="0"),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("date", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_payments_business_date", "payments", ["business_id", "date"])
    op.create_index("ix_payments_sale", "payments", ["sale_id"])
    op.create_index("ix_payments_purchase", "payments", ["purchase_id"])

    for table, ref in (("sales", "sale_id"), ("purchases", "purchase_id")):
        op.execute(
            f"""
            insert into payments (id, business_id, {ref}, amount, reason, date, created_at)
            select gen_random_uuid(), business_id, id, amount_paid,
                   '{table[:-1]}', date, created_at
            from {table}
            where amount_paid > 0
            """
        )

    for table in ("sales", "purchases"):
        op.add_column(table, sa.Column("due_date", sa.DateTime(), nullable=True))
        op.execute(f"update {table} set due_date = date + interval '30 days'")
        op.alter_column(table, "due_date", nullable=False, server_default=sa.func.now())

    op.add_column("parties", sa.Column("credit_days", sa.Integer(), nullable=True))
    op.add_column(
        "businesses",
        sa.Column("credit_days", sa.Integer(), nullable=False, server_default="30"),
    )


def downgrade() -> None:
    op.drop_column("businesses", "credit_days")
    op.drop_column("parties", "credit_days")
    for table in ("sales", "purchases"):
        op.drop_column(table, "due_date")
    op.drop_index("ix_payments_purchase", table_name="payments")
    op.drop_index("ix_payments_sale", table_name="payments")
    op.drop_index("ix_payments_business_date", table_name="payments")
    op.drop_table("payments")
