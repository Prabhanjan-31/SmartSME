/**
 * A draft on its way to being recorded: what it adds up to, and what a review
 * screen sends back once somebody has corrected it.
 *
 * The sums mirror the server's (`calculate_sale_totals` and its purchase
 * twin). The server is the one that decides; this exists so the number on the
 * screen is the number that gets stored.
 */
import { round2 } from "./utils";

export type DiscountType = "none" | "amount" | "percentage";
export type DraftType = "sale" | "purchase" | "expense";

export interface DraftLine {
  productId: string | null;
  description: string;
  quantity: number;
  unitPrice: number;
}

export interface DocumentTotals {
  subtotal: number;
  discountAmount: number;
  tax: number;
  total: number;
  /** The discount is worth more than the goods. The server refuses this. */
  overDiscount: boolean;
}

/** Subtotal, discount, tax and total. The discount comes off before tax. */
export function documentTotals(
  lines: Pick<DraftLine, "quantity" | "unitPrice">[],
  taxRate: number,
  discountType: DiscountType = "none",
  discountValue = 0,
): DocumentTotals {
  const subtotal = round2(
    lines.reduce((sum, line) => sum + (line.quantity || 0) * (line.unitPrice || 0), 0),
  );
  const discountAmount =
    discountType === "amount"
      ? round2(Math.max(0, discountValue))
      : discountType === "percentage"
        ? round2((subtotal * Math.max(0, discountValue)) / 100)
        : 0;
  const discounted = round2(Math.max(0, subtotal - discountAmount));
  const tax = round2(discounted * (taxRate / 100));
  return {
    subtotal,
    discountAmount,
    tax,
    total: round2(discounted + tax),
    overDiscount: discountType !== "none" && discountAmount > subtotal,
  };
}

export interface PricedProduct {
  id: string;
  sellingPrice: number;
  purchasePrice: number;
}

/** A sale is priced at what the shop sells for, a purchase at what it pays. */
export function priceFieldFor(type: DraftType): "sellingPrice" | "purchasePrice" {
  return type === "purchase" ? "purchasePrice" : "sellingPrice";
}

/**
 * The lines of a draft after its direction is flipped between sale and
 * purchase.
 *
 * A draft is priced for the direction the parser guessed. Flip a sale to a
 * purchase and leave the prices alone, and the shop "buys" at its own selling
 * price. So a line still carrying the catalogue price for the old direction
 * takes the catalogue price for the new one. A price somebody typed, or one
 * read off a slip, is left as it is.
 */
export function repriceLines<T extends DraftLine>(
  lines: T[],
  products: PricedProduct[],
  from: DraftType,
  to: DraftType,
): T[] {
  const was = priceFieldFor(from);
  const now = priceFieldFor(to);
  if (was === now) return lines;
  const byId = new Map(products.map((p) => [p.id, p]));
  return lines.map((line) => {
    const product = line.productId ? byId.get(line.productId) : undefined;
    return product && line.unitPrice === product[was] ? { ...line, unitPrice: product[now] } : line;
  });
}

/** What a review screen holds when Record is pressed. */
export interface ReviewedDraft {
  type: DraftType;
  /** `yyyy-mm-dd`, as a date field holds it. Blank means "now". */
  date: string;
  partyId: string | null;
  partyName: string | null;
  items: DraftLine[];
  discountType: DiscountType;
  discountValue: number;
  category: string;
  amount: number;
  description: string;
}

/**
 * The body of an accept request: the stored draft with the reviewer's
 * corrections laid over it.
 *
 * `type` and `suggestedType` are both set. The server records by the first
 * and the queue describes the message by the second, and a row that says
 * "read as sale" beside a recorded purchase is a lie.
 *
 * Today is sent as no date at all. The server then stamps the document with
 * the minute it was accepted, and decides for itself what day it is. Any
 * other day is sent as picked.
 */
export function acceptPayload(
  draft: object | null,
  reviewed: ReviewedDraft,
  today: string,
): Record<string, unknown> {
  const base = {
    ...draft,
    type: reviewed.type,
    suggestedType: reviewed.type,
    date: reviewed.date && reviewed.date !== today ? reviewed.date : null,
  };
  if (reviewed.type === "expense") {
    return {
      ...base,
      category: reviewed.category.trim() || "General",
      amount: reviewed.amount,
      description: reviewed.description.trim(),
    };
  }
  // A discount belongs to a sale. On a purchase the parser never sets one, and
  // flipping the direction must not carry it across.
  const discounted = reviewed.type === "sale" && reviewed.discountType !== "none";
  return {
    ...base,
    partyId: reviewed.partyId,
    partyName: reviewed.partyName,
    items: reviewed.items.filter((line) => line.description.trim() && line.quantity > 0),
    discountType: discounted ? reviewed.discountType : "none",
    discountValue: discounted ? reviewed.discountValue : 0,
  };
}
