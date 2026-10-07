import { Field, Input, Select } from "./ui/input";
import {
  PAYMENT_MODES,
  type FieldSpec,
  type PaymentFields,
  type PaymentMode,
  specFor,
} from "@/lib/payments";

/**
 * "How was it paid?" and the fields that go with the answer. Cash asks for
 * nothing; UPI asks for the transaction ID; a card for its last four digits;
 * a cheque for its number, and so on. Changing the mode clears the fields of
 * the old one, so a cheque number never rides along on a UPI payment.
 */
export function PaymentModeFields({
  value,
  onChange,
  problem,
}: {
  value: PaymentFields;
  onChange: (next: PaymentFields) => void;
  /** Shown under the fields once the person has typed something. */
  problem?: string | null;
}) {
  const spec = specFor(value.mode);

  function setMode(mode: PaymentMode) {
    onChange({ mode, reference: "", details: {} });
  }
  function setDetail(key: string, v: string) {
    onChange({ ...value, details: { ...value.details, [key]: v } });
  }

  function renderDetail(f: FieldSpec) {
    const v = value.details[f.key] ?? "";
    if (f.type === "select") {
      return (
        <Field key={f.key} label={f.label}>
          <Select value={v} onChange={(e) => setDetail(f.key, e.target.value)}>
            {(f.options ?? []).map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </Select>
        </Field>
      );
    }
    return (
      <Field key={f.key} label={f.label} hint={f.hint}>
        <Input
          type={f.type === "date" ? "date" : "text"}
          value={v}
          onChange={(e) => setDetail(f.key, e.target.value)}
          placeholder={f.placeholder}
          maxLength={f.maxLength ?? 64}
        />
      </Field>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      <Field label="Paid by">
        <Select value={value.mode} onChange={(e) => setMode(e.target.value as PaymentMode)}>
          {PAYMENT_MODES.map((m) => (
            <option key={m.key} value={m.key}>
              {m.label}
            </option>
          ))}
        </Select>
      </Field>
      {spec.reference && (
        <Field label={spec.reference.label} hint={spec.reference.hint}>
          <Input
            value={value.reference}
            onChange={(e) => onChange({ ...value, reference: e.target.value })}
            placeholder={spec.reference.placeholder}
            inputMode={spec.reference.inputMode}
            maxLength={spec.reference.maxLength ?? 64}
            autoComplete="off"
          />
        </Field>
      )}
      {spec.details.length > 0 && (
        <div className="grid gap-3 sm:grid-cols-2">{spec.details.map(renderDetail)}</div>
      )}
      {problem && (value.reference || Object.keys(value.details).length > 0) && (
        <p className="text-xs text-warning">{problem}</p>
      )}
    </div>
  );
}
