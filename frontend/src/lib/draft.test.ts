/**
 * A draft under review: what it adds up to, and what goes back to the server
 * once somebody has corrected it. The sums mirror the server's; the server is
 * the one that decides.
 */
import { describe, expect, it } from "vitest";

import {
  acceptPayload,
  documentTotals,
  priceFieldFor,
  repriceLines,
  type ReviewedDraft,
} from "./draft";

describe("what a document adds up to", () => {
  // The order the review window was first asked to total: 5 tea and 10 rice.
  const lines = [
    { quantity: 5, unitPrice: 265 },
    { quantity: 10, unitPrice: 1350 },
  ];

  it("adds tax on top of the lines", () => {
    expect(documentTotals(lines, 18)).toEqual({
      subtotal: 14825,
      discountAmount: 0,
      tax: 2668.5,
      total: 17493.5,
      overDiscount: false,
    });
  });

  it("is the bare subtotal when the business charges no tax", () => {
    expect(documentTotals(lines, 0).total).toBe(14825);
  });

  it("takes a percentage discount off before tax", () => {
    expect(documentTotals(lines, 18, "percentage", 10)).toEqual({
      subtotal: 14825,
      discountAmount: 1482.5,
      tax: 2401.65,
      total: 15744.15,
      overDiscount: false,
    });
  });

  it("takes a flat discount off before tax", () => {
    expect(documentTotals(lines, 18, "amount", 325)).toMatchObject({
      discountAmount: 325,
      tax: 2610,
      total: 17110,
    });
  });

  it("ignores a discount value when the type says there is none", () => {
    expect(documentTotals(lines, 18, "none", 10).total).toBe(17493.5);
  });

  it("treats a negative discount as no discount", () => {
    expect(documentTotals(lines, 18, "amount", -50).discountAmount).toBe(0);
  });

  it("flags a discount worth more than the goods, which the server refuses", () => {
    expect(documentTotals(lines, 18, "amount", 20000)).toMatchObject({
      total: 0,
      overDiscount: true,
    });
    expect(documentTotals(lines, 18, "percentage", 100).overDiscount).toBe(false);
  });

  it("counts a half-typed line as nothing", () => {
    expect(documentTotals([{ quantity: NaN, unitPrice: 265 }], 18).total).toBe(0);
    expect(documentTotals([], 18).total).toBe(0);
  });

  it("rounds to paise", () => {
    expect(documentTotals([{ quantity: 3, unitPrice: 33.33 }], 5)).toMatchObject({
      subtotal: 99.99,
      tax: 5,
      total: 104.99,
    });
  });
});

describe("prices when a draft changes direction", () => {
  const products = [{ id: "oil", sellingPrice: 140, purchasePrice: 100 }];
  const line = (unitPrice: number, productId: string | null = "oil") => ({
    productId,
    description: "Cooking Oil",
    quantity: 4,
    unitPrice,
  });

  it("prices a sale at the selling price and a purchase at the cost", () => {
    expect(priceFieldFor("sale")).toBe("sellingPrice");
    expect(priceFieldFor("purchase")).toBe("purchasePrice");
  });

  it("moves an untouched catalogue price to the other side", () => {
    expect(repriceLines([line(140)], products, "sale", "purchase")[0].unitPrice).toBe(100);
    expect(repriceLines([line(100)], products, "purchase", "sale")[0].unitPrice).toBe(140);
  });

  it("leaves a price somebody typed", () => {
    expect(repriceLines([line(150)], products, "sale", "purchase")[0].unitPrice).toBe(150);
  });

  it("leaves a line that matched no product", () => {
    expect(repriceLines([line(140, null)], products, "sale", "purchase")[0].unitPrice).toBe(140);
    expect(repriceLines([line(140, "gone")], products, "sale", "purchase")[0].unitPrice).toBe(140);
  });

  it("changes nothing when the direction does not change", () => {
    const lines = [line(140)];
    expect(repriceLines(lines, products, "sale", "sale")).toBe(lines);
  });

  it("keeps everything else about the line", () => {
    expect(repriceLines([line(140)], products, "sale", "purchase")[0]).toEqual({
      productId: "oil",
      description: "Cooking Oil",
      quantity: 4,
      unitPrice: 100,
    });
  });
});

describe("what a review sends back", () => {
  const TODAY = "2026-11-10";
  const draft = {
    suggestedType: "sale",
    engine: "heuristic",
    partyId: null,
    partyName: "anita",
    items: [{ productId: "oil", description: "Cooking Oil", quantity: 4, unitPrice: 140 }],
    amount: null,
    category: null,
    discountType: "percentage",
    discountValue: 10,
    date: null,
    note: "anita purchased 4 cooking oil",
  };
  const reviewed = (changes: Partial<ReviewedDraft> = {}): ReviewedDraft => ({
    type: "sale",
    date: TODAY,
    partyId: "c1",
    partyName: "Anita Stores",
    items: draft.items,
    discountType: "percentage",
    discountValue: 10,
    category: "General",
    amount: 0,
    description: "",
    ...changes,
  });

  it("names the party the reviewer picked, not the one the parser guessed", () => {
    expect(acceptPayload(draft, reviewed(), TODAY)).toMatchObject({
      partyId: "c1",
      partyName: "Anita Stores",
    });
  });

  it("records a walk-in when no party is picked", () => {
    const sent = acceptPayload(draft, reviewed({ partyId: null, partyName: null }), TODAY);
    expect(sent.partyId).toBeNull();
    expect(sent.partyName).toBeNull();
  });

  it("sends today as no date, so the server stamps the minute of acceptance", () => {
    expect(acceptPayload(draft, reviewed(), TODAY).date).toBeNull();
    expect(acceptPayload(draft, reviewed({ date: "" }), TODAY).date).toBeNull();
  });

  it("sends any other day as it was picked", () => {
    expect(acceptPayload(draft, reviewed({ date: "2026-11-07" }), TODAY).date).toBe("2026-11-07");
  });

  it("says the same type twice, so the queue agrees with the books", () => {
    expect(acceptPayload(draft, reviewed({ type: "purchase" }), TODAY)).toMatchObject({
      type: "purchase",
      suggestedType: "purchase",
    });
  });

  it("keeps a discount on a sale", () => {
    expect(acceptPayload(draft, reviewed(), TODAY)).toMatchObject({
      discountType: "percentage",
      discountValue: 10,
    });
  });

  it("drops the discount when the draft is flipped to a purchase", () => {
    expect(acceptPayload(draft, reviewed({ type: "purchase" }), TODAY)).toMatchObject({
      discountType: "none",
      discountValue: 0,
    });
  });

  it("drops the discount the reviewer removed", () => {
    expect(acceptPayload(draft, reviewed({ discountType: "none" }), TODAY)).toMatchObject({
      discountType: "none",
      discountValue: 0,
    });
  });

  it("leaves out lines that were emptied", () => {
    const items = [
      ...draft.items,
      { productId: null, description: "  ", quantity: 2, unitPrice: 10 },
      { productId: null, description: "Sugar", quantity: 0, unitPrice: 45 },
    ];
    expect(acceptPayload(draft, reviewed({ items }), TODAY).items).toEqual(draft.items);
  });

  it("carries the rest of the draft through", () => {
    expect(acceptPayload(draft, reviewed(), TODAY)).toMatchObject({
      engine: "heuristic",
      note: "anita purchased 4 cooking oil",
    });
  });

  it("sends an expense as a category, an amount and a description", () => {
    const expense = { ...draft, suggestedType: "expense", items: [], amount: 3200 };
    const sent = acceptPayload(
      expense,
      reviewed({
        type: "expense",
        category: " Utilities ",
        amount: 3250,
        description: " Electricity bill ",
      }),
      TODAY,
    );
    expect(sent).toMatchObject({
      type: "expense",
      suggestedType: "expense",
      category: "Utilities",
      amount: 3250,
      description: "Electricity bill",
      date: null,
    });
  });

  it("files an expense with no category under General", () => {
    const sent = acceptPayload(draft, reviewed({ type: "expense", category: "  " }), TODAY);
    expect(sent.category).toBe("General");
  });

  it("survives a message that produced no draft at all", () => {
    expect(acceptPayload(null, reviewed(), TODAY)).toMatchObject({
      type: "sale",
      partyId: "c1",
      items: draft.items,
    });
  });
});
