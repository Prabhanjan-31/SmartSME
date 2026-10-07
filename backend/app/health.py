"""Business health: four 0-100 scores and a weighted overall.

Split in two on purpose. `gather` runs the SQL and returns plain numbers; the
`score_*` functions are pure, so every threshold below is unit-tested without a
database. Each score is None when there is not enough data to say anything,
which the dashboard shows as "Not enough data yet" rather than a made-up number.

Why each formula, threshold and weight is what it is: docs/business-health.md.
"""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from .models import Expense, Party, Payment, Product, Purchase, Sale, SaleItem

#: The "recent" window for revenue.
RECENT_DAYS = 30
#: Profitability, sales velocity, dead stock, on-time payment and cash movement
#: all look back this far: long enough to hold two or three rent and salary
#: cycles.
LOOKBACK_DAYS = 90
#: Revenue is compared against up to 90 days before the recent window.
BASELINE_DAYS = 90
#: Less baseline history than this and a growth figure means nothing.
MIN_BASELINE_DAYS = 14
#: Below this many sales in the baseline, growth is scaled down in proportion.
FULL_CONFIDENCE_SALES = 20

#: Percentage points of the overall score. See docs/business-health.md.
WEIGHTS = {"cashFlow": 30, "profitability": 30, "revenue": 25, "inventory": 15}
#: At least this much of the weight must be backed by data for an overall score.
MIN_WEIGHT = 50
#: The overall can sit at most this far above the weakest part: the width of
#: the "Fair" band, so a part in "At risk" keeps the total out of "Healthy".
CAP_ABOVE_WEAKEST = 30


def _clamp(n: float, lo: int = 0, hi: int = 100) -> int:
    """Round half-up and clamp. `round()` rounds halves to even, so 82.5 would
    show as 82; the inner round strips float noise like 82.49999999999999."""
    return max(lo, min(hi, math.floor(round(n, 6) + 0.5)))


@dataclass(slots=True, frozen=True)
class InventoryInputs:
    product_count: int
    #: Sum of availability x 90-day sales value, and the sum of the weights.
    weighted_available: float
    sales_weight: float
    #: Sum of availability with every product counted once, for when nothing sold.
    plain_available: float
    #: Cost value of everything in stock, and of the part that is not moving.
    stock_value: float
    dead_stock_value: float


@dataclass(slots=True, frozen=True)
class RevenueInputs:
    has_sales: bool
    recent: float
    baseline: float
    #: How much of the 90-day baseline the business has history for.
    baseline_days: float
    baseline_count: int


@dataclass(slots=True, frozen=True)
class ProfitInputs:
    #: Last 90 days. Sales are net of tax: GST collected is not income.
    net_sales: float
    cogs: float
    expenses: float


@dataclass(slots=True, frozen=True)
class CashInputs:
    """Everything over the last LOOKBACK_DAYS, from the payment ledger.

    "On time" and "late" are rupee amounts of credit: money that was still
    owed after the day of the document. A payment is on time if it arrived by
    the deadline; an unpaid amount is on time until the deadline passes.
    """

    #: Credit customers owed: paid or still open by the deadline, or not.
    on_time_in: float
    late_in: float
    #: Credit the business owed its suppliers, the same way.
    on_time_out: float
    late_out: float
    #: Every rupee received against sales, and every rupee paid out on
    #: purchases and expenses.
    cash_in: float
    cash_out: float


@dataclass(slots=True, frozen=True)
class HealthInputs:
    inventory: InventoryInputs
    revenue: RevenueInputs
    profit: ProfitInputs
    cash: CashInputs


# ---------------------------------------------------------------------------
# Scores
# ---------------------------------------------------------------------------
def score_inventory(i: InventoryInputs) -> int | None:
    """70% availability, weighted by what sells; 30% stock that is not dead.

    A product is available (1), low (0.5, at or under its threshold) or out
    (0). Each counts in proportion to its sales over the lookback, so a best
    seller running out costs far more than a slow line doing the same.
    """
    if i.product_count == 0:
        return None
    if i.sales_weight > 0:
        availability = i.weighted_available / i.sales_weight
    else:
        availability = i.plain_available / i.product_count
    dead_share = i.dead_stock_value / i.stock_value if i.stock_value > 0 else 0.0
    return _clamp(100 * (0.7 * availability + 0.3 * (1 - dead_share)))


def score_revenue(r: RevenueInputs) -> int | None:
    """Last 30 days against the monthly average of the 90 days before.

    Flat scores 75, and every 1% of growth or decline moves it one point.
    """
    if not r.has_sales or r.baseline_days < MIN_BASELINE_DAYS:
        return None
    if r.recent == 0 and r.baseline == 0:
        return 0  # Dormant: nothing sold in four months.
    monthly_baseline = r.baseline / r.baseline_days * RECENT_DAYS
    if monthly_baseline == 0:
        # Selling again after a gap: there is nothing to grow from.
        return 75
    growth = (r.recent - monthly_baseline) / monthly_baseline
    confidence = min(1.0, r.baseline_count / FULL_CONFIDENCE_SALES)
    return _clamp(75 + 100 * growth * confidence)


def score_profitability(p: ProfitInputs) -> int | None:
    """Net margin: break-even scores 40, 5% scores 70, 10% or more scores 100."""
    if p.net_sales <= 0:
        return None
    margin = (p.net_sales - p.cogs - p.expenses) / p.net_sales
    return _clamp(40 + 600 * margin)


def _on_time_share(on_time: float, late: float) -> float | None:
    total = on_time + late
    return on_time / total if total > 0 else None


def cash_flow_checks(c: CashInputs) -> dict[str, float | None]:
    """The three checks behind the cash-flow score, each 0 to 1 or None.

    collecting: are customers paying by the deadline?
    paying: is the business paying its suppliers by the deadline?
    movement: did more money come in than go out? Break-even is 0.5, keeping
    a fifth of what came in is 1, and spending a fifth more is 0.
    """
    if c.cash_in == 0 and c.cash_out == 0:
        movement = None
    elif c.cash_in == 0:
        movement = 0.0
    else:
        movement = min(1.0, max(0.0, 0.5 + 2.5 * (c.cash_in - c.cash_out) / c.cash_in))
    return {
        "collecting": _on_time_share(c.on_time_in, c.late_in),
        "paying": _on_time_share(c.on_time_out, c.late_out),
        "movement": movement,
    }


def score_cash_flow(c: CashInputs) -> int | None:
    """The average of whichever of the three checks have anything to measure.

    A cash-only shop that pays its suppliers at the counter has no credit in
    either direction, so its cash flow is simply money in against money out.
    """
    present = [v for v in cash_flow_checks(c).values() if v is not None]
    if not present:
        return None
    return _clamp(100 * sum(present) / len(present))


def overall_score(parts: dict[str, int | None]) -> int | None:
    """Weighted average of the parts that have data, held near the weakest.

    Missing parts drop out and the rest are re-weighted, unless less than half
    the weight is left. The cap stops one bad part from hiding behind three
    good ones.
    """
    present = {k: v for k, v in parts.items() if v is not None}
    weight = sum(WEIGHTS[k] for k in present)
    if weight < MIN_WEIGHT:
        return None
    average = sum(WEIGHTS[k] * v for k, v in present.items()) / weight
    return _clamp(min(average, min(present.values()) + CAP_ABOVE_WEAKEST))


def score(inputs: HealthInputs) -> dict[str, int | None]:
    parts = {
        "inventory": score_inventory(inputs.inventory),
        "revenue": score_revenue(inputs.revenue),
        "profitability": score_profitability(inputs.profit),
        "cashFlow": score_cash_flow(inputs.cash),
    }
    return {"overall": overall_score(parts), **parts}


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------
def outstanding_balances(db: Session, business_id: uuid.UUID) -> tuple[float, float]:
    """What customers owe the business, and what it owes suppliers.

    A party's balance already holds the unpaid part of every document linked to
    it, plus any opening balance, so documents with a party must not be added
    again. Only walk-in sales and supplier-less purchases sit outside a balance.
    """
    balances = db.execute(
        select(
            func.coalesce(
                func.sum(Party.balance).filter(Party.type == "customer", Party.balance > 0), 0.0
            ),
            func.coalesce(
                func.sum(Party.balance).filter(Party.type == "supplier", Party.balance > 0), 0.0
            ),
        ).where(Party.business_id == business_id)
    ).one()
    walk_in, unbilled = (
        db.scalar(
            select(
                func.coalesce(func.sum(func.greatest(doc.total - doc.amount_paid, 0.0)), 0.0)
            ).where(
                doc.business_id == business_id, doc.status != "cancelled", doc.party_id.is_(None)
            )
        )
        or 0
        for doc in (Sale, Purchase)
    )
    return float(balances[0]) + float(walk_in), float(balances[1]) + float(unbilled)


def gather(db: Session, business_id: uuid.UUID, now: datetime | None = None) -> HealthInputs:
    """Every number the scores need, in a handful of aggregate queries."""
    now = now or datetime.now()
    recent_start = now - timedelta(days=RECENT_DAYS)
    lookback_start = now - timedelta(days=LOOKBACK_DAYS)
    baseline_start = recent_start - timedelta(days=BASELINE_DAYS)
    live_sale = (Sale.business_id == business_id, Sale.status != "cancelled")
    in_baseline = (Sale.date >= baseline_start, Sale.date < recent_start)

    s = db.execute(
        select(
            func.count(Sale.id),
            func.min(Sale.date),
            func.coalesce(func.sum(Sale.total).filter(Sale.date >= recent_start), 0.0),
            func.coalesce(func.sum(Sale.total).filter(*in_baseline), 0.0),
            func.count(Sale.id).filter(*in_baseline),
            func.coalesce(func.sum(Sale.total - Sale.tax).filter(Sale.date >= lookback_start), 0.0),
        ).where(*live_sale)
    ).one()
    count, first_sale, recent, baseline, baseline_count, net_90 = s

    # Days of baseline the business could have sold in: a shop that started
    # selling 50 days ago has 20 days of baseline, not 90 days with 70 empty.
    history_start = max(baseline_start, first_sale) if first_sale else recent_start
    baseline_days = max(0.0, (recent_start - history_start).total_seconds() / 86400)

    cogs = db.scalar(
        select(func.coalesce(func.sum(SaleItem.quantity * Product.purchase_price), 0.0))
        .select_from(SaleItem)
        .join(Sale, SaleItem.sale_id == Sale.id)
        .join(Product, SaleItem.product_id == Product.id)
        .where(*live_sale, Sale.date >= lookback_start)
    )
    expenses = db.scalar(
        select(func.coalesce(func.sum(Expense.amount), 0.0)).where(
            Expense.business_id == business_id, Expense.date >= lookback_start
        )
    )

    sold = (
        select(SaleItem.product_id.label("pid"), func.sum(SaleItem.line_total).label("value"))
        .join(Sale, SaleItem.sale_id == Sale.id)
        .where(*live_sale, Sale.date >= lookback_start, SaleItem.product_id.is_not(None))
        .group_by(SaleItem.product_id)
        .subquery()
    )
    availability = case(
        (Product.stock <= 0, 0.0),
        (Product.stock <= Product.low_stock_threshold, 0.5),
        else_=1.0,
    )
    weight = func.coalesce(sold.c.value, 0.0)
    cost_value = Product.stock * Product.purchase_price
    inv = db.execute(
        select(
            func.count(Product.id),
            func.coalesce(func.sum(availability * weight), 0.0),
            func.coalesce(func.sum(weight), 0.0),
            func.coalesce(func.sum(availability), 0.0),
            func.coalesce(func.sum(cost_value).filter(Product.stock > 0), 0.0),
            func.coalesce(
                func.sum(cost_value).filter(
                    Product.stock > 0,
                    # New lines have not had a fair chance to sell yet.
                    Product.created_at < lookback_start,
                    sold.c.pid.is_(None),
                ),
                0.0,
            ),
        )
        .select_from(Product)
        .outerjoin(sold, sold.c.pid == Product.id)
        .where(Product.business_id == business_id)
    ).one()

    return HealthInputs(
        inventory=InventoryInputs(
            product_count=inv[0],
            weighted_available=float(inv[1]),
            sales_weight=float(inv[2]),
            plain_available=float(inv[3]),
            stock_value=float(inv[4]),
            dead_stock_value=float(inv[5]),
        ),
        revenue=RevenueInputs(
            has_sales=count > 0,
            recent=float(recent),
            baseline=float(baseline),
            baseline_days=baseline_days,
            baseline_count=baseline_count,
        ),
        profit=ProfitInputs(
            net_sales=float(net_90), cogs=float(cogs or 0), expenses=float(expenses or 0)
        ),
        cash=_gather_cash(db, business_id, now, lookback_start),
    )


def _gather_cash(db: Session, business_id: uuid.UUID, now: datetime, since: datetime) -> CashInputs:
    """On-time against late, each way, plus money in against money out."""
    timing: dict[str, float] = {}
    for model, side in ((Sale, "in"), (Purchase, "out")):
        ref = Payment.sale_id if model is Sale else Payment.purchase_id
        live = (model.business_id == business_id, model.status != "cancelled")
        # Money that arrived after the day of the document, by whether it beat
        # the deadline. Payments taken on the day itself were never credit.
        paid = db.execute(
            select(
                func.coalesce(func.sum(Payment.amount).filter(Payment.date <= model.due_date), 0.0),
                func.coalesce(func.sum(Payment.amount).filter(Payment.date > model.due_date), 0.0),
            )
            .select_from(Payment)
            .join(model, ref == model.id)
            .where(*live, Payment.reason.in_(("payment", "settlement")), Payment.date >= since)
        ).one()
        # What is still owed: on time until its deadline passes.
        open_due = func.greatest(model.total - model.amount_paid, 0.0)
        owed = db.execute(
            select(
                func.coalesce(func.sum(open_due).filter(model.due_date >= now), 0.0),
                func.coalesce(func.sum(open_due).filter(model.due_date < now), 0.0),
            ).where(*live)
        ).one()
        timing[f"on_time_{side}"] = float(paid[0]) + float(owed[0])
        timing[f"late_{side}"] = float(paid[1]) + float(owed[1])

    cash_in = db.scalar(
        select(func.coalesce(func.sum(Payment.amount), 0.0))
        .select_from(Payment)
        .join(Sale, Payment.sale_id == Sale.id)
        .where(Sale.business_id == business_id, Sale.status != "cancelled", Payment.date >= since)
    )
    paid_out = db.scalar(
        select(func.coalesce(func.sum(Payment.amount), 0.0))
        .select_from(Payment)
        .join(Purchase, Payment.purchase_id == Purchase.id)
        .where(
            Purchase.business_id == business_id,
            Purchase.status != "cancelled",
            Payment.date >= since,
        )
    )
    expenses = db.scalar(
        select(func.coalesce(func.sum(Expense.amount), 0.0)).where(
            Expense.business_id == business_id, Expense.date >= since
        )
    )
    return CashInputs(
        on_time_in=timing["on_time_in"],
        late_in=timing["late_in"],
        on_time_out=timing["on_time_out"],
        late_out=timing["late_out"],
        cash_in=float(cash_in or 0),
        cash_out=float(paid_out or 0) + float(expenses or 0),
    )
