# Feature reference

What each page does: sales, purchases, stock, parties, reports and alerts.

[&larr; Back to the README](../README.md)

---

## Feature tour

### Dashboard
Six KPI cards (sales, purchases, expenses, inventory value, receivable, payable),
each clicking through to its page. Revenue chart, a **business-health score**
(cash flow, profitability, revenue and inventory, weighted 30 / 30 / 25 / 15,
with "Not enough data yet" until there is something to score; how each part is
worked out is in [Business health](business-health.md)), Recent Sales and
Recent Purchases side by side, and a low-stock "Needs attention" panel.

### Smart Input (`/input`)
Two modes: **natural language** (type `Sold 10 rice bags to Kumar Traders`) and
**image / OCR** (upload an invoice, order slip or WhatsApp screenshot). Either way
you land on a **confirmation screen** with the extracted party, line items,
discount and date, all editable, before anything is written. Typed text and the
parsed draft both survive navigating away and back, until the draft is published.

### Sales & Purchases
Full list with source badge (Form / AI·Text / AI·OCR) and payment status, which
reads **Overdue** once an unpaid balance is past its deadline. Click **any row**
for a detail modal with line items, totals, a click-to-edit transaction date, a
click-to-edit payment deadline, and the list of payments against the document
with the day each one came. Inline "Record payment" (amount and the date it was
paid, defaulting to today, with the picker limited to the days a payment may
carry: see [below](#which-day-a-payment-may-carry)) and "Cancel"; cancelling
reverses inventory and the party balance. Sales also have a printable invoice at `/sales/:id`, which
carries the payment deadline and the payments made against it (date, how it
was paid, amount), on screen and on paper.

Both support **discounts** (flat amount or percentage) applied to the subtotal
before tax, with a live preview while you type and a hard block when the discount
exceeds the document value.

### Transaction dates
Every sale and purchase carries a business `date` separate from `created_at`. It
defaults to today, can be set at creation, and corrected afterwards from the
detail modal, for entries logged late. Lists, charts, analytics and reports all
key off this date.

### Payment deadlines and the payment ledger
Every sale and purchase also carries a **due date**: the day its unpaid balance
is expected. It is the document date plus a number of credit days, which comes
from the first of these that is set:

1. the one document, extended by hand from its detail modal (for the customer
   who needs longer this once);
2. the party, from the "Payment deadline (days)" field on the customer or
   supplier (for the friend who always gets 60 days);
3. the business default on the Settings page, 30 days at sign-up.

Correcting a document's date moves its deadline by the same amount.

Every rupee that moves is recorded in a **payment ledger** with the day it
moved: money taken at the time of the sale or purchase, a payment recorded
later (dated whenever it actually came, not when it was typed in), or a
settlement. The ledger is what lets the business-health score tell on-time
from late; see [Business health](business-health.md#cash-flow-30).

#### Which day a payment may carry

Any day from the document's own date up to today, and nothing outside that:

- **Not before the sale or purchase.** Money cannot arrive for an invoice that
  did not exist yet.
- **Not after today.** A shopkeeper on the 10th has not been paid on the 11th.
  The refusal says what today is.
- **The document's own day always counts**, whatever time of day the document
  was made. This is a rule about calendar days, not clock times. It used to
  compare instants, and an order accepted from Telegram or email (stamped with
  the minute it was accepted, say 3:42 pm) could not be paid that same day,
  because a date picked in the dialog is stored as noon, and noon is "before"
  3:42 pm. Invoices typed into Smart Input or the form are themselves stored
  at noon, which is why only inbound orders showed it.
- **A document dated ahead of today** (an order booked for next week) takes no
  payment until its day comes; the dialog says so and disables the date.

The server enforces all four in `payment_moment()` in
[`app/domain/payments.py`](../backend/app/domain/payments.py) and answers 400
with the reason. The "Record payment" dialog applies the same rule first
(`paymentDateWindow()` in [`src/lib/payments.ts`](../frontend/src/lib/payments.ts)):
the date picker only offers days in the window, and a date outside it is
explained under the field with Save switched off.

"Today" is the shop's today, not the server's. A hosted server runs in UTC,
which for a shop in India is five and a half hours behind, so between midnight
and 5:30 am a payment dated today would have been refused as "in the future".
`APP_TIMEZONE` (default `Asia/Kolkata`) puts the whole process on the shop's
clock; see [Environment variables](setup.md#environment-variables).

Each payment also records **how** it was paid. "Record payment", and the
amount-paid section of a new sale or purchase, ask "Paid by" and then only for
what that mode needs:

| Paid by | Asked for | Optional extras |
|---|---|---|
| Cash | nothing | |
| UPI | transaction ID (UTR) | payer's UPI ID |
| Card | last 4 digits only | credit / debit, approval code |
| Cheque | cheque number | bank, date on the cheque |
| Bank transfer | UTR / reference (NEFT, RTGS, IMPS) | bank |
| Other | a short description | |

The full card number is never recorded: the server refuses anything longer
than four digits rather than trimming it. Settlements ("Mark paid" / "Pay
all"), payments taken through Smart Input, inbound orders, and anything paid
before this existed have no mode and show as "Mode not recorded" rather than
being guessed as cash.

### Parties (`/parties`)
Customers and suppliers with running balances and their own payment deadline.
Each party row expands to show the individual unpaid invoices/bills behind its
balance, each with its due date and marked when it is overdue, with **"Pay
all"** per party and **"Mark all as paid"** for all receivables or all payables.
Phone numbers use a country-code dropdown (202 countries).

"Pay all" for one party needs the same permission as taking a payment against a
single bill, so an employee can use it; "Mark all as paid" across the business
is owner-only.

### Products, Expenses, Notifications
Inventory with stock, HSN/SKU, low-stock thresholds and a stock-movement history;
manual stock adjustments that can never drive stock negative; categorised expenses
with their own dates; an alerts inbox fed by the workflow engine.

### Alert log

Alerts are raised by workflow rules and listed on the Notifications page. Each
one records **which rule fired, on which event, and therefore who caused it**
(`notifications.event_id` / `rule_id`, migration `0005`), which is the difference
between a message and something you can audit.

The list filters by severity and by unread, and an alert can be marked unread
again, dismissed, or cleared in bulk once dealt with. Reading and marking need
`data:read`; **dismissing and "Clear read" need `data:manage`**, so those two
buttons are hidden from employees and admins rather than offered and refused. Both source columns are
nullable and `SET NULL` on delete: an alert outlives the rule that raised it
rather than vanishing with it, and shows no source instead.

The notify action dedupes against *unread* alerts of the same title, so a noisy
rule cannot bury the one that matters.

The red count on the bell in the top bar follows the list. "Mark read",
"Unread", "Mark all read", dismissing and "Clear read" all update it at once, and
so does anything else that could raise an alert (recording a sale that trips a
rule, for example). The app shell listens for every successful write and
refetches the unread and Inbox counts; before this it only refetched on a
change of page, so the number was stale until you left Notifications.

### Info tips

A small **i** in a circle sits beside the page titles and the fields a first
visit does not explain by itself. Hover it, tab to it, or tap it (a tap pins it
open until you tap elsewhere or press Escape) for two or three sentences on
what the thing is and what it changes. They are on:

| Page | What the tips explain |
|---|---|
| Dashboard | how the business-health score is weighted and banded; what puts a product under "Needs attention" |
| Smart Input | what to type, in which languages, and that nothing is saved until you confirm |
| Sales, Purchases | what the list shows and how a row opens; where a document's "Due by" date comes from and that it can be extended for this one document |
| Parties | what a balance is; that "Payment deadline (days)" overrides the business default for this party only, and applies to documents made from then on |
| Settings | the invoice prefix and how numbers are formed; the default payment deadline (30 days) and how one party or one document overrides it |
| Products | stock, and what the low-stock threshold triggers |
| Expenses, Reports, Inbox, Notifications, Event bus | what the page is for |
| Workflow | what a rule is; the exact field names a condition can test for each event; what each of the four actions does |
| Team | the two roles and what an employee can do; how long an invitation lasts |

The tips are for the screen only and are left off printed invoices. The
component is described in [Design system](design.md).

---

## Reports (`/reports`)
KPI cards, a **trend chart** with a Y axis, hover tooltips showing exact values,
a switch between **sales, purchases and expenses**, and a range selector (last
week / month / 3 / 6 months / year) that buckets daily, weekly or monthly as
appropriate. Top products, top customers, top suppliers, expenses by category,
cash-flow summary, and **downloadable reports** (see below).

### Workflow (`/workflow`) and Event bus (`/events`)
Toggle built-in rules or add your own `WHEN <event> [condition] THEN <action>`
rule. The event bus page shows events flowing `pending → done`, with retry,
dead-letter, replay and a manual drain, and polls while open.

---

## Reports

`app/reports.py` builds a report for a **type** (sales, purchases, expenses, or
everything consolidated) over a **period**: today, last 7 days, this month, last
month, last 3 / 6 months, this year, last 12 months, or a custom range. It renders
server-side to **PDF** (reportlab, landscape A4, repeating table headers and page
numbers) or **CSV**, served as a normal download:

```
GET /api/reports/download?type=consolidated&preset=month&fmt=pdf
GET /api/reports/preview?type=sales&preset=last_12_months     # totals as JSON
```

Two deliberate details: cancelled documents are **listed but excluded from
totals** (the accountant-correct behaviour), and amounts print as plain grouped
numbers with the currency stated once in the header, because the PDF core fonts
have no rupee glyph.

Invoices print in **light mode regardless of the app theme**: the print handler
temporarily removes the `.dark` class and the app chrome is hidden with
`print:hidden`, so only the invoice reaches the page.

---

