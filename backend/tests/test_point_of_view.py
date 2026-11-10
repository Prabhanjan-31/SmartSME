"""Which side of the counter a note is written from.

"Anita Stores purchased 5 rice bags from us" was filed as a purchase from a
supplier called "Us", because the parser read the verb and nothing else. A
note is written by the shopkeeper about their own shop, so the question is
which way the goods moved. These tests pin that down for the built-in parser,
for a model's answer, and for the draft the shopkeeper finally sees.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app.ai import nlp
from app.ai.nlp import _prompt, heuristic_parse, point_of_view
from app.smart_input import ground_text

from .test_ai_mocked import fake_provider  # noqa: F401


# ---------------------------------------------------------------------------
# The built-in parser
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("note", "party"),
    [
        # The note that was reported.
        ("anita stores purchased 5 rice bags from us", "Anita Stores"),
        ("Anita Stores bought 5 rice bags from us", "Anita Stores"),
        ("Anita Stores has purchased 5 rice bags from our shop.", "Anita Stores"),
        ("Anita took 5 rice bags from us", "Anita"),
        ("yesterday anita stores bought 5 rice bags from us for cash", "Anita Stores"),
        # No "from us", but a named customer did the buying.
        ("Anita Stores bought 5 rice bags", "Anita Stores"),
        ("Kumar Traders purchased 5 rice bags", "Kumar Traders"),
        # Somebody bought, nobody in particular: a sale with no party on it.
        ("a customer bought 5 rice bags", None),
        # Hindi and Kannada, in Latin letters and in their own scripts.
        ("Anita ne humse 5 kg rice kharida", "Anita"),
        ("Anita ne 5 kg rice kharida", "Anita"),
        ("अनीता ने हमसे 5 किलो rice खरीदा", "अनीता"),
        ("ಅನಿತಾ ನಮ್ಮಿಂದ ೫ ಕಿಲೋ rice ಖರೀದಿಸಿದರು", "ಅನಿತಾ"),
    ],
)
def test_goods_that_left_the_shop_are_a_sale(note: str, party: str | None):
    parsed = heuristic_parse(note)
    assert parsed.eventType == "SALE_CREATED", note
    assert parsed.party == party, note
    assert parsed.product == "Rice", note
    assert parsed.quantity == 5, note


@pytest.mark.parametrize(
    ("note", "party"),
    [
        # What a purchase always looked like, and still does.
        ("bought 5 rice bags from Anita Stores", "Anita Stores"),
        ("Purchase 5 rice bags from ABC Suppliers", "Abc Suppliers"),
        ("I bought 5 rice bags", None),
        ("we purchased 5 rice bags", None),
        ("maine 5 kg rice kharida", None),
        ("ABC Suppliers se 5 bori rice kharida", "Abc Suppliers"),
        # A name in front, but the note says where the goods came from.
        ("Ramesh bought 5 bags rice from ABC Suppliers", "Abc Suppliers"),
        # A selling word, and a purchase: they sold, to this shop.
        ("Kumar Traders sold us 5 bags rice", "Kumar Traders"),
        ("Kumar Traders sold 5 rice bags to us", "Kumar Traders"),
        ("Kumar Traders delivered 5 rice bags to our shop", "Kumar Traders"),
    ],
)
def test_goods_that_came_to_the_shop_are_a_purchase(note: str, party: str | None):
    parsed = heuristic_parse(note)
    assert parsed.eventType == "PURCHASE_CREATED", note
    assert parsed.party == party, note
    assert parsed.product == "Rice", note
    assert parsed.quantity == 5, note


@pytest.mark.parametrize(
    "note",
    [
        "anita stores purchased 5 rice bags from us",
        "Anita took 5 rice bags from us",
        "Kumar Traders sold 5 rice bags to us",
        "Anita returned 2 bags to us",
        "paid 500 to me",
    ],
)
def test_the_shop_is_never_the_party(note: str):
    assert (heuristic_parse(note).party or "").lower() not in {"us", "me"}, note


def test_a_customer_whose_name_starts_with_us_is_still_a_name():
    """ "from us" only means the shop when the clause ends there."""
    assert heuristic_parse("sold 5 rice bags to US Foods").party == "Us Foods"
    bought = heuristic_parse("bought 5 rice bags from US Foods")
    assert (bought.eventType, bought.party) == ("PURCHASE_CREATED", "Us Foods")
    assert point_of_view("bought 5 rice bags from us foods") is None


def test_a_customer_who_wants_to_buy_is_an_order_not_a_purchase():
    for note in ("Anita wants to buy 5 rice bags from us", "Anita ordered 5 rice bags from us"):
        parsed = heuristic_parse(note)
        assert (parsed.eventType, parsed.party) == ("ORDER_CREATED", "Anita"), note


def test_what_follows_from_us_is_not_swallowed_into_the_item():
    parsed = heuristic_parse("Anita Stores purchased 5 rice bags from us, paid 500")
    assert [(i.product, i.quantity) for i in parsed.lineItems] == [("Rice", 5)]


def test_several_items_survive():
    parsed = heuristic_parse("Anita Stores bought 5 rice bags and 2 sugar packets from us")
    assert parsed.eventType == "SALE_CREATED"
    assert [(i.product, i.quantity) for i in parsed.lineItems] == [("Rice", 5), ("Sugar", 2)]


def test_a_date_is_not_read_as_an_item():
    """ "on 3 Nov" has the shape of an item: a number, then a word."""
    parsed = heuristic_parse("sold 5 kg rice to Anita Stores on 3 Nov")
    assert [(i.product, i.quantity) for i in parsed.lineItems] == [("Rice", 5)]
    assert parsed.date is not None and parsed.date.endswith("-11-03")


# ---------------------------------------------------------------------------
# A model's answer
# ---------------------------------------------------------------------------
def test_the_prompt_tells_the_model_whose_note_it_is():
    prompt = _prompt("anita stores purchased 5 rice bags from us", "2026-11-10")
    assert "Point of view" in prompt
    assert "from us" in prompt


def test_a_model_that_reads_the_verb_is_corrected(fake_provider):  # noqa: F811
    """The wording is explicit, so it is not left to the model's mood."""
    fake_provider["reply"]["text"] = json.dumps(
        {
            "eventType": "PURCHASE_CREATED",
            "party": "us",
            "lineItems": [{"product": "rice", "quantity": 5}],
        }
    )
    parsed = nlp.parse_command("anita stores purchased 5 rice bags from us")
    assert parsed.engine == "Test Model"
    assert parsed.eventType == "SALE_CREATED"
    assert parsed.party == "Anita Stores"


def test_a_model_is_corrected_the_other_way_too(fake_provider):  # noqa: F811
    fake_provider["reply"]["text"] = json.dumps(
        {"eventType": "SALE_CREATED", "party": "Kumar Traders", "lineItems": []}
    )
    parsed = nlp.parse_command("Kumar Traders sold us 10 bags sugar")
    assert parsed.eventType == "PURCHASE_CREATED"
    assert parsed.party == "Kumar Traders"


def test_a_model_is_left_alone_when_the_note_does_not_mention_the_shop(fake_provider):  # noqa: F811
    fake_provider["reply"]["text"] = json.dumps(
        {"eventType": "PURCHASE_CREATED", "party": "ABC Suppliers", "lineItems": []}
    )
    parsed = nlp.parse_command("ABC Suppliers 10 bags sugar")
    assert (parsed.eventType, parsed.party) == ("PURCHASE_CREATED", "ABC Suppliers")


def test_an_order_or_an_expense_is_not_turned_into_a_sale(fake_provider):  # noqa: F811
    fake_provider["reply"]["text"] = json.dumps(
        {"eventType": "ORDER_CREATED", "party": "Anita", "lineItems": []}
    )
    assert nlp.parse_command("Anita wants 5 rice bags from us").eventType == "ORDER_CREATED"


# ---------------------------------------------------------------------------
# The draft the shopkeeper sees
# ---------------------------------------------------------------------------
ANITA = SimpleNamespace(id="c1", name="Anita Stores", type="customer", phone=None)
SUNRISE = SimpleNamespace(id="s1", name="Sunrise Wholesale", type="supplier", phone=None)
RICE = SimpleNamespace(
    id="p1", name="Rice Bag 25kg", type="product", selling_price=1200.0, purchase_price=1000.0, stock=40
)


def test_the_reported_note_drafts_a_sale_to_the_customer_at_the_selling_price():
    note = "anita stores purchased 5 rice bags from us"
    draft = ground_text(heuristic_parse(note), [ANITA, SUNRISE], [RICE], note)
    assert draft["suggestedType"] == "sale"
    assert draft["partyId"] == "c1"
    assert draft["items"] == [
        {"productId": "p1", "description": "Rice Bag 25kg", "quantity": 5, "unitPrice": 1200.0}
    ]


def test_a_customer_nobody_has_met_yet_still_drafts_a_sale():
    note = "Lakshmi Provisions bought 5 rice bags"
    draft = ground_text(heuristic_parse(note), [ANITA, SUNRISE], [RICE], note)
    assert draft["suggestedType"] == "sale"
    assert draft["partyId"] is None
    assert draft["partyName"] == "Lakshmi Provisions"
