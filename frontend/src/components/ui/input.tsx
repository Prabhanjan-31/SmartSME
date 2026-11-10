import * as React from "react";
import { cn } from "@/lib/utils";
import { InfoTip } from "./info-tip";

const base =
  "w-full rounded-xl border border-input bg-card px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground shadow-sm transition-[border-color,box-shadow,background-color] focus:border-primary/60 focus-visible:focus-ring disabled:opacity-50";

export const Input = React.forwardRef<
  HTMLInputElement,
  React.InputHTMLAttributes<HTMLInputElement>
>(({ className, ...props }, ref) => (
  <input ref={ref} className={cn(base, "h-10", className)} {...props} />
));
Input.displayName = "Input";

export const Textarea = React.forwardRef<
  HTMLTextAreaElement,
  React.TextareaHTMLAttributes<HTMLTextAreaElement>
>(({ className, ...props }, ref) => (
  <textarea ref={ref} className={cn(base, "min-h-20", className)} {...props} />
));
Textarea.displayName = "Textarea";

export const Select = React.forwardRef<
  HTMLSelectElement,
  React.SelectHTMLAttributes<HTMLSelectElement>
>(({ className, ...props }, ref) => (
  <select ref={ref} className={cn(base, "h-10", className)} {...props} />
));
Select.displayName = "Select";

export function Label({ className, ...props }: React.LabelHTMLAttributes<HTMLLabelElement>) {
  return <label className={cn("text-sm font-medium text-foreground/90", className)} {...props} />;
}

export function Field({
  label,
  hint,
  info,
  children,
  className,
}: {
  label?: string;
  /** One line under the field: what to type. */
  hint?: string;
  /** A longer explanation behind an "i" beside the label: what it is for. */
  info?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-col gap-1.5", className)}>
      {/* The tip sits beside the label, not inside it: a button inside a
          <label> is what a click on the label's text would press. */}
      {label && info ? (
        <div className="flex items-center gap-1.5">
          <Label>{label}</Label>
          <InfoTip label={`About ${label}`}>{info}</InfoTip>
        </div>
      ) : (
        label && <Label>{label}</Label>
      )}
      {children}
      {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
    </div>
  );
}
