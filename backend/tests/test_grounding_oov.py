"""Grounding for words the lexicon does not know.

Two rules, both about the catalogue match rather than the parse:

* A word in front of a known one ("ragi" in "ragi atta") narrows it. Only a row
  that also says "ragi" may be chosen; with none, no row is. Matching the
  shop's only flour instead put a real product at a real price on a draft
  that was wrong, which is the mistake a hurried confirm lets through.
* The model's English name for a product is tried when the note's own word
  finds nothing, so "साबूदाना" reaches "Sago 500g" in an English catalogue.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.ai.nlp import ParsedCommand, ParsedLine, _lines, heuristic_parse
from app.smart_input import best_match, ground_text


def _product(name: str, pid: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=pid, name=name, type="product", selling_price=10.0, purchase_price=8.0, stock=5
    )


WHEAT = _product("Wheat Flour 10kg", "p1")
RAGI = _product("Ragi Flour 1kg", "p2")
RICE = _product("Rice Bag 25kg", "p3")
OIL = _product("Cooking Oil 1L", "p4")
SAGO = _product("Sago 500g", "p5")


@pytest.mark.parametrize("phrase", ["ragi atta", "ragi hittu", "रागी आटा"])
def test_a_qualifier_picks_the_row_that_names_it(phrase: str):
    assert best_match([WHEAT, RAGI], phrase) is RAGI


@pytest.mark.parametrize("phrase", ["ragi atta", "ragi hittu"])
def test_a_qualifier_no_row_names_is_not_matched_to_another_flour(phrase: str):
    assert best_match([WHEAT, RICE], phrase) is None


def test_plain_flour_still_finds_the_flour():
    assert best_match([RICE, WHEAT], "atta") is WHEAT


def test_words_after_the_known_one_do_not_block_it():
    # The regex parser sometimes leaves the verb on the product.
    assert best_match([RICE], "चावल दे दिया") is RICE


@pytest.mark.parametrize("phrase", ["packet sugar", "2 kg rice", "तेल के डिब्बे"])
def test_units_and_linking_words_are_not_qualifiers(phrase: str):
    sugar = _product("Sugar Packet 1kg", "p6")
    found = best_match([sugar, RICE, OIL], phrase)
    assert found is not None


def test_a_qualifier_the_row_does_name_still_matches():
    assert best_match([OIL], "cooking oil") is OIL


def test_the_english_name_is_tried_when_the_note_word_finds_nothing():
    parsed = ParsedCommand(
        eventType="SALE_CREATED",
        lineItems=[ParsedLine(product="साबूदाना", quantity=4, english="sago")],
    )
    draft = ground_text(parsed, [], [SAGO, RICE])
    line = draft["items"][0]
    assert line["productId"] == "p5"
    assert line["description"] == "Sago 500g"


def test_the_note_word_wins_over_the_english_name():
    parsed = ParsedCommand(
        lineItems=[ParsedLine(product="चावल", quantity=1, english="sago")],
    )
    assert ground_text(parsed, [], [SAGO, RICE])["items"][0]["productId"] == "p3"


def test_no_english_name_leaves_an_unmatched_line_as_written():
    parsed = ParsedCommand(lineItems=[ParsedLine(product="साबूदाना", quantity=2)])
    line = ground_text(parsed, [], [RICE])["items"][0]
    assert line["productId"] is None and line["description"] == "साबूदाना"


def test_the_model_answer_carries_the_english_name():
    lines = _lines({"lineItems": [{"product": "ಸಾಬಕ್ಕಿ", "quantity": 3, "english": " sago "}]})
    assert lines[0].english == "sago"


@pytest.mark.parametrize("value", [None, "", 5, ["sago"]])
def test_a_missing_or_malformed_english_name_is_ignored(value):
    lines = _lines({"lineItems": [{"product": "x", "quantity": 1, "english": value}]})
    assert lines[0].english is None


def test_the_regex_parser_never_invents_an_english_name():
    parsed = heuristic_parse("Anita ko 2 packet sabudana becha")
    assert all(line.english is None for line in parsed.lineItems)
