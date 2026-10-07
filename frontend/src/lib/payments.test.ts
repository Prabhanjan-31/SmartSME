/**
 * The payment-mode form rules, run on the client before the request goes
 * out. They mirror the server's; the server is the one that enforces them.
 */
import { describe, expect, it } from "vitest";

import {
  PAYMENT_MODES,
  describePayment,
  emptyPayment,
  paymentProblem,
  toPayload,
} from "./payments";

describe("which fields each mode asks for", () => {
  it("cash asks for nothing", () => {
    const cash = PAYMENT_MODES.find((m) => m.key === "cash")!;
    expect(cash.reference).toBeUndefined();
    expect(cash.details).toEqual([]);
  });

  it.each([
    ["upi", "Transaction ID"],
    ["card", "Last 4 digits of the card"],
    ["cheque", "Cheque number"],
    ["bank_transfer", "UTR / reference number"],
    ["other", "Details"],
  ])("%s asks for its %s", (mode, label) => {
    expect(PAYMENT_MODES.find((m) => m.key === mode)!.reference!.label).toBe(label);
  });

  it("offers the same modes the server accepts", () => {
    expect(PAYMENT_MODES.map((m) => m.key)).toEqual([
      "cash",
      "upi",
      "card",
      "cheque",
      "bank_transfer",
      "other",
    ]);
  });
});

describe("paymentProblem", () => {
  it("passes cash with nothing filled in", () => {
    expect(paymentProblem(emptyPayment("cash"))).toBeNull();
  });

  it("wants the identifier for every other mode", () => {
    expect(paymentProblem(emptyPayment("upi"))).toMatch(/transaction id/i);
    expect(paymentProblem(emptyPayment("cheque"))).toMatch(/cheque number/i);
    expect(paymentProblem(emptyPayment("bank_transfer"))).toMatch(/utr/i);
  });

  it("takes only the last four digits of a card", () => {
    expect(paymentProblem({ ...emptyPayment("card"), reference: "4111111111111111" })).toMatch(
      /last four/,
    );
    expect(paymentProblem({ ...emptyPayment("card"), reference: "4242" })).toBeNull();
  });
});

describe("toPayload", () => {
  it("drops empty extras and trims the reference", () => {
    const body = toPayload(
      { mode: "cheque", reference: " 004512 ", details: { bank: "", chequeDate: "2026-10-01" } },
      500,
      "2026-10-07",
    );
    expect(body).toEqual({
      amount: 500,
      date: "2026-10-07",
      mode: "cheque",
      reference: "004512",
      details: { chequeDate: "2026-10-01" },
    });
  });

  it("sends no reference for cash even if one was typed", () => {
    expect(
      toPayload({ mode: "cash", reference: "x", details: {} }, 1, "2026-10-07").reference,
    ).toBe(null);
  });
});

describe("describePayment", () => {
  it.each([
    [{ mode: "cash", reference: null, details: null }, "Cash"],
    [{ mode: "upi", reference: "3265", details: { upiId: "a@okaxis" } }, "UPI · 3265 · a@okaxis"],
    [
      { mode: "card", reference: "4242", details: { cardType: "debit" } },
      "Card ending 4242 (debit)",
    ],
    [
      { mode: "cheque", reference: "004512", details: { bank: "SBI", chequeDate: "2026-10-01" } },
      "Cheque 004512 · SBI · dated 2026-10-01",
    ],
    [{ mode: "bank_transfer", reference: "UTR1", details: {} }, "Bank transfer · UTR1"],
    [{ mode: "other", reference: "credit note", details: {} }, "Other · credit note"],
  ])("%o reads as %s", (row, text) => {
    expect(describePayment(row)).toBe(text);
  });

  it("says when the mode was never recorded, rather than guessing cash", () => {
    expect(describePayment({ mode: null, reference: null, details: null })).toBe(
      "Mode not recorded",
    );
  });
});
