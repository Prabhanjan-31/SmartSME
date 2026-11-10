"""Natural-language parsing for the Smart Input Engine.

An LLM does the work when a key is configured; otherwise a dependency-free
regex parser covers the same fields, so the feature degrades instead of dying.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta

from .categories import PROMPT_LIST, canonical_category
from .client import extract_json, get_provider
from .lang import DEVANAGARI, KANNADA, normalize

EventType = str  # SALE_CREATED | PURCHASE_CREATED | ORDER_CREATED | EXPENSE_ADDED


@dataclass(slots=True)
class ParsedLine:
    """One thing ordered, and how much of it."""

    product: str | None = None
    quantity: float | None = None
    #: The model's English name for the product ("sago" for साबूदाना), or None.
    #: `product` stays in the note's own script for display and for catalogues
    #: kept in that script; this is a second key for catalogues kept in English,
    #: and is only ever used when `product` itself finds nothing. The regex
    #: parser cannot translate, so it always leaves this empty.
    english: str | None = None


@dataclass(slots=True)
class ParsedCommand:
    """What one note says.

    `lineItems` is a list because notes are lists: "20 tea packets, 40 rice bags
    and 10 sugar packets" is one order with three items, and this used to hold a
    single `product`, so two of those three were simply dropped - by the model
    and the regex parser alike, since the shape gave neither anywhere to put
    them. A photograph of the same order came out right, because the image path
    always had `lineItems`.

    `product` and `quantity` remain as read-only views of the first item, so the
    many callers that only ever want one keep working and there is still only
    one place the answer lives.
    """

    eventType: EventType = "SALE_CREATED"
    party: str | None = None
    lineItems: list[ParsedLine] = field(default_factory=list)
    amount: float | None = None
    category: str | None = None
    #: True when the note refers to the whole inventory ("sell the entire stock").
    allInventory: bool = False
    discountType: str = "none"
    discountValue: float = 0
    #: Transaction date as YYYY-MM-DD when the note states one, else None.
    date: str | None = None
    #: The provider label that parsed it, or "Heuristic".
    engine: str = "Heuristic"

    @property
    def product(self) -> str | None:
        """The first item's product, for callers that only handle one."""
        return self.lineItems[0].product if self.lineItems else None

    @property
    def quantity(self) -> float | None:
        return self.lineItems[0].quantity if self.lineItems else None

    def dict(self) -> dict:
        out = asdict(self)
        # The derived views are not fields, so `asdict` cannot see them; the
        # JSON this produces is read by the frontend and by tests.
        out["product"] = self.product
        out["quantity"] = self.quantity
        return out


SYSTEM = (
    "You extract a single structured business event from an SME shopkeeper's "
    "plain-language note. The note may be in English, Hindi or Kannada, written "
    'either in its own script or in Latin letters ("5 kilo chawal Anita ko '
    'becha", "Anita ge 5 kilo akki maride"), and may mix them in one '
    "sentence. Reply with JSON only, no prose or markdown."
)


def _prompt(text: str, today_iso: str) -> str:
    return f"""Extract one business event from the note and return ONLY a single minified JSON object with exactly these keys:
- eventType: one of "SALE_CREATED" (goods went out of this shop to a customer), "PURCHASE_CREATED" (goods came into this shop from a supplier), "ORDER_CREATED" (a customer wants/needs something later), "EXPENSE_ADDED" (rent, salary, utilities, fuel, etc.).
- party: the customer or supplier name, or null. Never "us", "me" or "our shop": that is the shop itself.
- lineItems: an array of every product the note mentions, each {{ "product": string (singular, no unit words like "bags"/"packets"), "quantity": number, "english": string or null }}. "english" is the plain English name a shop's product list would use for that item, lowercase and singular (e.g. "rice" for "चावल", "jaggery" for "ಬೆಲ್ಲ", "gram flour" for "besan"); use null when "product" is already English or you do not know the English name. A note listing three things has three entries. Use an empty array when no product is named.
- amount: total money value in rupees if stated, else null.
- category: for EXPENSE_ADDED, exactly one of: {PROMPT_LIST}. Choose the closest; do not invent another word and do not answer in any language but English. null for everything else.
- allInventory: true if the note refers to the ENTIRE inventory / all stock / everything in stock (e.g. "sell the entire inventory", "clear out all stock", "sell everything"); otherwise false. When true, leave lineItems empty.
- discountType: "percentage" if a percentage discount is mentioned (e.g. "10% off", "discount of 10%"), "amount" if a flat money discount is mentioned (e.g. "discount of 300 rupees"), otherwise "none".
- discountValue: the numeric discount, the percent number for "percentage" or the rupee figure for "amount"; 0 when discountType is "none".
- date: the date the transaction happened as "YYYY-MM-DD" if the note states one (e.g. "on 20th August 2026", "yesterday", "3 Sept"); otherwise null. Today is {today_iso}, resolve relative words against it, and assume a bare day+month is the most recent past occurrence.
Point of view: the shopkeeper wrote the note about their own shop, so decide eventType by which way the goods moved, not by the verb. "Anita Stores purchased 5 rice bags from us" and "Anita Stores bought 5 rice bags" are SALE_CREATED with party "Anita Stores", because a named customer did the buying. "bought 5 rice bags from Anita Stores", "we purchased 5 rice bags" and "Kumar Traders sold us 10 bags" are PURCHASE_CREATED. Hindi "humse"/"हमसे" and Kannada "namminda"/"ನಮ್ಮಿಂದ" mean "from us".
Language: the note may be English, Hindi or Kannada, in Devanagari, Kannada script or Latin letters, or a mix. Understand all of them. Keep `party` and `product` in the script the note used - do not translate or transliterate them, because they are matched against a catalogue that may itself be in that script. Common verbs: becha/bech diya/ಮಾರಿದೆ/maride mean sold; kharida/ಖರೀದಿಸಿದೆ/kharidiside mean bought; kharch/ಖರ್ಚು/kharchu means an expense; chahiye/ಬೇಕು/beku means a customer wants something. "ko"/"ge"/"ಗೆ" mark the recipient and "se"/"inda"/"ಇಂದ" the supplier, and both come AFTER the name. Hindi "kal" is yesterday for something already done and tomorrow for something wanted.
Use null where a value is unknown. No extra keys, no commentary.

Note: "{text}\""""


def parse_command(text: str) -> ParsedCommand:
    provider = get_provider()
    if provider is not None:
        try:
            raw = provider.complete(
                system=SYSTEM,
                prompt=_prompt(text, _iso_date(datetime.now())),
                max_tokens=1024,
            )
            parsed = extract_json(raw)
            if parsed and parsed.get("eventType"):
                out = _normalize(parsed)
                _apply_point_of_view(out, text)
                out.engine = provider.label
                return out
        except Exception as err:
            print(f"[nlp] provider parse failed, falling back to heuristic: {err}")
    out = heuristic_parse(text)
    out.engine = "Heuristic"
    return out


_ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _num(v: object) -> float | None:
    if v is None:
        return None
    try:
        return float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _lines(p: dict) -> list[ParsedLine]:
    """The line items a model returned, tolerating the older single-field shape."""
    raw = p.get("lineItems")
    if isinstance(raw, list):
        out = []
        for entry in raw:
            if not isinstance(entry, dict):
                continue
            product = entry.get("product") or None
            if product:
                english = entry.get("english")
                out.append(
                    ParsedLine(
                        product=str(product),
                        quantity=_num(entry.get("quantity")),
                        english=str(english).strip() or None if isinstance(english, str) else None,
                    )
                )
        if out:
            return out
    # A model that answered the old way, or one that ignored the array.
    product = p.get("product") or None
    if product:
        return [ParsedLine(product=str(product), quantity=_num(p.get("quantity")))]
    return []


def _normalize(p: dict) -> ParsedCommand:
    discount_type = p.get("discountType")
    if discount_type not in ("amount", "percentage"):
        discount_type = "none"
    discount_value = _num(p.get("discountValue")) or 0
    date = p.get("date")
    return ParsedCommand(
        eventType=p.get("eventType") or "SALE_CREATED",
        party=p.get("party") or None,
        lineItems=_lines(p),
        amount=_num(p.get("amount")),
        # Pinned to the fixed list, whatever the model answered: an
        # expense report is only useful if the same cost lands under the
        # same heading every time.
        category=canonical_category(p.get("category")) if p.get("category") else None,
        allInventory=bool(p.get("allInventory")),
        discountType=discount_type,
        discountValue=discount_value if discount_value > 0 else 0,
        date=date if isinstance(date, str) and _ISO_RE.match(date) else None,
    )


# ---------------------------------------------------------------------------
# Dates
# ---------------------------------------------------------------------------
MONTH_INDEX = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}
_MONTHS = "jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec"


def _iso_date(d: datetime) -> str:
    return d.strftime("%Y-%m-%d")


def _build_date(year: int, month: int, day: int) -> str | None:
    """Reject impossible dates (31 Feb) rather than rolling them over."""
    try:
        return _iso_date(datetime(year, month, day))
    except ValueError:
        return None


def _infer_year(month: int, day: int, today: datetime) -> int:
    """For a bare day+month, pick the most recent occurrence that is not future."""
    year = today.year
    try:
        candidate = datetime(year, month, day)
    except ValueError:
        return year
    return year - 1 if candidate > today else year


def parse_date_phrase(text: str, now: datetime | None = None) -> str | None:
    """Pull a transaction date out of a note. Returns YYYY-MM-DD, or None."""
    now = now or datetime.now()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    lower = text.lower()

    if re.search(r"\bday before yesterday\b", lower):
        return _iso_date(today - timedelta(days=2))
    if re.search(r"\byesterday\b", lower):
        return _iso_date(today - timedelta(days=1))
    if re.search(r"\btomorrow\b", lower):
        return _iso_date(today + timedelta(days=1))
    if re.search(r"\btoday\b", lower):
        return _iso_date(today)

    # 2026-08-20
    m = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", lower)
    if m:
        return _build_date(int(m[1]), int(m[2]), int(m[3]))

    # 20/08/2026 or 20-08-26 (day first, the Indian convention)
    m = re.search(r"\b(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})\b", lower)
    if m:
        year = int(m[3])
        return _build_date(2000 + year if year < 100 else year, int(m[2]), int(m[1]))

    # "20th August 2026", "3 sept", "on 20 aug"
    m = re.search(
        rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+({_MONTHS})[a-z]*\.?(?:,?\s*(\d{{4}}))?\b", lower
    )
    if m:
        day, mon = int(m[1]), MONTH_INDEX[m[2]]
        return _build_date(int(m[3]) if m[3] else _infer_year(mon, day, today), mon, day)

    # "August 20 2026" / "on aug 20" - requires "on" or a year, so a stray
    # "may 10 bags" is not read as a date.
    m = re.search(
        rf"\b(on\s+)?({_MONTHS})[a-z]*\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?(?:,?\s*(\d{{4}}))?\b", lower
    )
    if m and (m[1] or m[4]):
        mon, day = MONTH_INDEX[m[2]], int(m[3])
        return _build_date(int(m[4]) if m[4] else _infer_year(mon, day, today), mon, day)

    return None


# ---------------------------------------------------------------------------
# Discounts
# ---------------------------------------------------------------------------
def parse_discount(lower: str) -> tuple[str, float]:
    """Pull a "discount of 10%" / "discount of 300 rupees" clause out of a note."""
    # No trailing \b after the alternation: "%" is a non-word char, so a word
    # boundary can never follow it and "10%" would fail to match.
    pct = re.search(r"(?:discount|off)\D{0,15}?(\d[\d.]*)\s*(?:%|percent|pct)", lower) or re.search(
        r"(\d[\d.]*)\s*(?:%|percent|pct)\s*(?:discount|off)?", lower
    )
    if pct:
        return "percentage", float(pct[1])

    amt = re.search(r"discount\s+of\s+(?:₹|rs\.?|inr)?\s*(\d[\d,]*(?:\.\d+)?)", lower) or re.search(
        r"(?:₹|rs\.?|inr)\s*(\d[\d,]*(?:\.\d+)?)\s*(?:discount|off)", lower
    )
    if amt:
        return "amount", float(amt[1].replace(",", ""))

    return "none", 0


# ---------------------------------------------------------------------------
# Heuristic parser
# ---------------------------------------------------------------------------
UNIT_WORDS = re.compile(
    r"\b(bags?|packets?|pkts?|boxes?|box|pcs?|pieces?|units?|kgs?|kg|kilograms?|grams?|g|"
    r"litres?|liters?|ltrs?|l|dozens?|cartons?|of|the)\b",
    re.IGNORECASE,
)


#: Words that can never be part of a party or product name. After
#: normalisation a note can read "to Anita 5 kg rice sold", so the name is no
#: longer guaranteed to sit at the end of the sentence and "$" cannot end it.
#:
#: Only words that cannot appear *inside* a name belong here, and "and" plainly
#: can: it cut "Ram and Sons" down to "Ram", which then matched an entirely
#: different customer called Ramesh, and "salt and pepper" down to "Salt".
#:
#: The whole-inventory wording is matched as a phrase for the same reason. A
#: bare "all" would halve "all purpose flour", whereas "all stock" is not part
#: of anything's name - it is what a note says instead of naming a product.
STOP_WORDS = (
    "for|at|on|worth|each|to|from|tomorrow|today|yesterday|sold|bought|sell|buy|"
    "purchased|expense|spent|wants|order|ordered|discount|off|rs|inr|everything|"
    r"(?:entire|all|whole|complete|full)\s+(?:inventory|stocks?|goods|products?)"
)

#: Left lowercase in the middle of a name, so a new party is created as
#: "Ram and Sons" rather than "Ram And Sons".
_MINOR_WORDS = {"and", "of", "the", "for", "at", "to"}


#: A quantity, then the words belonging to it, ending at the next quantity, a
#: stop word, or the end of the sentence.
_ITEM_RUN = re.compile(
    rf"(\d[\d,]*(?:\.\d+)?)\s+(.*?)(?=\s+\d[\d,]*(?:\.\d+)?\s|\s+(?:{STOP_WORDS})\b|\s*[.!?]|$)",
    re.IGNORECASE,
)

#: Words that join two items rather than belong to either.
_JOINERS = re.compile(r"^(?:and|aur|mattu|plus|with|&|,)\s+|\s+(?:and|aur|mattu|plus|&)$", re.I)

#: "on 3 Nov" has the shape of an item, a number and then a word. It is the
#: date, which `parse_date_phrase` has already read, not three of something.
_MONTH_NOT_ITEM = re.compile(rf"^(?:{_MONTHS})[a-z]*\.?(?:,?\s*\d{{4}})?$", re.IGNORECASE)


def _read_items(text: str) -> list[ParsedLine]:
    """Every "<quantity> <product>" the note contains, in order.

    Notes are lists. "20 tea packets, 40 rice bags and 10 sugar packets" is three
    items, and reading only the first silently dropped two thirds of an order.

    The split is on **quantities**, not on the word "and", which is the whole
    reason it is safe: "2 kg salt and pepper" has one quantity, so it stays one
    item called salt and pepper, while "2 salt 3 pepper" has two and becomes
    two. Splitting on conjunctions would get that exactly backwards.
    """
    out: list[ParsedLine] = []
    for match in _ITEM_RUN.finditer(text):
        words = _JOINERS.sub("", match[2].strip(" ,.;:-")).strip()
        cleaned = re.sub(r"\s+", " ", UNIT_WORDS.sub(" ", words)).strip(" ,.;:-")
        if not cleaned or _MONTH_NOT_ITEM.match(cleaned):
            continue
        try:
            quantity = float(match[1].replace(",", ""))
        except ValueError:
            continue
        out.append(ParsedLine(product=cleaned, quantity=quantity if quantity > 0 else None))
    return out


def _title_case(s: str) -> str:
    words = [w for w in s.lower().split() if w]
    return " ".join(
        w if i and w in _MINOR_WORDS else w[0].upper() + w[1:] for i, w in enumerate(words)
    ).strip()


# ---------------------------------------------------------------------------
# Point of view
#
# A note is written by the shopkeeper, about their own shop. "Anita Stores
# purchased 5 rice bags from us" has the word "purchased" in it and is a sale:
# the goods left this shop. Reading sale-versus-purchase off the verb alone
# gets every note written from the other side of the counter backwards, and
# then reads "Us" as the name of the supplier.
# ---------------------------------------------------------------------------
_US = r"(?:us|me|(?:our|my)\s+(?:shop|store))"

#: What may follow "from us" for it to mean this shop: the end of the note,
#: punctuation, a number, or a word that starts another clause. Anything else
#: is left alone as a name, so a customer called "US Foods" is not us.
_US_END = (
    rf"(?=\s+(?:{STOP_WORDS}|and|but|with|in|by|this|last|paid|cash|upi|credit)\b"
    r"|\s+\d|\s*[.,;!?₹]|\s*$)"
)
_FROM_US = re.compile(rf"\bfrom\s+{_US}{_US_END}", re.IGNORECASE)
_TO_US = re.compile(rf"\bto\s+{_US}{_US_END}", re.IGNORECASE)
_SUPPLY_VERBS = r"sold|sells?|gave|gives?|supplied|supplies|delivered|sent"
#: "Kumar Traders sold us 10 bags".
_VERB_US = re.compile(rf"\b({_SUPPLY_VERBS})\s+(?:us|me){_US_END}", re.IGNORECASE)
_SUPPLY_VERB = re.compile(rf"\b(?:{_SUPPLY_VERBS})\b", re.IGNORECASE)


def point_of_view(text: str) -> str | None:
    """Which way the goods moved, when the note says so about the shop itself.

    "sale" for goods that left it ("... from us"), "purchase" for goods that
    came to it ("... sold us", "delivered ... to us"), None when the note does
    not mention the shop. Takes a note already through `lang.normalize`.
    """
    if _FROM_US.search(text):
        return "sale"
    if _VERB_US.search(text) or (_TO_US.search(text) and _SUPPLY_VERB.search(text)):
        return "purchase"
    return None


def _without_us(text: str) -> str:
    """The note with the shop's own mentions removed, so "us" is never read as
    the party and never ends up inside a product name."""
    text = _VERB_US.sub(lambda m: m[1], text)
    text = _TO_US.sub(" ", _FROM_US.sub(" ", text))
    return re.sub(r"\s+", " ", text).strip()


_BUY_VERBS = r"bought|buys?|purchase[ds]?"
_SUBJECT_VERBS = (
    rf"{_BUY_VERBS}|took|takes?|taken|got|gets?|collected|received|{_SUPPLY_VERBS}"
    r"|ordered|orders|wants|needs|requested|requires"
)
#: Words allowed between the name and its verb: "Anita has bought", "Anita
#: wants to buy".
_AUXILIARIES = (
    r"(?:(?:has|have|had|just|also|again|will|wants?\s+to|needs?\s+to|would\s+like\s+to)\s+)*"
)
#: A name at the head of the note, then what shows it is the one acting: the
#: verb ("Anita Stores bought ..."), Hindi's agent marker ("Anita ne ..."), or
#: the shop itself ("Anita from us ...", which is how "Anita humse ..." arrives).
#: No digits: a name ends where a quantity starts.
_SUBJECT = re.compile(
    rf"^([A-Za-z{DEVANAGARI}{KANNADA}][A-Za-z&.'\s{DEVANAGARI}{KANNADA}]*?)\s+"
    rf"(?:(?:ne|ने)(?![\w{DEVANAGARI}{KANNADA}])"
    rf"|{_AUXILIARIES}(?:{_SUBJECT_VERBS})\b"
    rf"|(?:from|to)\s+{_US}{_US_END})",
    re.IGNORECASE,
)
_LEADING_DATE = re.compile(
    r"^(?:(?:day before yesterday|yesterday|today|tomorrow)\s*,?\s+)+", re.IGNORECASE
)

#: The shopkeeper, in the three languages. A note that opens with one of these
#: is about what the shop did, which is how every verb was already being read.
_FIRST_PERSON = {
    "i", "we", "me", "us", "my", "our", "ive", "i've", "we've",
    "maine", "mene", "main", "mai", "humne", "hamne", "hum",
    "मैंने", "मैने", "मैं", "हमने", "हम",
    "naanu", "nanu", "naavu", "navu", "ನಾನು", "ನಾವು",
}  # fmt: skip
#: Someone bought, but nobody in particular: a sale with no party on it.
_NOBODY = {
    "customer", "a customer", "one customer", "the customer", "client", "a client",
    "someone", "somebody", "walk in", "walk-in", "walkin", "a walk in customer",
}  # fmt: skip
_NOT_A_SUBJECT = re.compile(
    rf"^(?:{STOP_WORDS}|{_SUBJECT_VERBS}|paid|restock(?:ed)?)$", re.IGNORECASE
)


def _subject(text: str) -> tuple[bool, str | None]:
    """Who the note says did it, when that is not the shopkeeper.

    Returns (someone else acted, their name). The name is None for "a customer
    bought ...", where there is a buyer but nobody to put on the invoice.
    """
    match = _SUBJECT.match(_LEADING_DATE.sub("", text.strip()))
    if not match:
        return False, None
    name = re.sub(r"\s+", " ", match[1]).strip(" .,'&")
    if name.lower() in _NOBODY:
        return True, None
    words = name.lower().split()
    if not words or any(
        w in _FIRST_PERSON or _NOT_A_SUBJECT.match(w) or UNIT_WORDS.fullmatch(w) for w in words
    ):
        return False, None
    return True, name


def _apply_point_of_view(out: ParsedCommand, text: str) -> None:
    """Hold a model's answer to what the note says about the shop itself.

    A model usually gets "purchased ... from us" right, and the prompt asks it
    to, but "usually" is not good enough to leave a sale filed as a purchase.
    Only the explicit wording is enforced; everything else stays the model's
    call.
    """
    shaped = normalize(text)
    side = point_of_view(shaped.lower())
    if side and out.eventType in ("SALE_CREATED", "PURCHASE_CREATED"):
        out.eventType = "SALE_CREATED" if side == "sale" else "PURCHASE_CREATED"
    if out.party and re.fullmatch(rf"(?:the\s+)?{_US}", out.party.strip(), re.IGNORECASE):
        acted, name = _subject(shaped)
        out.party = _title_case(name) if acted and name else None


def heuristic_parse(text: str) -> ParsedCommand:
    """A dependency-free parser for the common shapes.

    Good enough as a starting point: the confirmation screen lets the user
    correct anything before it is published.

    The note is first rewritten into its English shape by `lang.normalize`, so
    Hindi and Kannada, in their own scripts or typed in Latin letters, reach
    the same rules as English. Names and products are left in whatever script
    they were written in, to be matched against the catalogue as-is.
    """
    text = normalize(text)
    lower = text.lower()

    all_inventory = bool(
        re.search(
            r"\b(entire|all|whole|complete|full)\s+(inventory|stock|stocks|goods|products?)\b",
            lower,
        )
        or re.search(r"\b(sell|clear|sold|liquidat\w*)\s+everything\b", lower)
    )
    discount_type, discount_value = parse_discount(lower)
    date = parse_date_phrase(text)

    # Who is on which side of the counter, before any verb is trusted.
    side = point_of_view(lower)
    acted, subject = _subject(text)
    #: The note with "from us" and the like taken out, for finding the party
    #: and the items: "us" is neither.
    plain = _without_us(text)
    names_a_source = bool(re.search(r"\bfrom\b", plain, re.IGNORECASE))
    buy_word = re.search(rf"\b(?:{_BUY_VERBS})\b", lower)
    wants = re.search(r"\b(order(?:ed)?|wants?|need[s]?|requires?|requested)\b", lower)
    #: The other side did the buying, so this shop did the selling: the note
    #: says "from us", or it opens with a name and gives no supplier.
    they_bought = bool(buy_word) and (side == "sale" or (acted and not names_a_source))

    event_type: EventType = "SALE_CREATED"
    if they_bought:
        event_type = "ORDER_CREATED" if wants else "SALE_CREATED"
    elif buy_word or (re.search(r"\b(received|restock(?:ed)?)\b", lower) and names_a_source):
        event_type = "PURCHASE_CREATED"
    elif wants:
        event_type = "ORDER_CREATED"
    elif (
        # Strong expense words classify as an expense even with "to <payee>".
        re.search(
            r"\b(rent|salary|wages?|electricity|utilit\w*|fuel|maintenance|internet)\b", lower
        )
        or re.search(r"\b(expense|spent|spend|bill)\b", lower)
        or (re.search(r"\bpaid\b", lower) and not re.search(r"\bto\b", lower))
    ):
        event_type = "EXPENSE_ADDED"
    elif side == "purchase":
        # "Kumar Traders sold us 10 bags": a selling word, and a purchase.
        event_type = "PURCHASE_CREATED"

    qty_match = re.search(r"\b(\d[\d,]*(?:\.\d+)?)\b", text)
    first_number = float(qty_match[1].replace(",", "")) if qty_match else None

    # "at" is intentionally excluded: it usually marks a unit price
    # ("5 bags at 100 each"), not the total.
    # The word boundary matters: without it "ABC Suppliers 10 bags" matches the
    # "rs" inside "Suppliers" and reads 10 as the money value. Shop names ending
    # in Traders/Suppliers/Brothers are everywhere.
    amt_match = re.search(
        r"(?:₹|\b(?:rs\.?|inr|worth|for|amount))\s*(\d[\d,]*(?:\.\d+)?)",
        text,
        re.IGNORECASE,
    )
    amount = float(amt_match[1].replace(",", "")) if amt_match else None

    # "for" counts as well, but only when a name follows rather than a number:
    # "40 tea packets for Kumar Traders" names a customer, "2 boxes for 1200"
    # names a price. Real messages use it constantly.
    party_match = re.search(
        rf"\b(?:to|from|for)\s+(?!\d)([A-Za-z0-9&.'\s{DEVANAGARI}{KANNADA}]+?)"
        rf"(?=\s+(?:{STOP_WORDS})\b|\s+\d|\s*[.,!?₹]|$)",
        plain,
        re.IGNORECASE,
    )
    party = _title_case(party_match[1].strip()) if party_match else None
    if acted and (side or they_bought):
        # The name at the head of the note is the other party, and beats a
        # stray "for cash" further along. It may be nobody: "a customer bought".
        party = _title_case(subject) if subject else None

    if event_type == "EXPENSE_ADDED":
        amount = amount if amount is not None else first_number
        cat_match = re.search(
            rf"\bfor\s+([A-Za-z\s{DEVANAGARI}{KANNADA}]+)", text, re.IGNORECASE
        ) or re.search(
            r"\b(rent|salary|electricity|utilities?|fuel|transport|internet|maintenance|misc\w*)\b",
            text,
            re.IGNORECASE,
        )
        category = canonical_category(cat_match[1]) if cat_match else "General"
        return ParsedCommand(
            eventType=event_type,
            party=None,
            lineItems=[],
            amount=amount,
            category=category,
            allInventory=False,
            discountType="none",
            discountValue=0,
            date=date,
        )

    # From the note as written, not `plain`: "from" and "to" are what end an
    # item, so "5 rice bags from us, paid 500" needs them left in place.
    items = _read_items(text)

    return ParsedCommand(
        eventType=event_type,
        party=party,
        lineItems=[
            ParsedLine(product=_title_case(i.product or ""), quantity=i.quantity or first_number)
            for i in items
        ],
        amount=amount,
        category=None,
        allInventory=all_inventory,
        discountType=discount_type,
        discountValue=discount_value,
        date=date,
    )
