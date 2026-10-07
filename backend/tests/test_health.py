"""Business health: the four scores, the overall, and the numbers behind them.

Two halves. The first exercises the pure scoring functions with hand-built
inputs, so every threshold in docs/business-health.md is pinned without a
database. The second builds a business through the API, with back-dated sales,
purchases and expenses, and checks the gathered inputs to the rupee, which is
what proves the SQL feeds the formulas what they claim to read.

Several tests pin a case the score this replaced got wrong, and their
docstrings say what it used to show. The end-to-end ones fail against it.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy import update

from app.health import (
    WEIGHTS,
    CashInputs,
    HealthInputs,
    InventoryInputs,
    ProfitInputs,
    RevenueInputs,
    cash_flow_checks,
    overall_score,
    score,
    score_cash_flow,
    score_inventory,
    score_profitability,
    score_revenue,
)


def inventory(**kw) -> InventoryInputs:
    base = {
        "product_count": 1,
        "weighted_available": 0.0,
        "sales_weight": 0.0,
        "plain_available": 1.0,
        "stock_value": 0.0,
        "dead_stock_value": 0.0,
    }
    return InventoryInputs(**{**base, **kw})


def revenue(**kw) -> RevenueInputs:
    base = {
        "has_sales": True,
        "recent": 0.0,
        "baseline": 0.0,
        "baseline_days": 90.0,
        "baseline_count": 20,
    }
    return RevenueInputs(**{**base, **kw})


def cash(**kw) -> CashInputs:
    base = {
        "on_time_in": 0.0,
        "late_in": 0.0,
        "on_time_out": 0.0,
        "late_out": 0.0,
        "cash_in": 0.0,
        "cash_out": 0.0,
    }
    return CashInputs(**{**base, **kw})


# ---------------------------------------------------------------------------
# Inventory
# ---------------------------------------------------------------------------
def test_inventory_has_no_score_without_products():
    """It used to be 100: a business with nothing to stock scored perfect."""
    assert score_inventory(inventory(product_count=0, plain_available=0)) is None


def test_inventory_all_in_stock_and_moving_is_perfect():
    assert score_inventory(inventory(weighted_available=500, sales_weight=500)) == 100


def test_a_best_seller_running_out_costs_more_than_a_slow_line():
    # Two products: one is 90% of sales, the other 10%. One of them is out.
    best_seller_out = inventory(product_count=2, weighted_available=100, sales_weight=1000)
    slow_line_out = inventory(product_count=2, weighted_available=900, sales_weight=1000)
    assert score_inventory(best_seller_out) == 37  # 0.7 * 0.1 + 0.3
    assert score_inventory(slow_line_out) == 93  # 0.7 * 0.9 + 0.3


def test_low_stock_counts_half_and_out_of_stock_counts_nothing():
    low = inventory(weighted_available=0.5 * 200, sales_weight=200)
    out = inventory(weighted_available=0, sales_weight=200)
    assert score_inventory(low) == 65  # 0.7 * 0.5 + 0.3
    assert score_inventory(out) == 30


def test_with_no_recent_sales_every_product_counts_once():
    assert score_inventory(inventory(product_count=4, plain_available=2)) == 65


def test_dead_stock_drags_the_score_down():
    # Everything available, but half the stock value has not sold in 90 days.
    i = inventory(
        weighted_available=100, sales_weight=100, stock_value=10_000, dead_stock_value=5_000
    )
    assert score_inventory(i) == 85  # 0.7 + 0.3 * 0.5


def test_stock_with_no_recorded_cost_is_not_called_dead():
    assert score_inventory(inventory(stock_value=0, dead_stock_value=0)) == 100


# ---------------------------------------------------------------------------
# Revenue
# ---------------------------------------------------------------------------
def test_revenue_has_no_score_without_sales():
    assert score_revenue(revenue(has_sales=False)) is None


def test_revenue_has_no_score_until_there_is_a_baseline_to_compare():
    assert score_revenue(revenue(recent=5000, baseline=900, baseline_days=10)) is None
    assert score_revenue(revenue(recent=5000, baseline=900, baseline_days=14)) is not None


def test_a_business_that_stopped_selling_scores_zero():
    """It used to score 60, "Fair", for having sold nothing in a month."""
    assert score_revenue(revenue(recent=0, baseline=0)) == 0


@pytest.mark.parametrize(
    ("recent", "expected"),
    [
        (1000, 75),  # flat
        (1050, 80),  # +5%
        (1250, 100),  # +25% reaches the top
        (2000, 100),  # and stays there
        (950, 70),  # -5% is still healthy
        (650, 40),  # -35% is the edge of at risk
        (500, 25),  # -50%
        (0, 0),  # sold nothing this month
    ],
)
def test_one_point_per_percent_from_75_at_flat(recent, expected):
    # A 90-day baseline of 3,000 is 1,000 a month.
    assert score_revenue(revenue(recent=recent, baseline=3000)) == expected


def test_a_handful_of_sales_cannot_swing_revenue_to_the_top():
    """Going from 500 to 1,000 on a single invoice used to score 100."""
    thin = revenue(recent=1000, baseline=1500, baseline_count=1)  # +100%, 1 sale
    busy = revenue(recent=1000, baseline=1500, baseline_count=20)
    assert score_revenue(thin) == 80  # growth scaled by 1/20
    assert score_revenue(busy) == 100


def test_a_young_business_is_compared_on_the_days_it_existed():
    # 20 days of baseline worth 2,000 is 3,000 a month, so 3,000 now is flat.
    assert score_revenue(revenue(recent=3000, baseline=2000, baseline_days=20)) == 75


def test_selling_again_after_a_long_gap_reads_as_flat():
    assert score_revenue(revenue(recent=800, baseline=0, baseline_count=0)) == 75


# ---------------------------------------------------------------------------
# Profitability
# ---------------------------------------------------------------------------
def test_profitability_has_no_score_without_sales():
    assert score_profitability(ProfitInputs(net_sales=0, cogs=0, expenses=500)) is None


@pytest.mark.parametrize(
    ("cogs", "expenses", "expected"),
    [
        (700, 300, 40),  # break-even
        (700, 250, 70),  # 5% net margin
        (700, 200, 100),  # 10%
        (500, 100, 100),  # 40%, capped
        (700, 350, 10),  # -5%
        (800, 300, 0),  # -10%
    ],
)
def test_net_margin_bands(cogs, expenses, expected):
    assert score_profitability(ProfitInputs(1000, cogs, expenses)) == expected


def test_selling_below_cost_is_unprofitable_even_with_no_expenses():
    """The expense score this replaced ignored cost of goods, so this scored 100."""
    assert score_profitability(ProfitInputs(net_sales=1000, cogs=1100, expenses=0)) == 0


# ---------------------------------------------------------------------------
# Cash flow
# ---------------------------------------------------------------------------
def test_cash_flow_has_no_score_with_nothing_to_measure():
    assert score_cash_flow(cash()) is None
    assert cash_flow_checks(cash()) == {"collecting": None, "paying": None, "movement": None}


def test_a_cash_only_shop_is_judged_on_money_in_against_money_out():
    """No credit in either direction, so the only check left is the third."""
    assert score_cash_flow(cash(cash_in=100_000, cash_out=80_000)) == 100  # kept a fifth
    assert score_cash_flow(cash(cash_in=100_000, cash_out=100_000)) == 50  # break-even
    assert score_cash_flow(cash(cash_in=100_000, cash_out=110_000)) == 25
    assert score_cash_flow(cash(cash_in=100_000, cash_out=120_000)) == 0


def test_money_going_out_with_nothing_coming_in_is_the_worst_case():
    assert score_cash_flow(cash(cash_out=5_000)) == 0


def test_customers_paying_by_the_deadline_is_perfect_collection():
    assert score_cash_flow(cash(on_time_in=50_000)) == 100


def test_a_pile_of_overdue_invoices_is_not_a_strength():
    """Ten lakh owed, all past its deadline. Two versions ago this scored 95
    for being owed so much."""
    assert score_cash_flow(cash(late_in=1_000_000)) == 0


def test_three_rupees_in_four_on_time_scores_seventy_five():
    assert score_cash_flow(cash(on_time_in=300, late_in=100)) == 75


def test_paying_suppliers_late_is_a_warning_sign_of_its_own():
    """Customers all on time, but the shop is behind with its suppliers."""
    assert score_cash_flow(cash(on_time_in=10_000, late_out=4_000)) == 50


def test_owing_a_supplier_a_little_is_not_a_crisis():
    """A bill not yet due, and a shop keeping a tenth of what comes in. The
    ratio score two versions ago gave this 40, its lowest."""
    c = cash(on_time_out=5_000, cash_in=50_000, cash_out=45_000)
    assert score_cash_flow(c) == 88  # paying 1, movement 0.75


def test_the_three_checks_are_averaged():
    c = cash(on_time_in=300, late_in=100, on_time_out=50, late_out=50, cash_in=100, cash_out=100)
    assert cash_flow_checks(c) == {"collecting": 0.75, "paying": 0.5, "movement": 0.5}
    assert score_cash_flow(c) == 58


# ---------------------------------------------------------------------------
# Overall
# ---------------------------------------------------------------------------
def test_the_weights_add_up_to_a_hundred():
    assert sum(WEIGHTS.values()) == 100


def test_overall_is_the_weighted_average():
    parts = {"cashFlow": 80, "profitability": 60, "revenue": 70, "inventory": 90}
    assert overall_score(parts) == 73  # (2400 + 1800 + 1750 + 1350) / 100


def test_a_part_without_data_drops_out_and_the_rest_reweight():
    parts = {"cashFlow": 80, "profitability": 60, "revenue": 70, "inventory": None}
    assert overall_score(parts) == 70  # 5950 / 85


@pytest.mark.parametrize(
    ("present", "has_overall"),
    [
        ({"inventory", "revenue"}, False),  # 40
        ({"inventory", "cashFlow"}, False),  # 45
        ({"cashFlow", "profitability"}, True),  # 60
        ({"cashFlow", "revenue"}, True),  # 55
    ],
)
def test_at_least_half_the_weight_needs_data(present, has_overall):
    parts = {k: (80 if k in present else None) for k in WEIGHTS}
    assert (overall_score(parts) is not None) is has_overall


@pytest.mark.parametrize(
    ("weakest", "expected"),
    [
        (0, 30),  # one part at zero: the business is at risk
        (10, 40),  # one part at risk keeps the total at fair, at best
        (35, 65),
        (40, 70),  # every part at least fair: healthy is reachable
        (60, 88),  # far enough up that the cap no longer bites
    ],
)
def test_one_bad_part_cannot_hide_behind_three_good_ones(weakest, expected):
    """The old plain average let a cash crisis read as "Healthy"."""
    parts = {"cashFlow": weakest, "profitability": 100, "revenue": 100, "inventory": 100}
    assert overall_score(parts) == expected


def test_a_brand_new_business_has_no_score_at_all():
    """It used to show 85, "Healthy", before a single thing was recorded."""
    empty = HealthInputs(
        inventory=inventory(product_count=0, plain_available=0),
        revenue=revenue(has_sales=False, baseline_days=0, baseline_count=0),
        profit=ProfitInputs(0, 0, 0),
        cash=cash(),
    )
    assert score(empty) == {
        "overall": None,
        "inventory": None,
        "revenue": None,
        "profitability": None,
        "cashFlow": None,
    }


# ---------------------------------------------------------------------------
# Through the API and the database
# ---------------------------------------------------------------------------
def _sign_up(client) -> str:
    r = client.post(
        "/api/auth/sign-up",
        json={
            "businessName": f"Health Check {uuid.uuid4().hex[:6]}",
            "name": "Health Owner",
            "email": f"health-{uuid.uuid4().hex[:10]}@smoketest.dev",
            "password": "health1234",
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["business"]["id"]


def _post(client, path: str, body: dict) -> str:
    r = client.post(path, json=body)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _ago(days: int) -> str:
    return (datetime.now() - timedelta(days=days)).isoformat(timespec="seconds")


def test_a_new_business_dashboard_shows_no_score(fresh_client):
    _sign_up(fresh_client)
    health = fresh_client.get("/api/dashboard").json()["health"]
    assert health == {
        "overall": None,
        "inventory": None,
        "revenue": None,
        "profitability": None,
        "cashFlow": None,
    }


def test_products_alone_are_not_enough_for_an_overall(fresh_client):
    _sign_up(fresh_client)
    _post(fresh_client, "/api/products", {"name": "Soap", "stock": 40, "lowStockThreshold": 5})
    health = fresh_client.get("/api/dashboard").json()["health"]
    assert health["inventory"] == 100
    assert health["overall"] is None


def test_credit_sold_to_a_named_customer_is_counted_once(fresh_client):
    """The dashboard added each unpaid invoice on top of the customer balance
    that already held it, so this receivable showed as 236, not 118."""
    _sign_up(fresh_client)
    customer = _post(fresh_client, "/api/parties", {"type": "customer", "name": "Anita"})
    soap = _post(fresh_client, "/api/products", {"name": "Soap", "stock": 10})
    _post(
        fresh_client,
        "/api/sales",
        {
            "partyId": customer,
            "items": [{"productId": soap, "description": "Soap", "quantity": 1, "unitPrice": 100}],
        },
    )
    totals = fresh_client.get("/api/dashboard").json()["totals"]
    assert totals["receivable"] == 118
    assert fresh_client.get("/api/parties").json()["stats"]["receivable"] == 118


def test_every_input_and_score_from_a_real_ledger(fresh_client):
    """One business, built to known numbers. The arithmetic for each expected
    value is written out beside it."""
    from app.core.db import SessionLocal
    from app.health import gather, outstanding_balances
    from app.models import Product

    c = fresh_client
    business_id = uuid.UUID(_sign_up(c))  # GST defaults to 18%

    customer = _post(
        c, "/api/parties", {"type": "customer", "name": "Anita", "openingBalance": 100}
    )
    supplier = _post(c, "/api/parties", {"type": "supplier", "name": "ABC Suppliers"})
    rice = _post(
        c,
        "/api/products",
        {
            "name": "Rice",
            "purchasePrice": 100,
            "sellingPrice": 150,
            "stock": 100,
            "lowStockThreshold": 10,
        },
    )
    oil = _post(
        c,
        "/api/products",
        {
            "name": "Oil",
            "purchasePrice": 50,
            "sellingPrice": 80,
            "stock": 5,
            "lowStockThreshold": 5,
        },
    )
    old = _post(
        c,
        "/api/products",
        {"name": "Old line", "purchasePrice": 20, "stock": 10, "lowStockThreshold": 2},
    )
    with SessionLocal() as db:
        # Stocked 200 days ago and never sold since: dead stock.
        db.execute(
            update(Product)
            .where(Product.id == uuid.UUID(old))
            .values(created_at=datetime.now() - timedelta(days=200))
        )
        db.commit()

    def sale(days, product, qty, price, *, paid, party=None):
        total = round(qty * price * 1.18, 2)
        return _post(
            c,
            "/api/sales",
            {
                "partyId": party,
                "items": [
                    {"productId": product, "description": "x", "quantity": qty, "unitPrice": price}
                ],
                "amountPaid": total if paid else 0,
                "date": _ago(days),
            },
        )

    def pay(path, amount, days):
        r = c.post(path, json={"amount": amount, "date": _ago(days)})
        assert r.status_code == 200, r.text

    # Baseline window (30 to 120 days ago): four sales of 177 each. Every
    # deadline is the default 30 days after the sale.
    sale(100, rice, 1, 150, paid=True)  # also older than the 90-day lookback
    sale(80, rice, 1, 150, paid=True)
    on_time = sale(60, rice, 1, 150, paid=False, party=customer)
    pay(f"/api/sales/{on_time}/payment", 177, days=50)  # due 30 days ago: on time
    late = sale(40, rice, 1, 150, paid=False, party=customer)
    pay(f"/api/sales/{late}/payment", 100, days=5)  # due 10 days ago: late, 77 overdue
    # Recent window: 354 owed by Anita, 472 owed by a walk-in, and Oil sells out.
    sale(10, rice, 2, 150, paid=False, party=customer)
    sale(5, oil, 5, 80, paid=False)
    # A cancelled sale must not count anywhere.
    cancelled = sale(3, rice, 1, 150, paid=True)
    assert c.post(f"/api/sales/{cancelled}/cancel").status_code == 200

    def purchase(days, qty, *, paid, party=None):
        body = {
            "partyId": party,
            "items": [
                {"productId": rice, "description": "Rice", "quantity": qty, "unitPrice": 100}
            ],
            "amountPaid": paid,
            "date": _ago(days),
        }
        return _post(c, "/api/purchases", body)

    bill = purchase(20, 10, paid=500, party=supplier)  # 1,180 billed, due in 10 days
    pay(f"/api/purchases/{bill}/payment", 200, days=10)  # on time, 480 still owed
    purchase(45, 5, paid=0)  # 590 on a bill with no supplier, due 15 days ago

    for days, amount in ((20, 300), (100, 1000)):  # the second is outside 90 days
        _post(c, "/api/expenses", {"description": "Rent", "amount": amount, "date": _ago(days)})

    with SessionLocal() as db:
        receivable, payable = outstanding_balances(db, business_id)
        inputs = gather(db, business_id)

    # Anita: 100 opening + 177 - 177 + 177 - 100 + 354 = 531, plus the 472
    # walk-in. Each once.
    assert receivable == pytest.approx(1003)
    # ABC: 480, plus the 590 bill with no supplier.
    assert payable == pytest.approx(1070)

    # Credit that was, or still is, within its deadline: the 177 paid at day
    # 50, and the 354 and 472 not yet due. Late: the 100 paid after the
    # deadline and the 77 still owed past it.
    assert inputs.cash.on_time_in == pytest.approx(177 + 354 + 472)
    assert inputs.cash.late_in == pytest.approx(100 + 77)
    # Suppliers: 200 paid in time and 480 not yet due; 590 past its deadline.
    assert inputs.cash.on_time_out == pytest.approx(200 + 480)
    assert inputs.cash.late_out == pytest.approx(590)
    # Money that moved in the last 90 days. The 177 taken at the day-100 sale
    # is outside the window and the cancelled sale's 177 is not money.
    assert inputs.cash.cash_in == pytest.approx(177 + 177 + 100)
    assert inputs.cash.cash_out == pytest.approx(500 + 200 + 300)
    checks = cash_flow_checks(inputs.cash)
    assert checks["collecting"] == pytest.approx(1003 / 1180)
    assert checks["paying"] == pytest.approx(680 / 1270)
    assert checks["movement"] == 0  # 454 in, 1,000 out

    assert inputs.profit.net_sales == pytest.approx(1150)  # 1357 less 207 GST
    assert inputs.profit.cogs == pytest.approx(5 * 100 + 5 * 50)
    assert inputs.profit.expenses == pytest.approx(300)

    assert inputs.revenue.recent == pytest.approx(354 + 472)
    assert inputs.revenue.baseline == pytest.approx(177 * 4)
    assert inputs.revenue.baseline_count == 4
    # Selling began 100 days ago, so the baseline has 70 days of history.
    assert inputs.revenue.baseline_days == pytest.approx(70, abs=0.1)

    assert inputs.inventory.product_count == 3
    assert inputs.inventory.sales_weight == pytest.approx(750 + 400)  # rice, oil
    assert inputs.inventory.weighted_available == pytest.approx(750)  # oil is out
    assert inputs.inventory.plain_available == pytest.approx(2)
    # Rice: 100 - 6 sold + 15 bought = 109 at 100. Old line: 10 at 20.
    assert inputs.inventory.stock_value == pytest.approx(10_900 + 200)
    assert inputs.inventory.dead_stock_value == pytest.approx(200)

    body = c.get("/api/dashboard").json()
    assert body["health"] == {
        "inventory": 75,  # 0.7 * 750/1150 + 0.3 * (1 - 200/11100)
        "revenue": 100,  # +172% on a 4-sale baseline, scaled by 4/20, still past +25%
        "profitability": 92,  # 100 / 1150 = 8.7% margin
        "cashFlow": 46,  # (0.850 collecting + 0.535 paying + 0 movement) / 3
        "overall": 76,  # weighted average is 77.65, capped at 46 + 30
    }
    assert body["totals"]["receivable"] == 1003
    assert body["totals"]["payable"] == 1070
    # All-time: 1,534 of sales less 234 GST less 850 cost of goods.
    assert body["totals"]["grossProfit"] == 450

    # The Parties page still totals the named parties only.
    assert c.get("/api/parties").json()["stats"] == {"receivable": 531, "payable": 480}

    # And the list shows which invoice is the late one.
    rows = {r["id"]: r for r in c.get("/api/sales").json()["rows"]}
    assert rows[late]["overdue"] is True
    assert rows[on_time]["overdue"] is False
