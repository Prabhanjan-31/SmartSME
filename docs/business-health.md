# Business health

How the dashboard's health score is worked out, why each weight and threshold is
what it is, and what the score cannot see.

[&larr; Back to the README](../README.md)

---

## In plain words

The card gives the business a mark out of 100, made from four smaller marks:

| Part | The question it answers | Share of the total |
|---|---|---|
| **Cash flow** | Is money actually coming in when it should, and going out no faster than it comes in? | 30% |
| **Profitability** | After paying for the goods and the bills, is there anything left? | 30% |
| **Revenue** | Are sales going up or down compared with the last few months? | 25% |
| **Inventory** | Are the things that sell well on the shelf, and is anything just gathering dust? | 15% |

Each part is a mark out of 100 too, and every mark reads the same way:

| Mark | Label | Meaning |
|---|---|---|
| 70 and up | Healthy | Fine. Nothing here needs attention. |
| 40 to 69 | Fair | Worth a look. Not a problem yet. |
| Below 40 | At risk | Needs doing something about. |

Two rules keep the overall mark honest:

- **One bad part cannot hide behind three good ones.** The overall can never be
  more than 30 points above the weakest part. If cash flow is At risk, the
  business cannot read Healthy, however good the rest looks.
- **No guessing.** A part with nothing to measure shows "No data yet" instead of
  a number, and the overall only appears once at least half the weight has real
  data behind it. A business that has recorded nothing has no score at all.

Where it lives:

- `backend/app/health.py`: every formula and constant. `gather()` runs the SQL;
  the `score_*` functions are pure, so they are tested without a database.
- `backend/app/analytics.py`: `load_overview()` calls it for `GET /api/dashboard`
  and `GET /api/reports/overview`.
- `frontend/src/lib/health.ts`: the bands and labels; `pages/Dashboard.tsx` draws
  the card.

---

## The four parts

Each part below starts with the plain version, then the exact arithmetic for
anyone changing it.

### Cash flow (30%)

**In plain words.** Three questions, each answered 0 to 100, then averaged:

1. **Are customers paying you by the deadline?** Of the money customers owed on
   credit, how much arrived by the due date (or is not yet due)? All of it: 100.
   None of it: 0.
2. **Are you paying your suppliers by the deadline?** The same question the
   other way round. Falling behind with suppliers is one of the first signs a
   shop is short of cash.
3. **Is more money coming in than going out?** Over the last three months, cash
   received against sales, against cash paid to suppliers plus expenses. Keeping
   a fifth of what comes in: 100. Break-even: 50. Spending a fifth more than
   comes in: 0.

A question with nothing to measure is left out. A shop where every customer pays
at the counter has no credit to collect, so only the questions that apply are
averaged.

**Where the deadline comes from.** Every invoice and bill has a payment
deadline, `due_date`. It is the document's date plus the party's credit days,
or the business default from Settings (30 unless changed). Any one document's
deadline can be extended from its detail view, for the customer who needs
longer.

**Where the dates come from.** Every rupee that moves is written to the
`payments` ledger with the day it moved: money taken at the time of the sale or
purchase (reason `sale` or `purchase`), a payment recorded later (`payment`),
or a party or everything being settled at once (`settlement`). A later payment
is on time if its date is on or before the deadline. Money still owed is on
time until the deadline passes, then late.

**The arithmetic.** All over the last 90 days.

```
collecting = on-time credit from customers / (on-time + late credit from customers)
paying     = on-time credit to suppliers  / (on-time + late credit to suppliers)
movement   = 0.5 + 2.5 x (cash in - cash out) / cash in        (held between 0 and 1)
cash flow  = 100 x average of whichever of the three have data
```

"Credit" means money that was still owed after the day of the document, so a
sale paid in full at the counter is not part of the first two questions. It is
part of the third.

| Situation | Score |
|---|---|
| Cash-only shop, pays suppliers at the counter, keeps a fifth of what comes in | 100 |
| Same shop, spending exactly what comes in | 50 |
| Same shop, spending a fifth more than comes in | 0 |
| Customers all pay by the deadline; nothing else to measure | 100 |
| ₹10 lakh owed by customers, all of it past the deadline | 0 |
| Customers on time, but the shop is behind with every supplier bill | 50 |
| A supplier bill not yet due, and the shop keeping a tenth of what comes in | 88 |

**Why these three.** The score before this one judged cash by comparing what
was owed to the business against what it owed, which rewarded being owed money:
₹10 lakh of uncollected invoices scored 95. Money you have not received is not
cash. These three questions only look at money that moved, and when.

**Why movement runs from -20% to +20%.** Over three months, a shop that spends a
fifth more than it takes in is burning through whatever it had; one that keeps a
fifth is building a cushion. Between those two, the score is a straight line.

**Why the ledger, not a bank balance.** SmartSME does not know the bank balance,
and the owner's own drawings are not recorded, so "cash on hand" would be a
guess. What *is* known exactly is which rupee moved on which day. That is
enough to say whether customers pay on time, whether suppliers are being paid on
time, and whether the shop took in more than it paid out.

**No data** means no credit in either direction and no money moved in 90 days.

### Profitability (30%)

**In plain words.** Out of every ₹100 of sales (not counting GST), how much is
left after paying for the goods and the bills? Nothing left scores 40. ₹5 left
scores 70. ₹10 or more left scores 100. Losing money scores below 40.

**The arithmetic.** Net margin over the last 90 days:

```
margin = (sales net of GST - cost of goods sold - expenses) / sales net of GST
score  = 40 + 600 x margin                                          (held between 0 and 100)
```

| Net margin | Score | Band |
|---|---|---|
| -6.7% or worse | 0 | At risk |
| -5% | 10 | At risk |
| 0% (break-even) | 40 | Fair |
| 5% | 70 | Healthy |
| 10% or more | 100 | Healthy |

**Why these anchors.** Losing money is At risk by definition, so break-even sits
exactly on the edge of Fair. Single-digit net margins are normal for small
traders and retailers, so 5% is where Healthy starts and 10% is the top of the
scale rather than the middle of it.

**Why 90 days and not 30.** Rent, salaries and utilities land once a month. A
30-day window that happens to miss the rent, or catches two payments of it,
moves the margin by a whole month's rent. Ninety days holds about three of each.

**Why net of GST.** GST collected on a sale is owed to the government, not
earned. Counting it overstates the margin by roughly the tax rate. The Gross
profit figure on the dashboard and the Reports page uses net-of-GST sales as
well.

**Cost of goods sold** is quantity sold multiplied by the product's purchase
price.

**No data** means no sales in the last 90 days. Recording rent before the first
sale does not produce a score of 0.

### Revenue (25%)

**In plain words.** Were the last 30 days better or worse than a normal month?
"Normal" is the average month out of the three months before that. Same as
normal scores 75. Every 1% better adds a point, every 1% worse takes one away.
So 25% better is 100, and 35% worse is where At risk begins. If only a handful
of sales make up the comparison, a single big order could swing it, so the
change counts for less until there are about twenty.

**The arithmetic.** Sales over the last 30 days against the monthly average of
the 90 days before them (days 31 to 120):

```
growth = (last 30 days - baseline monthly average) / baseline monthly average
score  = 75 + 100 x growth x confidence                             (held between 0 and 100)
```

| Change | Score |
|---|---|
| +25% or more | 100 |
| +5% | 80 |
| Flat | 75 |
| -5% | 70 |
| -35% | 40 |
| -75% or worse | 0 |

**Why 75 for flat.** Steady sales are healthy, and the ordinary few-percent wobble
between months should not push a business out of Healthy. A 35% fall, where At
risk begins, is a serious one.

**Why a 90-day baseline.** Comparing one month with the month before lets a
single unusual month, a festival or a bulk order, decide the score. A
three-month average is steadier.

**Confidence.** Below 20 sales in the baseline, growth is scaled by `sales / 20`.
With a single baseline sale, doubling scores 80, not 100. Twenty is one or two
sales a week across the baseline.

**Young businesses** are compared on the days they actually traded. The baseline
starts at the first sale, so a shop that began selling 50 days ago is compared
against its 20 days of baseline, scaled to a month. With fewer than 14 days of
baseline there is nothing meaningful to compare, and revenue shows No data yet.

**A business that has stopped selling** (nothing in the last 120 days) scores 0.
One that starts selling again after a gap that long scores 75, since there is
nothing recent to grow from.

### Inventory (15%)

**In plain words.** Two things. First, are the products that actually sell on
the shelf? A best seller that is out of stock hurts far more than a slow line
that is out. Fully stocked: 100. Running low (at or under the product's
low-stock threshold) counts half. Out of stock counts nothing. That is 70% of
the mark. The other 30%: how much of the stock, by what it cost, has not sold
at all in three months? None: full marks. Half of it: half marks.

**The arithmetic.**

```
inventory = 100 x (0.7 x availability + 0.3 x (1 - dead stock share))
```

**Availability.** Each product is in stock (counts 1), low (0.5) or out (0),
weighted by its sales over the last 90 days. With two products, one making 90%
of sales, running out of the best seller scores 37; running out of the other
scores 93. If nothing sold in 90 days, every product counts equally.

**Dead stock share.** The cost value of stock that has not sold in 90 days, as a
share of all stock on hand. Products added in the last 90 days are left out: they
have not had a fair chance to sell.

**Why 70/30.** A stockout loses a sale today, and a customer who finds the shelf
empty may not come back. Dead stock ties up cash, but it can be discounted or
returned.

**No data** means no products.

---

## The overall score

### Weights

| Part | Weight |
|---|---|
| Cash flow | 30 |
| Profitability | 30 |
| Revenue | 25 |
| Inventory | 15 |

**Cash flow and profitability carry the most** because between them they decide
whether the business survives, on two different clocks. Cash is the short-run
constraint: a small business rarely has credit to bridge a gap, so it can be
profitable on paper and still fail to pay its rent or its suppliers. Late
payment is a big enough problem for Indian small businesses that the MSMED Act
caps the payment terms a buyer can agree with a micro or small supplier at 45
days. Profit is the long-run constraint: a business that keeps losing money runs
out of cash eventually, however well it collects. Neither outranks the other, so
they get the same weight.

**Revenue gets a little less.** It is the most reliably recorded number in
SmartSME and the earliest warning, but it is noisy from month to month, and growth
on its own does not make a business healthier: selling more at a loss makes
things worse. What revenue does to the bottom line is already in profitability.

**Inventory gets the least,** because most of what goes wrong with stock already
shows up in the other three: a stockout as lost revenue, dead stock as cash tied
up. Weighting it higher would count the same problem twice. It also rests on
stock counts being kept accurate, which is the data small shops most often let
drift, and a business that holds no stock has no inventory part at all.

**Splits considered and not used:**

- *Equal weights (25 each)*, which is what the original plain average was. It
  gives stock the same say as cash. In practice inventory had the most pull on
  that score, since it was the only part that could swing from 0 to 100; cash
  flow could only move between 40 and 95.
- *Cash flow first (35 / 30 / 20 / 15)*. Now that cash flow reads the payment
  ledger it is a direct measure, and this split is more defensible than it was.
  It is still not used, because the ledger starts on the day it was introduced:
  older paid invoices have no payment date, so for the first few months the
  cash-flow part leans on fewer facts than profitability does.

**The weights only matter while every part is at least Fair.** Once any part
falls into At risk, the cap below decides the overall score, so a crisis in any
one area shows whatever its weight.

### When a part has no data

It drops out and the remaining weights are scaled up in proportion. If less than
half of the weight (50 points) is left, there is no overall score. Inventory and
revenue alone (40) are not enough; cash flow and profitability (60) are.

### The cap

The overall can be at most 30 points above the weakest part. Thirty is the width
of the Fair band, so:

- any part in At risk (below 40) keeps the overall out of Healthy;
- any part below 10 puts the overall in At risk.

With cash flow at 10 and everything else at 100, the weighted average is 73, but
the overall is 40.

---

## What the score cannot see

- **Cash in the bank.** SmartSME has no bank balance, and the owner's drawings
  are not recorded. Cash flow knows what moved, not what is left.
- **Payments before the ledger existed.** A document paid before this version
  has one ledger row dated on the document itself, because that was the only
  date the old schema kept. Those count as paid on the day, never late. The
  on-time checks become meaningful as new payments are recorded.
- **GST remittance.** GST collected is paid to the government outside SmartSME,
  so cash in includes it and cash out does not.
- **What stock actually cost.** Cost of goods uses each product's current
  purchase price, not the price paid for the units that were sold.
- **Free-text sale lines.** A line with no product attached has no cost, so it
  overstates the margin.
- **Seasons.** A festival month compared with the three months before it looks
  like strong growth, and the month after it like a fall. Comparing against the
  same month last year would fix that once a year of data exists.
- **The kind of business.** The profitability bands suit most small traders and
  retailers; a very thin-margin wholesaler can sit in Fair while doing well. A
  service recorded as a product with no stock counts as out of stock.
- **GST on expenses.** Expenses are taken at face value, including any GST paid
  on them.

---

## Changing the numbers

Every window, threshold and weight is a named constant at the top of
`backend/app/health.py`:

| Constant | Value | What it sets |
|---|---|---|
| `RECENT_DAYS` | 30 | The recent revenue window |
| `LOOKBACK_DAYS` | 90 | Profitability, sales velocity, dead stock, on-time payment, cash movement |
| `BASELINE_DAYS` | 90 | How far back the revenue baseline reaches |
| `MIN_BASELINE_DAYS` | 14 | Baseline history needed before revenue is scored |
| `FULL_CONFIDENCE_SALES` | 20 | Baseline sales needed for growth to count in full |
| `WEIGHTS` | 30 / 30 / 25 / 15 | The overall weights |
| `MIN_WEIGHT` | 50 | Weight that must have data for an overall score |
| `CAP_ABOVE_WEAKEST` | 30 | How far the overall may sit above the weakest part |

The default payment deadline is a business setting (`businesses.credit_days`,
30 at sign-up), overridable per party (`parties.credit_days`) and per document
(`due_date`). `DEFAULT_CREDIT_DAYS` in `backend/app/domain/payments.py` is the
fallback if neither is set.

The shapes of the curves (75 + 100 x growth, 40 + 600 x margin, 0.5 + 2.5 x
movement, the 70/30 split) are in the `score_*` functions beside them. Change
any of them and `tests/test_health.py` points at exactly which documented
behaviour moved; update this page to match.

## Tests

`backend/tests/test_health.py`, 55 tests. The pure functions are pinned at every
threshold on this page, with no database. Four end-to-end tests go through the
API: an empty business has no score, products alone are not enough for one,
credit to a named customer is counted once, and one business built to known
numbers (back-dated sales, purchases, expenses, dated payments both on time and
late, a cancelled sale and a dead product) has every gathered input checked to
the rupee and every score checked against hand-worked arithmetic.

`backend/tests/test_payments.py`, 26 tests, covers the ledger and the deadlines
the cash-flow part reads: where a deadline comes from, extending one, that the
deadline moves with a corrected date, that payments are dated, that a payment
cannot predate its document, that settlements write ledger rows, and the
overdue flag.

`frontend/src/lib/health.test.ts` covers the bands and checks that a part with no
data never renders as a red zero.
