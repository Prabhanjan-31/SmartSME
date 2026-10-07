"""How a payment was made: the mode, its identifier, and the extras.

The one rule that matters most is the card one. The server accepts the last
four digits and nothing longer, and refuses rather than truncates, so there
is no path by which a full card number ends up in the database.
"""

from __future__ import annotations

import pytest

from app.domain.payments import PAYMENT_MODES, clean_payment_mode

from .test_health import _post
from .test_payments import _sale, shop  # noqa: F401 - `shop` is a fixture


# ---------------------------------------------------------------------------
# The rules, with no database
# ---------------------------------------------------------------------------
def test_cash_needs_nothing_and_keeps_nothing():
    assert clean_payment_mode("cash", "stray text", {"bank": "x"}) == ("cash", None, None)


def test_no_mode_means_not_recorded():
    assert clean_payment_mode(None, "123", {}) == (None, None, None)
    assert clean_payment_mode("  ", None, None) == (None, None, None)


@pytest.mark.parametrize(
    ("mode", "needs"),
    [
        ("upi", "transaction ID"),
        ("card", "last four digits"),
        ("cheque", "cheque number"),
        ("bank_transfer", "UTR"),
        ("other", "description"),
    ],
)
def test_every_mode_but_cash_needs_its_identifier(mode, needs):
    with pytest.raises(ValueError, match=needs):
        clean_payment_mode(mode, "", {})


def test_a_full_card_number_is_refused_not_truncated():
    with pytest.raises(ValueError, match="last four digits"):
        clean_payment_mode("card", "4111111111111111", {})
    with pytest.raises(ValueError, match="last four digits"):
        clean_payment_mode("card", "41111", {})
    assert clean_payment_mode("card", " 4242 ", {}) == ("card", "4242", None)


def test_card_extras_are_checked():
    assert clean_payment_mode("card", "4242", {"cardType": "Credit", "approvalCode": "A1B2"}) == (
        "card",
        "4242",
        {"cardType": "credit", "approvalCode": "A1B2"},
    )
    with pytest.raises(ValueError, match="credit or debit"):
        clean_payment_mode("card", "4242", {"cardType": "amex"})


def test_cheque_keeps_bank_and_date_and_drops_what_it_does_not_know():
    assert clean_payment_mode(
        "cheque", "004512", {"bank": "HDFC Bank", "chequeDate": "2026-10-01", "upiId": "x"}
    ) == ("cheque", "004512", {"bank": "HDFC Bank", "chequeDate": "2026-10-01"})
    with pytest.raises(ValueError, match="yyyy-mm-dd"):
        clean_payment_mode("cheque", "004512", {"chequeDate": "1/10/2026"})
    with pytest.raises(ValueError, match="letters, digits"):
        clean_payment_mode("cheque", "no. 4512", {})


def test_unknown_modes_and_overlong_references_are_refused():
    with pytest.raises(ValueError, match="Unknown payment mode"):
        clean_payment_mode("bitcoin", "x", {})
    with pytest.raises(ValueError, match="too long"):
        clean_payment_mode("upi", "x" * 65, {})


def test_the_frontend_list_matches():
    """The keys `frontend/src/lib/payments.ts` offers must all be accepted."""
    assert set(PAYMENT_MODES) == {"cash", "upi", "card", "cheque", "bank_transfer", "other"}


# ---------------------------------------------------------------------------
# Through the API
# ---------------------------------------------------------------------------
def _pay(client, sale_id, **body):
    body.setdefault("amount", 10)
    return client.post(f"/api/sales/{sale_id}/payment", json=body)


def _ledger(client, sale_id):
    return client.get(f"/api/sales/{sale_id}").json()["payments"]


def test_cash_is_the_default(shop):  # noqa: F811
    c, product = shop
    sale_id = _sale(c, product=product)
    assert _pay(c, sale_id).status_code == 200
    (row,) = _ledger(c, sale_id)
    assert (row["mode"], row["reference"], row["details"]) == ("cash", None, {})


def test_a_upi_payment_keeps_its_transaction_id(shop):  # noqa: F811
    c, product = shop
    sale_id = _sale(c, product=product)
    r = _pay(c, sale_id, mode="upi")
    assert r.status_code == 400
    assert "transaction ID" in r.json()["detail"]
    assert _ledger(c, sale_id) == [], "nothing was recorded"

    r = _pay(c, sale_id, mode="upi", reference="326514789012", details={"upiId": "anita@okaxis"})
    assert r.status_code == 200, r.text
    (row,) = _ledger(c, sale_id)
    assert row["mode"] == "upi"
    assert row["reference"] == "326514789012"
    assert row["details"] == {"upiId": "anita@okaxis"}


def test_a_card_payment_stores_only_the_last_four_digits(shop):  # noqa: F811
    c, product = shop
    sale_id = _sale(c, product=product)
    r = _pay(c, sale_id, mode="card", reference="4111 1111 1111 1111")
    assert r.status_code == 400
    assert "never recorded" in r.json()["detail"]

    r = _pay(c, sale_id, mode="card", reference="1111", details={"cardType": "debit"})
    assert r.status_code == 200, r.text
    (row,) = _ledger(c, sale_id)
    assert (row["mode"], row["reference"], row["details"]) == (
        "card",
        "1111",
        {"cardType": "debit"},
    )


def test_a_cheque_payment_keeps_the_bank_and_the_cheque_date(shop):  # noqa: F811
    c, product = shop
    sale_id = _sale(c, product=product)
    r = _pay(
        c,
        sale_id,
        mode="cheque",
        reference="004512",
        details={"bank": "SBI", "chequeDate": "2026-10-01"},
    )
    assert r.status_code == 200, r.text
    (row,) = _ledger(c, sale_id)
    assert row["details"] == {"bank": "SBI", "chequeDate": "2026-10-01"}


def test_an_unknown_mode_is_refused(shop):  # noqa: F811
    c, product = shop
    sale_id = _sale(c, product=product)
    assert _pay(c, sale_id, mode="barter", reference="x").status_code == 400


def test_money_taken_at_the_sale_carries_the_mode_from_the_form(shop):  # noqa: F811
    c, product = shop
    sale_id = _post(
        c,
        "/api/sales",
        {
            "items": [
                {"productId": product, "description": "Soap", "quantity": 1, "unitPrice": 100}
            ],
            "amountPaid": 118,
            "paymentMode": "bank_transfer",
            "paymentReference": "SBIN526280012345",
            "paymentDetails": {"bank": "SBI"},
        },
    )
    (row,) = _ledger(c, sale_id)
    assert row["reason"] == "sale"
    assert (row["mode"], row["reference"], row["details"]) == (
        "bank_transfer",
        "SBIN526280012345",
        {"bank": "SBI"},
    )


def test_a_bad_reference_refuses_the_whole_sale(shop):  # noqa: F811
    c, product = shop
    before = c.get("/api/sales").json()["page"]["total"]
    r = c.post(
        "/api/sales",
        json={
            "items": [
                {"productId": product, "description": "Soap", "quantity": 1, "unitPrice": 100}
            ],
            "amountPaid": 118,
            "paymentMode": "card",
            "paymentReference": "4111111111111111",
        },
    )
    assert r.status_code == 400
    assert c.get("/api/sales").json()["page"]["total"] == before


def test_a_sale_published_without_a_mode_says_so(shop):  # noqa: F811
    """Smart Input and inbound orders do not know how the money came."""
    c, product = shop
    sale_id = _sale(c, product=product, paid=118)
    (row,) = _ledger(c, sale_id)
    assert row["mode"] is None
    assert row["reference"] is None


def test_settlements_record_no_mode(shop):  # noqa: F811
    c, product = shop
    party = _post(c, "/api/parties", {"type": "customer", "name": "Anita"})
    sale_id = _sale(c, party=party, product=product)
    assert c.post(f"/api/parties/{party}/settle").status_code == 200
    (row,) = _ledger(c, sale_id)
    assert row["reason"] == "settlement"
    assert row["mode"] is None


def test_purchases_take_a_mode_too(shop):  # noqa: F811
    c, product = shop
    pur_id = _post(
        c,
        "/api/purchases",
        {"items": [{"productId": product, "description": "Soap", "quantity": 2, "unitPrice": 50}]},
    )
    r = c.post(
        f"/api/purchases/{pur_id}/payment",
        json={"amount": 50, "mode": "cheque", "reference": "991100", "details": {"bank": "ICICI"}},
    )
    assert r.status_code == 200, r.text
    (row,) = c.get(f"/api/purchases/{pur_id}").json()["payments"]
    assert (row["mode"], row["reference"], row["details"]) == (
        "cheque",
        "991100",
        {"bank": "ICICI"},
    )
