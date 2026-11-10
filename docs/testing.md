# The test suite

What is covered, how to run it, and how to add to it.

[&larr; Back to the README](../README.md)

---

## Tests

```bash
cd backend
.venv/Scripts/python -m pytest -q              # 569 tests
```

```
================================ test summary =================================
  AI (mocked)             24 passed
  Alert log                9 passed
  Business health         55 passed
  Dispatch                 8 passed
  Domain units            48 passed
  Endpoint smoke          36 passed
  Event authors            6 passed
  Inbound orders          44 passed
  Languages               46 passed
  Order slips (OCR)       23 passed
  Paging                  25 passed
  Payment modes           22 passed
  Payments & deadlines    42 passed
  Point of view           39 passed
  Review regressions       8 passed
  Review regressions II   22 passed
  Roles & throttle        27 passed
  Translation             65 passed
  Unknown words           20 passed
-------------------------------------------------------------------------------
  569 passed in 42.45s
```

Hooks in `tests/conftest.py` replace pytest's default report order. Pytest prints
failures first and the counts last, so after a long run the thing you actually
want has scrolled off; here a per-layer summary comes last, with the failures,
full traceback and assertion diff, printed underneath it. A skip prints its
reason, which is almost always "Postgres is unreachable".

Nineteen layers, in one run.

**`tests/test_health.py`: 55 tests over the business-health score.** The scoring
functions are pure, so every threshold in
[Business health](business-health.md) is pinned without a database: the bands
for each part, the "no data" cases, the re-weighting when a part is missing, and
the cap that stops one bad part hiding behind three good ones. Four more go
through the API: an empty business has no score, products alone are not enough
for one, credit to a named customer is counted once, and one business built to
known numbers (back-dated sales, purchases and expenses, payments dated on
time and late, a cancelled sale, a dead product) has every input checked to the
rupee and every score checked against arithmetic written out in the test. All
four fail against the score this replaced.

**`tests/test_payments.py`: 42 tests over payment deadlines and the ledger.**
Where a deadline comes from (the business default, a party's own terms, a hand
edit on one document), that it moves with a corrected date and cannot be set
before the document, that money taken at the sale is dated on the sale and a
later payment on the day it came, that settling a party or everything writes
one ledger row per document, that an unpaid balance reads overdue once its day
has passed, that only a manager can change a deadline, plus the Reports
additions: top suppliers, and the trend chart's switch between sales, purchases
and expenses.

Sixteen of them pin **which day a payment may carry**, which is a rule about
calendar days and used to be a comparison of clock times. A payment can be
dated the day of the sale whatever the clock says (an invoice raised at three
in the afternoon could not be paid that day, because a date picked in the
dialog is stored as noon, and noon is "before" three), it cannot be dated
after today, it cannot be dated before its document, a sale dated ahead takes
no payment until its day comes, and a purchase follows the same rules.
`payment_moment()` is pure and takes the current time as an argument, so the
edges (a minute before midnight is still today) are checked without waiting
for them, along with the wording of each refusal.

**`tests/test_payment_modes.py`: 22 tests over how a payment was made.** The
rules first, with no database: cash keeps nothing, every other mode needs its
identifier, a card may carry only its last four digits (a full number is
refused, never trimmed), card type must be credit or debit, a cheque date must
be a date, unknown extras are dropped, unknown modes and overlong references
are refused. Then through the API: each mode round-trips with its extras,
money taken at the sale carries the mode from the form, a bad reference refuses
the whole sale rather than leaving an invoice behind, and a sale published
without a mode, or a settlement, says "not recorded" rather than "cash".

**`tests/test_domain.py`: 48 unit tests, no database.** The maths and parsing the
money and Smart Input features depend on: discount-before-tax totals for sales and
purchases, `round2` half-up rounding, line-item validation, the full date-phrase
parser, discount extraction, the heuristic classifier, party/product fuzzy
matching, report period resolution, and password hashing. Six cover the shop's
clock: `APP_TIMEZONE` is applied to the process, a `TZ` already set on the
machine wins, a blank or unknown zone leaves the machine clock alone, and the
default is India.

**`tests/test_point_of_view.py`: 39 tests over who sold to whom.** "Anita
Stores purchased 5 rice bags from us" is a sale, and the word "purchased" must
not make it a purchase. Notes written from the customer's side, from the
shop's side and from a supplier's side, in English, Hindi and Kannada; that the
shop itself ("us", "our shop") is never taken for the party; that a customer
called "US Foods" is still a name; that wanting to buy is an order; that
several items and a trailing "paid 500" survive; and, with the model faked,
that an answer which read the verb is corrected while one about a note that
does not mention the shop is left alone. The last two go through grounding, so
the draft the shopkeeper sees is a sale to the right customer at the selling
price. See [Point of view](smart-input.md#point-of-view).

**`tests/test_grounding_oov.py`: 20 tests over words the lexicon does not
know.** A qualifier in front of a known word ("ragi atta") picks the product
that names it and declines when none does, units and linking words are not
qualifiers, and words after the known one do not block a match. Then the
model's English name: it is tried only when the note's own word finds nothing,
the note's word wins when both match, a missing or malformed one is ignored,
and the regex parser never invents one. See
[Words the lexicon does not know](smart-input.md#words-the-lexicon-does-not-know).

**`tests/test_multilingual.py`: 46 tests over Hindi and Kannada.** The same
note written five ways must produce the same event; native digits become
numbers; postpositions are moved; names keep their script; and the awkward cases
are pinned: ಬಾಡಿಗೆ is not split into "to ಬಾಡಿ", a product is not swallowed by
the party beside it, and a shop called "ABC Suppliers" is not read as "rs 10".

**`tests/test_ai_mocked.py`: 24 tests over the AI path, model faked.** Provider
selection and precedence, what the prompt asks for, and above all what happens
when the model answers badly: markdown fences, prose around the JSON, truncated
objects, wrong field types, a provider that raises. Every one must degrade to
the built-in parser rather than reaching the shopkeeper. No network, no key, no
cost.

**`tests/test_alerts.py`: 9 tests over the alert log.** That an alert names its
rule, event and author, that an employee's alert is attributed to the employee,
the severity and unread filters, mark-unread, dismissal, bulk clear, and that a
sourceless alert still renders.

**`tests/test_inbound.py` - 44 tests over orders arriving from outside.** A raw
RFC-822 message and a real Telegram `getUpdates` payload go in; a draft, a queue
entry and eventually a recorded sale with moved stock come out. Covers routing by
token, HTML-only mail, Kannada surviving the mail encoding, deduplication (the
key is the message, not the chat), unroutable mail being dropped rather than
guessed at, that an employee can work the queue but not erase it, and that an
order accepted in the afternoon can be paid the same day (an accepted order is
dated to the minute it was accepted, which is what exposed the payment-date
bug above). Three cover the review window: a draft corrected from a sale to a
purchase, with another party and another day, is recorded as exactly that;
the total the window works out from `GET /api/input/status` is the total the
server stores for a discounted order; and an emailed expense can be corrected
and recorded, while one with no amount is refused and stays in the queue.

**`tests/test_dispatch.py` - 8 tests over both dispatch modes.** That inline
applies effects before a write returns, that celery mode enqueues instead, that
the task applies an event and passes its chain on, that a duplicate delivery is
skipped rather than applied twice, that the sweep rescues stranded events and
leaves fresh ones alone, and that a broker which is down does not fail the write.
The broker is faked, so these run offline; one extra test talks to a real Redis
and skips without one.

**`tests/test_event_actor.py`: 6 tests over event authorship.** That a sale
names the person who made it, that a chained stock event inherits the same
author, that an employee's work is attributed to them and not to the owner, and
that authorless system events still serialize.

**`tests/test_pagination.py`: 25 tests over paging.** That every list endpoint
returns an envelope, that pages do not overlap, that a page past the end is
empty rather than an error, and above all that the statistics beside the rows
still describe the whole set when the page is shrunk to one row.

**`tests/test_rbac.py`: 27 tests over roles, invites and throttling.** Every
role against the endpoints that matter for it, from both sides: what it may do
*and* what it must be refused, which is the half that actually proves anything.
Covers the permission table itself, cross-tenant access, the invite round trip
(including revoked and reused tokens), the last-owner guard, and the lockout:
that an owner locks after five failures, that an employee never does, that a
successful sign-in clears the streak, and that the lock doubles.

**`tests/test_api_smoke.py`: 36 tests over every endpoint.** One pass across the
whole HTTP surface: all 73 routes are called the way the SPA calls them and the
response is checked for the shape the client relies on: routing, auth,
serialization, the domain call behind each route, and the event effects that
follow a write (a sale moves stock before the request returns; cancelling it puts
the stock back; a workflow rule raises a notification). Error paths are part of
the sweep too: 401 without a session, 404 for a missing document, 400 for an empty
sale, an unknown event type, an out-of-range tax rate and an empty report period.

The smoke tests need Postgres, so start it first with `docker compose up -d`. They
never touch your development data:

- `tests/conftest.py` drops and recreates a scratch **`smartsme_test`** database
  beside the configured one, and runs `alembic upgrade head` into it, so the
  migrations are smoke-tested as well.
- The demo seed is off and each run signs up its own business, so counts are
  deterministic.
- The background worker is off; the write endpoints drain the event queue inline,
  which is what makes the effects assertable.
- Every AI key is cleared, so Smart Input falls back to its built-in parser and
  OCR reports itself unavailable. **The suite makes no network calls** and costs
  nothing to run.

If Postgres is unreachable the smoke tests skip with a note and the unit tests
still run.

Frontend: `npm run typecheck` and `npm run build` in `frontend/`.

### Lint & format

```bash
cd backend
.venv/Scripts/python -m ruff check .            # lint
.venv/Scripts/python -m ruff format .           # format
```

```bash
cd frontend
npm run format                                  # prettier --write
npm run format:check                            # verify only
```

Ruff is configured in `backend/pyproject.toml` (100 columns, import sorting,
pyupgrade, bugbear) and Prettier in `frontend/.prettierrc.json`. The LLM prompt
files (`app/ai/nlp.py`, `app/ai/ocr.py`) are exempt from the line-length rule so
the prompts stay verbatim.

---


## Frontend tests

```powershell
cd frontend
npm test            # vitest, once
npm run test:watch
```

81 tests in five files. Small on purpose, and pointed first at one thing:
`src/lib/api.ts`, where the frontend and the API agree on the shape of a
request. Vitest runs in plain Node with no browser, so what is tested is the
logic kept in `src/lib`, not the components that draw it.

That file is covered because a bug lived in it undetected. `request()` set
`Content-Type: application/json` whenever a body was present - including when
the body was a `FormData` - so the browser never set its own
`multipart/form-data; boundary=...`. FastAPI found no `file` field and answered
**422 "Field required"**. Image upload never worked from the UI at all.

The backend suite could not have caught it. Every test there posts multipart
straight at the endpoint with `TestClient`, which skips the frontend's
request-building entirely. **A contract only one side is tested against is not
a tested contract** - and that is the argument for these tests existing at all,
rather than any coverage number.

`src/lib/health.test.ts` covers the other half of a contract in the same spirit.
The API sends `null` for a business-health part with no data behind it, and the
dashboard must show that as "No data yet" with an empty bar, never as a red
zero. The backend tests pin the `null`; this pins what the browser does with it.

`src/lib/api.test.ts` also pins the signal that keeps the bell honest. Every
write that succeeds tells the app shell, which refetches the unread-alert and
Inbox counts; marking an alert read used to leave the red number in place
until you left the page. The tests check that a POST, PATCH or DELETE fires
it, that a GET, a refused write, and signing in or out do not, and that an
unsubscribed listener stops hearing it.

`src/lib/payments.test.ts` covers what the "Record payment" dialog asks for in
each mode, and `paymentDateWindow()`: the same calendar-day rule the server
enforces (not before the sale, not after today), so the date picker can be
limited to days the server will accept and a bad date is explained before the
request is sent.

`src/lib/draft.test.ts` covers the Inbox review window: what it adds up to and
what it sends back. `documentTotals()` is held to the server's rule (discount
off the subtotal, then tax, rounded to paise, an over-discount flagged).
`repriceLines()` must move a catalogue price to the other side when a draft is
flipped between sale and purchase, and leave a typed price alone.
`acceptPayload()` must send the party the reviewer picked and not the one the
parser guessed, send today as no date, keep a discount only on a sale, leave
out emptied lines, and send an expense as a category, an amount and a
description.

## What the test suite does not measure

Every test here checks that the code does what it was written to do. None of
them can say whether reading "Anita ko 5 kilo chawal becha" produces the *right*
sale, because "right" is a judgement about meaning rather than a property of the
code.

Worth being blunt about a second gap: **the suite never calls a real model.**
`conftest.py` clears every API key so runs are hermetic and free, the language
tests exercise `heuristic_parse` (the regex fallback), and the AI tests use a
fake provider. That is the correct design for a suite that must finish in ten
seconds on every save - and it means the component the product is named after is
not covered by any of it.

Both gaps are the job of the accuracy harness, which is opt-in, hits the real
providers, and scores against human-written gold labels:
[backend/eval/README.md](../backend/eval/README.md).
