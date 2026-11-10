import { Icon } from "./Icon";
import type { DiscountType, DocumentTotals } from "@/lib/draft";
import { money } from "@/lib/utils";

/** Subtotal, discount, tax and total, as every screen that prices a document
 *  shows them. One component, so a sale reads the same wherever it is drawn. */
export function TotalsSummary({
  totals,
  taxRate,
  currency,
  discountType = "none",
  discountValue = 0,
  overDiscountHint = "Discount is more than the subtotal, lower it before publishing.",
  onRemoveDiscount,
}: {
  totals: DocumentTotals;
  taxRate: number;
  currency: string;
  discountType?: DiscountType;
  discountValue?: number;
  overDiscountHint?: string;
  /** Where the discount cannot be edited, it can at least be taken off. */
  onRemoveDiscount?: () => void;
}) {
  return (
    <div className="space-y-1 rounded-lg bg-muted/50 p-3 text-sm">
      <div className="flex justify-between">
        <span className="text-muted-foreground">Subtotal</span>
        <span className="tabular-nums">{money(totals.subtotal, currency)}</span>
      </div>
      {totals.discountAmount > 0 && (
        <div className="flex justify-between text-success">
          <span>
            Discount{discountType === "percentage" ? ` (${discountValue}%)` : ""}
            {onRemoveDiscount && (
              <button
                type="button"
                onClick={onRemoveDiscount}
                className="ml-2 text-xs text-muted-foreground underline underline-offset-2 hover:text-foreground"
              >
                Remove
              </button>
            )}
          </span>
          <span className="tabular-nums">- {money(totals.discountAmount, currency)}</span>
        </div>
      )}
      <div className="flex justify-between">
        <span className="text-muted-foreground">Tax ({taxRate}%)</span>
        <span className="tabular-nums">{money(totals.tax, currency)}</span>
      </div>
      <div className="flex justify-between border-t border-border pt-1 font-semibold">
        <span>Total</span>
        <span className="tabular-nums">{money(totals.total, currency)}</span>
      </div>
      {totals.overDiscount && (
        <p className="flex items-center gap-1 pt-1 text-xs text-destructive">
          <Icon name="alert" size={13} />
          {overDiscountHint}
        </p>
      )}
    </div>
  );
}
