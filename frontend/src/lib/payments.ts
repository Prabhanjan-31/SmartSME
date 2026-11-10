/**
 * How a payment was made, and what each way needs recorded with it.
 *
 * This mirrors `PAYMENT_MODES` in backend/app/domain/payments.py. The server
 * is the one that enforces the rules; what lives here is the form: which
 * fields to show for each mode, and the same checks run early so the person
 * is told before the request goes out.
 */

import { formatDate, toDateInputValue } from "./utils";

export type PaymentMode = "cash" | "upi" | "card" | "cheque" | "bank_transfer" | "other";

export interface FieldSpec {
  key: string;
  label: string;
  placeholder?: string;
  hint?: string;
  type?: "text" | "date" | "select";
  options?: { value: string; label: string }[];
  inputMode?: "numeric" | "text";
  maxLength?: number;
}

export interface PaymentModeSpec {
  key: PaymentMode;
  label: string;
  /** The identifier this mode needs. Absent for cash. */
  reference?: FieldSpec;
  /** Optional extras, stored under their key in `details`. */
  details: FieldSpec[];
}

export const PAYMENT_MODES: PaymentModeSpec[] = [
  { key: "cash", label: "Cash", details: [] },
  {
    key: "upi",
    label: "UPI",
    reference: {
      key: "reference",
      label: "Transaction ID",
      placeholder: "326514789012",
      hint: "The UTR / reference number shown in the UPI app.",
      inputMode: "numeric",
      maxLength: 64,
    },
    details: [{ key: "upiId", label: "Payer's UPI ID (optional)", placeholder: "name@bank" }],
  },
  {
    key: "card",
    label: "Card",
    reference: {
      key: "reference",
      label: "Last 4 digits of the card",
      placeholder: "4242",
      hint: "Only the last four. The full card number is never recorded.",
      inputMode: "numeric",
      maxLength: 4,
    },
    details: [
      {
        key: "cardType",
        label: "Card type",
        type: "select",
        options: [
          { value: "", label: "Not sure" },
          { value: "credit", label: "Credit" },
          { value: "debit", label: "Debit" },
        ],
      },
      { key: "approvalCode", label: "Approval code (optional)", placeholder: "From the slip" },
    ],
  },
  {
    key: "cheque",
    label: "Cheque",
    reference: {
      key: "reference",
      label: "Cheque number",
      placeholder: "004512",
      inputMode: "numeric",
      maxLength: 20,
    },
    details: [
      { key: "bank", label: "Bank (optional)", placeholder: "HDFC Bank" },
      { key: "chequeDate", label: "Date on the cheque (optional)", type: "date" },
    ],
  },
  {
    key: "bank_transfer",
    label: "Bank transfer",
    reference: {
      key: "reference",
      label: "UTR / reference number",
      placeholder: "HDFCN52026091412345",
      hint: "NEFT, RTGS or IMPS reference from the bank statement.",
      maxLength: 64,
    },
    details: [{ key: "bank", label: "Bank (optional)", placeholder: "HDFC Bank" }],
  },
  {
    key: "other",
    label: "Other",
    reference: {
      key: "reference",
      label: "Details",
      placeholder: "e.g. adjusted against credit note CN-12",
      maxLength: 64,
    },
    details: [],
  },
];

export interface PaymentFields {
  mode: PaymentMode;
  reference: string;
  details: Record<string, string>;
}

export interface PaymentPayload extends Omit<PaymentFields, "reference"> {
  amount: number;
  /** `yyyy-mm-dd`: the day the money moved. */
  date: string;
  reference: string | null;
}

export function emptyPayment(mode: PaymentMode = "cash"): PaymentFields {
  return { mode, reference: "", details: {} };
}

export function specFor(mode: string): PaymentModeSpec {
  return PAYMENT_MODES.find((m) => m.key === mode) ?? PAYMENT_MODES[0];
}

/** What is wrong with the fields as typed, or null when they can be sent. */
export function paymentProblem(p: PaymentFields): string | null {
  const spec = specFor(p.mode);
  if (!spec.reference) return null;
  const ref = p.reference.trim();
  if (!ref) return `${spec.label} payments need the ${spec.reference.label.toLowerCase()}.`;
  if (p.mode === "card" && !/^\d{4}$/.test(ref)) {
    return "Enter only the last four digits of the card.";
  }
  if (p.mode === "cheque" && !/^[A-Za-z0-9-]{1,20}$/.test(ref)) {
    return "A cheque number is letters, digits and dashes only.";
  }
  if (ref.length > (spec.reference.maxLength ?? 64)) return "That reference is too long.";
  return null;
}

/** The days a payment against a document may be dated, as `yyyy-mm-dd`. */
export interface PaymentDateWindow {
  /** The document's own day: money cannot arrive before the sale it pays. */
  earliest: string;
  /** Today: a payment that has not happened yet cannot be recorded. */
  latest: string;
  /** What to tell the person when `date` is outside the window, else null. */
  problem: string | null;
}

/**
 * Whether a payment may carry this date. Mirrors `payment_moment` on the
 * server, which is the one that enforces it.
 *
 * Whole days are compared, never times. The document's date arrives with a
 * time on it (an order accepted from Telegram at 15:42 says so), while the
 * date picked here has none, and a payment on the document's own day is
 * always allowed whatever the clock said.
 */
export function paymentDateWindow(
  date: string,
  documentDate: string,
  noun: string,
  now: Date = new Date(),
): PaymentDateWindow {
  const earliest = toDateInputValue(documentDate);
  const latest = toDateInputValue(now);
  let problem: string | null = null;
  if (earliest > latest) {
    problem =
      `This ${noun} is dated ${formatDate(documentDate)}, which has not arrived yet. ` +
      `Record the payment on that day, or correct the ${noun} date first.`;
  } else if (!date) {
    problem = "Choose the day the money was paid.";
  } else if (date > latest) {
    problem = "A payment cannot be dated in the future.";
  } else if (date < earliest) {
    problem = `A payment cannot be dated before the ${noun} itself (${formatDate(documentDate)}).`;
  }
  return { earliest, latest, problem };
}

/** The request body for a payment, with empty extras dropped. */
export function toPayload(p: PaymentFields, amount: number, date: string): PaymentPayload {
  const details: Record<string, string> = {};
  for (const [k, v] of Object.entries(p.details)) if (v && v.trim()) details[k] = v.trim();
  return {
    amount,
    date,
    mode: p.mode,
    reference: specFor(p.mode).reference ? p.reference.trim() || null : null,
    details,
  };
}

/** One line for a ledger row: "UPI · 326514789012", "Card ending 4242 (debit)". */
export function describePayment(p: {
  mode: string | null;
  reference: string | null;
  details: Record<string, string> | null;
}): string {
  if (!p.mode) return "Mode not recorded";
  const d = p.details ?? {};
  switch (p.mode) {
    case "cash":
      return "Cash";
    case "upi":
      return `UPI · ${p.reference ?? ""}${d.upiId ? ` · ${d.upiId}` : ""}`;
    case "card":
      return `Card ending ${p.reference ?? "????"}${d.cardType ? ` (${d.cardType})` : ""}`;
    case "cheque":
      return `Cheque ${p.reference ?? ""}${d.bank ? ` · ${d.bank}` : ""}${
        d.chequeDate ? ` · dated ${d.chequeDate}` : ""
      }`;
    case "bank_transfer":
      return `Bank transfer · ${p.reference ?? ""}${d.bank ? ` · ${d.bank}` : ""}`;
    case "other":
      return `Other · ${p.reference ?? ""}`;
    default:
      return p.mode;
  }
}
