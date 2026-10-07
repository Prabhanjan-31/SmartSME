import { useState } from "react";
import { Modal } from "./ui/modal";
import { Button } from "./ui/button";
import { Field, Input } from "./ui/input";
import { PaymentModeFields } from "./PaymentModeFields";
import { useMutation } from "@/lib/api";
import { emptyPayment, paymentProblem, toPayload, type PaymentPayload } from "@/lib/payments";
import { money, toDateInputValue } from "@/lib/utils";

export function RecordPaymentButton({
  onSubmit,
  due,
  currency,
  label = "Record payment",
  variant = "outline",
  onDone,
}: {
  /** The request body: amount, the day it was paid, and how. */
  onSubmit: (payment: PaymentPayload) => Promise<unknown>;
  due: number;
  currency: string;
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

  function openDialog() {
    setAmount(due);
    setDate(toDateInputValue());
    setHow(emptyPayment());
    setOpen(true);
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (problem) return;
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
          <Field label="Paid on" hint="Defaults to today. Back-date it if the money came earlier.">
            <Input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
          </Field>
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
            <Button type="submit" disabled={pending || !date || problem !== null}>
              {pending ? "Saving…" : "Save payment"}
            </Button>
          </div>
        </form>
      </Modal>
    </>
  );
}
