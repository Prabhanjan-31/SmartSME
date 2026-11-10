"""Unit tests for the pure domain logic (no database required).

Ports the original node:test cases for totals and adds coverage for the date,
discount and party-matching behaviour the Smart Input engine depends on.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from app.ai.nlp import heuristic_parse, parse_date_phrase, parse_discount
from app.core.security import hash_password, verify_password
from app.core.utils import group_number, money, parse_date_input, round2
from app.domain.line_items import clean_line_items
from app.domain.purchases import calculate_purchase_totals
from app.domain.sales import calculate_sale_totals
from app.models import Party, Product
from app.reports import resolve_period
from app.schemas import LineInput
from app.smart_input import best_match

# --- Totals ----------------------------------------------------------------


def test_amount_discount_reduces_subtotal_before_tax():
    t = calculate_sale_totals(100, 10, "amount", 10)
    assert t.discountAmount == 10
    assert t.tax == 9
    assert t.total == 99


def test_percentage_discount_reduces_subtotal_before_tax():
    t = calculate_sale_totals(1000, 18, "percentage", 10)
    assert t.discountAmount == 100
    assert t.tax == 162
    assert t.total == 1062


def test_no_discount_leaves_tax_on_full_subtotal():
    t = calculate_sale_totals(1000, 18)
    assert t.discountAmount == 0
    assert t.total == 1180


def test_purchase_discounts_match_sale_maths():
    s = calculate_sale_totals(1000, 18, "amount", 300)
    p = calculate_purchase_totals(1000, 18, "amount", 300)
    assert (s.discountAmount, s.tax, s.total) == (p.discountAmount, p.tax, p.total)


def test_discount_never_drives_the_total_negative():
    t = calculate_sale_totals(200, 18, "amount", 500)
    assert t.total == 0
    # The caller still rejects this; the maths must not produce a negative.
    assert t.discountAmount == 500


def test_round2_rounds_half_up():
    assert round2(1.005) == 1.01
    assert round2(2.675) == 2.68
    assert round2(-1.005) == -1.01


def test_money_formats_indian_grouping():
    assert money(123456.5, "INR") == "₹1,23,456.50"
    assert group_number(1000) == "1,000.00"


# --- Line items ------------------------------------------------------------


def test_clean_line_items_drops_blanks_and_keeps_valid():
    kept = clean_line_items(
        [
            LineInput(description="  ", quantity=5, unitPrice=10),
            LineInput(description="Rice", quantity=2, unitPrice=100),
        ]
    )
    assert len(kept) == 1
    assert kept[0].description == "Rice"


def test_clean_line_items_requires_at_least_one():
    with pytest.raises(ValueError, match="at least one line item"):
        clean_line_items([LineInput(description="", quantity=0, unitPrice=0)])


def test_clean_line_items_rejects_negative_price():
    with pytest.raises(ValueError, match="zero or more"):
        clean_line_items([LineInput(description="Rice", quantity=1, unitPrice=-5)])


# --- Dates -----------------------------------------------------------------

NOW = datetime(2026, 9, 6, 10, 0, 0)


@pytest.mark.parametrize(
    ("text", "want"),
    [
        ("i sold 4 Litres Cooking oil to Shreeharsha on 20th August 2026", "2026-08-20"),
        ("sold 3 bags to Kumar on 20 aug 2026", "2026-08-20"),
        ("sold 3 bags to Kumar on 3 sept", "2026-09-03"),
        ("sold 3 bags yesterday", "2026-09-05"),
        ("sold 3 bags today", "2026-09-06"),
        ("sold 3 bags day before yesterday", "2026-09-04"),
        ("sold 3 bags on 20/08/2026", "2026-08-20"),
        ("sold 3 bags on 2026-08-20", "2026-08-20"),
        ("sold 3 bags on august 20 2026", "2026-08-20"),
        ("sold 3 bags on aug 20", "2026-08-20"),
        ("Sold 10 rice bags to Kumar Traders", None),
        ("sold 31 feb 2026 bags", None),
    ],
)
def test_parse_date_phrase(text: str, want: str | None):
    assert parse_date_phrase(text, NOW) == want


def test_bare_day_month_in_future_rolls_back_a_year():
    assert parse_date_phrase("sold on 20 december", NOW) == "2025-12-20"


def test_month_like_quantity_is_not_a_date():
    assert parse_date_phrase("sell may 10 bags", NOW) is None


def test_parse_date_input_anchors_to_local_noon():
    d = parse_date_input("2026-08-20")
    assert d is not None
    assert (d.year, d.month, d.day, d.hour) == (2026, 8, 20, 12)
    assert parse_date_input("") is None
    assert parse_date_input("not-a-date") is None


# --- Discounts -------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "want"),
    [
        ("sell everything to anita stores at a discount of 10%", ("percentage", 10)),
        ("sell everything to anita at a discount of 300 rupees", ("amount", 300)),
        ("sell 5 bags to kumar 15% off", ("percentage", 15)),
        ("Sold 10 rice bags to Kumar Traders", ("none", 0)),
    ],
)
def test_parse_discount(text: str, want: tuple[str, float]):
    assert parse_discount(text.lower()) == want


# --- Heuristic parser ------------------------------------------------------


def test_heuristic_parses_a_full_sale_note():
    p = heuristic_parse("i sold 4 Litres Cooking oil to Shreeharsha on 20th August 2026")
    assert p.eventType == "SALE_CREATED"
    assert p.quantity == 4
    assert p.date == "2026-08-20"
    assert "shreeharsha" in (p.party or "").lower()
    assert "oil" in (p.product or "").lower()


def test_heuristic_detects_entire_inventory():
    p = heuristic_parse("sell the entire inventory to Anita Stores")
    assert p.allInventory is True
    assert p.eventType == "SALE_CREATED"


def test_heuristic_classifies_purchase_and_expense():
    assert (
        heuristic_parse("Purchase 50 sugar packets from ABC Suppliers").eventType
        == "PURCHASE_CREATED"
    )
    assert heuristic_parse("Paid electricity bill 3200").eventType == "EXPENSE_ADDED"


# --- Party / product matching ---------------------------------------------


def _parties() -> list[Party]:
    return [
        Party(name="Kumar Traders", type="customer"),
        Party(name="Anita Stores", type="customer"),
        Party(name="ABC Suppliers", type="supplier"),
    ]


@pytest.mark.parametrize("query", ["Anita Stores", "anita stores.", "ANITA  STORES", "Anita"])
def test_best_match_resolves_a_party(query: str):
    m = best_match(_parties(), query)
    assert m is not None and m.name == "Anita Stores"


def test_best_match_returns_none_for_unknown():
    assert best_match(_parties(), "Totally Unknown Shop") is None
    assert best_match(_parties(), None) is None


def test_best_match_works_for_products():
    products = [Product(name="Cooking Oil 1L"), Product(name="Rice Bag 25kg")]
    m = best_match(products, "cooking oil")
    assert m is not None and m.name == "Cooking Oil 1L"


# --- Report periods --------------------------------------------------------


def test_today_period_spans_one_day():
    start, end, label = resolve_period("today")
    assert label == "Today"
    assert (end - start).days == 0


def test_last_month_ends_before_this_month_starts():
    start, end, _ = resolve_period("last_month")
    now = datetime.now()
    assert end < datetime(now.year, now.month, 1)
    assert start <= end


def test_backwards_custom_range_is_swapped():
    start, end, _ = resolve_period("custom", "2026-03-10", "2026-03-01")
    assert start < end


# --- Passwords -------------------------------------------------------------


def test_password_round_trip_and_format():
    stored = hash_password("demo1234")
    assert stored.startswith("pbkdf2$")
    assert len(stored.split("$")) == 3
    assert verify_password("demo1234", stored)
    assert not verify_password("wrong", stored)
    assert not verify_password("demo1234", "garbage")


# --- The shop's clock ------------------------------------------------------
#
# A hosted server runs in UTC. Every date in the app is the server's local
# time, so for a shop in India "today" there is five and a half hours behind
# the shopkeeper's own, and a payment taken at one in the morning would be
# refused as dated tomorrow. `apply_timezone` puts the process on the shop's
# clock. Windows has no `tzset`, so the calls are stubbed and the test runs
# everywhere.


@pytest.fixture
def clock(monkeypatch):
    """A machine with a `tzset`, an empty environment, and a known zone."""
    from app.core import config

    # A plain dict, so nothing here reaches the real environment. (pytest
    # keeps a variable of its own in it, hence `.get("TZ")` below.)
    env: dict[str, str] = {}
    applied: list[str] = []
    monkeypatch.setattr(config.os, "environ", env)
    monkeypatch.setattr(config.time, "tzset", lambda: applied.append(env["TZ"]), raising=False)
    monkeypatch.setattr(config, "_zone_exists", lambda name: name == "Asia/Kolkata")
    return config, env, applied


def test_the_process_is_put_on_the_shop_clock(clock):
    config, env, applied = clock
    assert config.apply_timezone("Asia/Kolkata") == "Asia/Kolkata"
    assert env.get("TZ") == "Asia/Kolkata"
    assert applied == ["Asia/Kolkata"]


def test_a_time_zone_already_set_on_the_machine_wins(clock):
    config, env, applied = clock
    env["TZ"] = "Europe/London"
    assert config.apply_timezone("Asia/Kolkata") == "Europe/London"
    assert env.get("TZ") == "Europe/London"
    assert applied == []


@pytest.mark.parametrize("name", ["", "   ", "Asia/Nowhere"])
def test_a_blank_or_unknown_zone_leaves_the_machine_clock_alone(clock, name):
    """An unknown name is not an error to the C library. It quietly means UTC,
    which is the very thing being fixed, so it is never handed over."""
    config, env, applied = clock
    assert config.apply_timezone(name) is None
    assert "TZ" not in env
    assert applied == []


def test_the_default_zone_is_india():
    from app.core.config import Settings

    assert Settings.model_fields["app_timezone"].default == "Asia/Kolkata"
