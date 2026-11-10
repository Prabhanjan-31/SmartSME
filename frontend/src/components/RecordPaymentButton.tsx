import { useState } from "react";
import { Modal } from "./ui/modal";
import { Button } from "./ui/button";
import { Field, Input } from "./ui/input";
import { PaymentModeFields } from "./PaymentModeFields";
import { useMutation } from "@/lib/api";
import {
  emptyPayment,
  paymentDateWindow,
  paymentProblem,
  toPayload,
  type PaymentPayload,
} from "@/lib/payments";
import { formatDate, money, toDateInputValue } from "@/lib/utils";

export function RecordPaymentButton({
  onSubmit,
  due,
  currency,
  documentDate,
  noun,
  label = "Record payment",
  variant = "outline",
  onDone,
}: {
  /** The request body: amount, the day it was paid, and how. */
  onSubmit: (payment: PaymentPayload) => Promise<unknown>;
  due: number;
  currency: string;
  /** The sale's or purchase's own date, as the API sent it. A payment can be
   *  dated from that day up to today, and the picker is limited to match. */
  documentDate: string;
  /** What is being paid, for the wording: "before the sale itself". */
  noun: "sale" | "purchase";
  label?: string;
  variant?: "outline" | "primary" | "ghost";
  onDone?: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [amount, setAmount] = useState<number>(due);
  const [date, setDate] = useState(toDateInputValue());
  const [how, setHow] = useState(emptyPayment());
  const { run, pending, error } = useMutation();
  const problem = paymentProblem(how);
  const when = paymentDateWindow(date, documentDate, noun);
  // A sale or purchase dated ahead of today (an order booked for next week)
  // has no day it can be paid on yet; the message under the field says so.
  const notYet = when.earliest > when.latest;
  const dateHint = notYet
    ? undefined
    : when.earliest === when.latest
      ? `This ${noun} is dated today, so the payment is too.`
      : `Defaults to today. Back-date it if the money came earlier, as far back as ${formatDate(documentDate)}, the day of the ${noun}.`;

  function openDialog() {
    setAmount(due);
    setDate(toDateInputValue());
    setHow(emptyPayment());
    setOpen(true);
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (problem || when.problem) return;
    await run(
      () => onSubmit(toPayload(how, amount, date)),
      () => {
        setOpen(false);
        onDone?.();
      },
    );
  }

  return (
    <>
      <Button variant={variant} size="sm" onClick={openDialog}>
        {label}
      </Button>
      <Modal open={open} onClose={() => setOpen(false)} title="Record payment" className="max-w-md">
        <form onSubmit={submit} className="flex flex-col gap-4">
          <p className="text-sm text-muted-foreground">
            Outstanding: <span className="font-medium text-foreground">{money(due, currency)}</span>
          </p>
          <Field label="Amount">
            <Input
              type="number"
              min={0}
              step="0.01"
              value={amount || ""}
              onChange={(e) => setAmount(Number(e.target.value) || 0)}
              autoFocus
            />
          </Field>
          <Field label="Paid on" hint={dateHint}>
            <Input
              type="date"
              value={date}
              min={notYet ? undefined : when.earliest}
              max={when.latest}
              disabled={notYet}
              onChange={(e) => setDate(e.target.value)}
              aria-invalid={when.problem !== null}
            />
          </Field>
          {when.problem && <p className="text-sm text-destructive">{when.problem}</p>}
          <PaymentModeFields value={how} onChange={setHow} problem={problem} />
          {error && <p className="text-sm text-destructive">{error}</p>}
          <div className="flex justify-end gap-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => setOpen(false)}
              disabled={pending}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={pending || problem !== null || when.problem !== null}>
              {pending ? "Saving…" : "Save payment"}
            </Button>
          </div>
        </form>
      </Modal>
    </>
  );
}
