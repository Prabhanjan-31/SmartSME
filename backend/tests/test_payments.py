"""Dated payments and payment deadlines.

A payment used to be a number that went up. Now it is a ledger row with a
date, every invoice and bill carries the day its balance is expected, and that
deadline comes from the party, or the business, or a hand edit on the one
document. These tests go through the API and read back what was written.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest

from app.domain.payments import payment_moment

from .test_health import _ago, _post, _sign_up


def _settings(client) -> dict:
    return client.get("/api/settings").json()["business"]


def _set_credit_days(client, days: int) -> None:
    body = {**_settings(client), "creditDays": days}
    assert client.put("/api/settings", json=body).status_code == 200, body


def _sale(client, *, party=None, paid=0.0, days_ago=0, product=None, qty=1, price=100):
    body = {
        "partyId": party,
        "items": [
            {"productId": product, "description": "Soap", "quantity": qty, "unitPrice": price}
        ],
        "amountPaid": paid,
    }
    if days_ago:
        body["date"] = _ago(days_ago)
    return _post(client, "/api/sales", body)


def _day(iso: str) -> str:
    return iso[:10]


def _days_between(a: str, b: str) -> int:
    return (datetime.fromisoformat(b) - datetime.fromisoformat(a)).days


@pytest.fixture
def shop(fresh_client):
    """A fresh business with one product, as the client that owns it."""
    _sign_up(fresh_client)
    product = _post(fresh_client, "/api/products", {"name": "Soap", "stock": 500})
    return fresh_client, product


# ---------------------------------------------------------------------------
# Deadlines
# ---------------------------------------------------------------------------
def test_a_new_invoice_is_due_thirty_days_after_its_date(shop):
    c, product = shop
    sale = c.get(f"/api/sales/{_sale(c, product=product)}").json()
    assert _days_between(sale["date"], sale["dueDate"]) == 30
    assert sale["overdue"] is False


def test_the_default_deadline_is_a_business_setting(shop):
    c, product = shop
    assert _settings(c)["creditDays"] == 30
    _set_credit_days(c, 45)
    sale = c.get(f"/api/sales/{_sale(c, product=product)}").json()
    assert _days_between(sale["date"], sale["dueDate"]) == 45

    # A sale already written keeps the deadline it was given.
    _set_credit_days(c, 30)
    assert _days_between(sale["date"], c.get(f"/api/sales/{sale['id']}").json()["dueDate"]) == 45


def test_a_party_can_have_longer_terms_than_the_default(shop):
    """The close friend: their invoices get 60 days without touching anyone
    else's."""
    c, product = shop
    friend = _post(c, "/api/parties", {"type": "customer", "name": "Ravi", "creditDays": 60})
    other = _post(c, "/api/parties", {"type": "customer", "name": "Anita"})
    assert c.get("/api/parties").json()["rows"][0]["creditDays"] in (60, None)

    for party, expected in ((friend, 60), (other, 30)):
        sale = c.get(f"/api/sales/{_sale(c, party=party, product=product)}").json()
        assert _days_between(sale["date"], sale["dueDate"]) == expected


def test_clearing_a_partys_terms_puts_them_back_on_the_default(shop):
    c, product = shop
    party = _post(c, "/api/parties", {"type": "customer", "name": "Ravi", "creditDays": 60})
    r = c.put(
        f"/api/parties/{party}", json={"type": "customer", "name": "Ravi", "creditDays": None}
    )
    assert r.status_code == 200, r.text
    sale = c.get(f"/api/sales/{_sale(c, party=party, product=product)}").json()
    assert _days_between(sale["date"], sale["dueDate"]) == 30


def test_terms_must_be_a_sensible_number_of_days(shop):
    c, _ = shop
    bad = c.post("/api/parties", json={"type": "customer", "name": "X", "creditDays": -1})
    assert bad.status_code == 400
    bad = c.put("/api/settings", json={**_settings(c), "creditDays": 5000})
    assert bad.status_code == 400


def test_one_invoice_can_be_extended_by_hand(shop):
    c, product = shop
    sale_id = _sale(c, product=product)
    later = (datetime.now() + timedelta(days=90)).strftime("%Y-%m-%d")
    r = c.patch(f"/api/sales/{sale_id}/due-date", json={"date": later})
    assert r.status_code == 200, r.text
    assert _day(c.get(f"/api/sales/{sale_id}").json()["dueDate"]) == later


def test_a_deadline_cannot_be_before_the_sale(shop):
    c, product = shop
    sale_id = _sale(c, product=product)
    earlier = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d")
    r = c.patch(f"/api/sales/{sale_id}/due-date", json={"date": earlier})
    assert r.status_code == 400
    assert "before" in r.json()["detail"]


def test_moving_the_sale_date_moves_the_deadline_with_it(shop):
    c, product = shop
    sale_id = _sale(c, product=product)
    before = c.get(f"/api/sales/{sale_id}").json()
    new_date = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d")
    assert c.patch(f"/api/sales/{sale_id}/date", json={"date": new_date}).status_code == 200
    after = c.get(f"/api/sales/{sale_id}").json()
    assert _day(after["date"]) == new_date
    assert _days_between(after["date"], after["dueDate"]) == _days_between(
        before["date"], before["dueDate"]
    )


def test_an_unpaid_invoice_reads_overdue_once_its_day_has_passed(shop):
    c, product = shop
    overdue = _sale(c, product=product, days_ago=40)  # due 10 days ago
    fresh = _sale(c, product=product, days_ago=5)
    paid = _sale(c, product=product, days_ago=40, paid=118)
    rows = {r["id"]: r for r in c.get("/api/sales").json()["rows"]}
    assert rows[overdue]["overdue"] is True
    assert rows[fresh]["overdue"] is False
    assert rows[paid]["overdue"] is False, "nothing is owed, so nothing is late"

    dash = c.get("/api/dashboard").json()["recentSales"]
    assert {r["id"]: r["overdue"] for r in dash}[overdue] is True


def test_a_party_sees_which_of_its_documents_are_overdue(shop):
    c, product = shop
    party = _post(c, "/api/parties", {"type": "customer", "name": "Anita"})
    _sale(c, party=party, product=product, days_ago=40)
    _sale(c, party=party, product=product, days_ago=5)
    row = next(r for r in c.get("/api/parties").json()["rows"] if r["id"] == party)
    flags = sorted(d["overdue"] for d in row["outstanding"])
    assert flags == [False, True]
    assert all("dueDate" in d for d in row["outstanding"])


def test_purchases_get_the_same_treatment(shop):
    c, product = shop
    supplier = _post(c, "/api/parties", {"type": "supplier", "name": "ABC", "creditDays": 15})
    pur_id = _post(
        c,
        "/api/purchases",
        {
            "partyId": supplier,
            "items": [
                {"productId": product, "description": "Soap", "quantity": 10, "unitPrice": 50}
            ],
            "amountPaid": 200,
        },
    )
    pur = c.get(f"/api/purchases/{pur_id}").json()
    assert _days_between(pur["date"], pur["dueDate"]) == 15
    assert [(p["reason"], p["amount"]) for p in pur["payments"]] == [("purchase", 200)]

    later = (datetime.now() + timedelta(days=60)).strftime("%Y-%m-%d")
    assert c.patch(f"/api/purchases/{pur_id}/due-date", json={"date": later}).status_code == 200
    assert _day(c.get(f"/api/purchases/{pur_id}").json()["dueDate"]) == later


def test_only_a_manager_can_change_a_deadline(employee_client, client, workspace):
    sale_id = _post(
        client,
        "/api/sales",
        {
            "partyId": workspace["customerId"],
            "items": [
                {
                    "productId": workspace["productId"],
                    "description": "Cooking Oil",
                    "quantity": 1,
                    "unitPrice": 140,
                }
            ],
            "amountPaid": 0,
        },
    )
    later = (datetime.now() + timedelta(days=60)).strftime("%Y-%m-%d")
    assert (
        employee_client.patch(f"/api/sales/{sale_id}/due-date", json={"date": later}).status_code
        == 403
    )
    assert client.patch(f"/api/sales/{sale_id}/due-date", json={"date": later}).status_code == 200


# ---------------------------------------------------------------------------
# The ledger
# ---------------------------------------------------------------------------
def test_money_taken_at_the_sale_is_dated_on_the_sale(shop):
    c, product = shop
    sale_id = _sale(c, product=product, paid=50, days_ago=7)
    sale = c.get(f"/api/sales/{sale_id}").json()
    assert len(sale["payments"]) == 1
    row = sale["payments"][0]
    assert row["reason"] == "sale"
    assert row["amount"] == 50
    assert _day(row["date"]) == _day(sale["date"])


def test_a_cash_sale_with_nothing_paid_has_no_ledger_row(shop):
    c, product = shop
    assert c.get(f"/api/sales/{_sale(c, product=product)}").json()["payments"] == []


def test_a_later_payment_is_dated_when_the_money_came(shop):
    c, product = shop
    sale_id = _sale(c, product=product, days_ago=20)
    when = (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d")
    r = c.post(f"/api/sales/{sale_id}/payment", json={"amount": 40, "date": when})
    assert r.status_code == 200, r.text
    r = c.post(f"/api/sales/{sale_id}/payment", json={"amount": 78})  # today
    assert r.status_code == 200, r.text

    sale = c.get(f"/api/sales/{sale_id}").json()
    assert sale["paymentStatus"] == "paid"
    assert [(p["reason"], p["amount"], _day(p["date"])) for p in sale["payments"]] == [
        ("payment", 40, when),
        ("payment", 78, datetime.now().strftime("%Y-%m-%d")),
    ]


def test_a_payment_cannot_be_dated_before_the_sale(shop):
    c, product = shop
    sale_id = _sale(c, product=product, days_ago=2)
    when = (datetime.now() - timedelta(days=9)).strftime("%Y-%m-%d")
    r = c.post(f"/api/sales/{sale_id}/payment", json={"amount": 10, "date": when})
    assert r.status_code == 400
    assert "before" in r.json()["detail"]
    assert c.get(f"/api/sales/{sale_id}").json()["amountPaid"] == 0


def test_a_payment_can_be_dated_the_day_of_the_sale_whatever_the_clock_says(shop):
    """An order accepted from Telegram or email is stamped with the minute it
    was accepted, and a date picked in the payment dialog is stored as noon.
    Compared as instants, an invoice raised in the afternoon could not be paid
    on its own day: the report was an invoice dated 10 Nov that would only
    take a payment dated 11 Nov."""
    c, product = shop
    today = datetime.now().strftime("%Y-%m-%d")
    sale_id = _post(
        c,
        "/api/sales",
        {
            "items": [
                {"productId": product, "description": "Soap", "quantity": 1, "unitPrice": 100}
            ],
            "date": f"{today}T23:59:00",
        },
    )
    r = c.post(f"/api/sales/{sale_id}/payment", json={"amount": 40, "date": today})
    assert r.status_code == 200, r.text

    sale = c.get(f"/api/sales/{sale_id}").json()
    assert sale["amountPaid"] == 40
    # Stored no earlier than the invoice, so the ledger reads in order.
    assert [p["date"] for p in sale["payments"]] == [sale["date"]]


def test_a_payment_cannot_be_dated_after_today(shop):
    c, product = shop
    sale_id = _sale(c, product=product, days_ago=2)
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    r = c.post(f"/api/sales/{sale_id}/payment", json={"amount": 10, "date": tomorrow})
    assert r.status_code == 400
    assert "future" in r.json()["detail"]
    assert c.get(f"/api/sales/{sale_id}").json()["amountPaid"] == 0


def test_the_same_two_rules_hold_for_a_bill(shop):
    c, product = shop
    today = datetime.now().strftime("%Y-%m-%d")
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    bill = _post(
        c,
        "/api/purchases",
        {
            "items": [
                {"productId": product, "description": "Soap", "quantity": 1, "unitPrice": 100}
            ],
            "date": f"{today}T23:59:00",
        },
    )
    late = c.post(f"/api/purchases/{bill}/payment", json={"amount": 10, "date": tomorrow})
    assert late.status_code == 400 and "future" in late.json()["detail"]
    same_day = c.post(f"/api/purchases/{bill}/payment", json={"amount": 10, "date": today})
    assert same_day.status_code == 200, same_day.text
    assert c.get(f"/api/purchases/{bill}").json()["amountPaid"] == 10


def test_a_sale_dated_ahead_cannot_take_a_payment_yet(shop):
    """No day is both on or after the sale's and on or before today, so the
    answer says that instead of sending the shopkeeper round in a circle."""
    c, product = shop
    ahead = (datetime.now() + timedelta(days=3)).strftime("%Y-%m-%d")
    sale_id = _post(
        c,
        "/api/sales",
        {
            "items": [
                {"productId": product, "description": "Soap", "quantity": 1, "unitPrice": 100}
            ],
            "date": ahead,
        },
    )
    for date in (datetime.now().strftime("%Y-%m-%d"), ahead, None):
        body = {"amount": 10} if date is None else {"amount": 10, "date": date}
        r = c.post(f"/api/sales/{sale_id}/payment", json=body)
        assert r.status_code == 400, date
        assert "not arrived yet" in r.json()["detail"], date
    assert c.get(f"/api/sales/{sale_id}").json()["amountPaid"] == 0


NOON = datetime(2026, 11, 10, 12, 0)
MID_AFTERNOON = datetime(2026, 11, 10, 15, 42, 7)


@pytest.mark.parametrize(
    ("doc_date", "picked", "now", "stored"),
    [
        # The report: raised at 15:42 from Telegram, paid "10 Nov" in the dialog.
        (MID_AFTERNOON, NOON, datetime(2026, 11, 10, 16, 0), MID_AFTERNOON),
        # Typed into Smart Input, so both are noon. This always worked.
        (NOON, NOON, datetime(2026, 11, 10, 16, 0), NOON),
        # No date sent: the moment it was recorded.
        (NOON, None, datetime(2026, 11, 10, 16, 0), datetime(2026, 11, 10, 16, 0)),
        # No date sent, before noon, on a sale dated today.
        (NOON, None, datetime(2026, 11, 10, 9, 0), NOON),
        # A later day keeps the time it was given.
        (MID_AFTERNOON, datetime(2026, 11, 12, 12, 0), datetime(2026, 11, 14, 8, 0),
         datetime(2026, 11, 12, 12, 0)),
        # Today, a minute before midnight, is still today.
        (NOON, datetime(2026, 11, 14, 12, 0), datetime(2026, 11, 14, 23, 59),
         datetime(2026, 11, 14, 12, 0)),
    ],
)  # fmt: skip
def test_when_a_payment_is_recorded_as_made(doc_date, picked, now, stored):
    assert payment_moment(doc_date, picked, "sale", now) == stored


@pytest.mark.parametrize(
    ("doc_date", "picked", "now", "says"),
    [
        (MID_AFTERNOON, datetime(2026, 11, 9, 12, 0), datetime(2026, 11, 10, 16, 0), "before"),
        (MID_AFTERNOON, datetime(2026, 11, 9, 23, 59), datetime(2026, 11, 10, 16, 0), "before"),
        (NOON, datetime(2026, 11, 11, 12, 0), datetime(2026, 11, 10, 16, 0), "future"),
        # One minute into tomorrow is tomorrow.
        (NOON, datetime(2026, 11, 11, 0, 1), datetime(2026, 11, 10, 23, 59), "future"),
        (datetime(2026, 11, 13, 12, 0), NOON, datetime(2026, 11, 10, 16, 0), "not arrived yet"),
    ],
)
def test_when_a_payment_is_refused(doc_date, picked, now, says):
    with pytest.raises(ValueError, match=says):
        payment_moment(doc_date, picked, "sale", now)


def test_the_refusal_names_the_dates_involved():
    """ "Cannot be dated before the sale" left the shopkeeper to work out
    which date the sale had."""
    with pytest.raises(ValueError, match="10 Nov 2026"):
        payment_moment(MID_AFTERNOON, datetime(2026, 11, 9, 12, 0), "sale", MID_AFTERNOON)
    with pytest.raises(ValueError, match="Today is 10 Nov 2026"):
        payment_moment(NOON, datetime(2026, 11, 11, 12, 0), "sale", MID_AFTERNOON)


def test_overpaying_records_only_what_the_invoice_could_take(shop):
    c, product = shop
    sale_id = _sale(c, product=product, paid=100)  # 18 left on a 118 invoice
    assert c.post(f"/api/sales/{sale_id}/payment", json={"amount": 500}).status_code == 200
    sale = c.get(f"/api/sales/{sale_id}").json()
    assert sale["amountPaid"] == 118
    assert [p["amount"] for p in sale["payments"]] == [100, 18]


def test_settling_a_party_writes_one_row_per_document(shop):
    c, product = shop
    party = _post(c, "/api/parties", {"type": "customer", "name": "Anita"})
    ids = [_sale(c, party=party, product=product) for _ in range(2)]
    settled = c.post(f"/api/parties/{party}/settle").json()
    assert settled["count"] == 2
    for sale_id in ids:
        rows = c.get(f"/api/sales/{sale_id}").json()["payments"]
        assert [(p["reason"], p["amount"]) for p in rows] == [("settlement", 118)]


def test_settling_everything_covers_walk_in_sales_too(shop):
    c, product = shop
    walk_in = _sale(c, product=product)
    assert c.post("/api/parties/settle-all/receivable").json()["count"] >= 1
    rows = c.get(f"/api/sales/{walk_in}").json()["payments"]
    assert [p["reason"] for p in rows] == ["settlement"]


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------
def test_top_suppliers_rank_by_what_was_bought(shop):
    c, product = shop
    big = _post(c, "/api/parties", {"type": "supplier", "name": "Big Wholesale"})
    small = _post(c, "/api/parties", {"type": "supplier", "name": "Corner Supply"})
    for supplier, qty in ((small, 1), (big, 10), (big, 5)):
        _post(
            c,
            "/api/purchases",
            {
                "partyId": supplier,
                "items": [
                    {"productId": product, "description": "Soap", "quantity": qty, "unitPrice": 50}
                ],
            },
        )
    # A bill with no supplier has nobody to rank.
    _post(
        c,
        "/api/purchases",
        {"items": [{"productId": product, "description": "Soap", "quantity": 99, "unitPrice": 50}]},
    )
    top = c.get("/api/reports/overview").json()["topSuppliers"]
    assert [(t["label"], t["value"]) for t in top] == [
        ("Big Wholesale", 885),
        ("Corner Supply", 59),
    ]


@pytest.mark.parametrize("metric", ["sales", "purchases", "expenses"])
def test_the_trend_chart_can_show_each_money_stream(shop, metric):
    c, product = shop
    _sale(c, product=product, paid=118)
    _post(
        c,
        "/api/purchases",
        {"items": [{"productId": product, "description": "Soap", "quantity": 2, "unitPrice": 50}]},
    )
    _post(c, "/api/expenses", {"description": "Rent", "amount": 700})
    r = c.get("/api/reports/revenue", params={"days": 7, "metric": metric})
    assert r.status_code == 200
    body = r.json()
    assert body["metric"] == metric
    assert (
        sum(p["value"] for p in body["points"])
        == {
            "sales": 118,
            "purchases": 118,
            "expenses": 700,
        }[metric]
    )


def test_an_unknown_metric_falls_back_to_sales(shop):
    c, _ = shop
    assert c.get("/api/reports/revenue", params={"metric": "profit"}).json()["metric"] == "sales"


def test_a_cancelled_document_leaves_the_chart(shop):
    c, product = shop
    sale_id = _sale(c, product=product, paid=118)
    assert c.post(f"/api/sales/{sale_id}/cancel").status_code == 200
    r = c.get("/api/reports/revenue", params={"days": 7, "metric": "sales"}).json()
    assert sum(p["value"] for p in r["points"]) == 0


def test_the_shape_the_dashboard_relies_on(shop):
    c, product = shop
    _sale(c, product=product, paid=10)
    sale = c.get("/api/sales").json()["rows"][0]
    assert {"dueDate", "overdue", "due", "paymentStatus"} <= sale.keys()
    assert isinstance(uuid.UUID(sale["id"]), uuid.UUID)
