import { Badge } from "@/components/ui/badge";

/**
 * Paid / Partial / Unpaid, or "Overdue" once an unpaid amount is past its
 * deadline. Overdue wins because it is the one that needs doing something
 * about; the amount still owed is beside it in the table.
 */
export function PaymentBadge({ status, overdue = false }: { status: string; overdue?: boolean }) {
  const map: Record<string, { tone: "success" | "warning" | "destructive"; label: string }> = {
    paid: { tone: "success", label: "Paid" },
    partial: { tone: "warning", label: "Partial" },
    unpaid: { tone: "destructive", label: "Unpaid" },
  };
  if (overdue && status !== "paid") return <Badge tone="destructive">Overdue</Badge>;
  const m = map[status] ?? { tone: "warning" as const, label: status };
  return <Badge tone={m.tone}>{m.label}</Badge>;
}

export function EventStatusBadge({ status }: { status: string }) {
  const map: Record<
    string,
    { tone: "info" | "warning" | "success" | "destructive" | "outline"; label: string }
  > = {
    pending: { tone: "outline", label: "Pending" },
    processing: { tone: "info", label: "Processing" },
    done: { tone: "success", label: "Done" },
    failed: { tone: "warning", label: "Failed" },
    dead: { tone: "destructive", label: "Dead-letter" },
  };
  const m = map[status] ?? { tone: "outline" as const, label: status };
  return <Badge tone={m.tone}>{m.label}</Badge>;
}

// Where a document came from. The three AI paths are kept apart on purpose:
// "an order was parsed" is much less useful after the fact than "an order
// arrived by email", which is what someone asks when a figure looks wrong.
export function SourceBadge({ source }: { source: string }) {
  const map: Record<string, { tone: "default" | "primary" | "info" | "success"; label: string }> = {
    form: { tone: "default", label: "Form" },
    nlp: { tone: "primary", label: "AI · Text" },
    ocr: { tone: "info", label: "AI · Photo" },
    email: { tone: "success", label: "Email" },
    telegram: { tone: "success", label: "Telegram" },
  };
  const m = map[source] ?? { tone: "default" as const, label: source };
  return <Badge tone={m.tone}>{m.label}</Badge>;
}
