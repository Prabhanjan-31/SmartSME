import * as React from "react";
import { createPortal } from "react-dom";
import { cn } from "@/lib/utils";
import { Icon } from "@/components/Icon";

const MARGIN = 12;
const GAP = 8;

/**
 * A small "i" beside a label that explains the thing it sits next to, for the
 * person seeing it for the first time.
 *
 * It opens on hover and on keyboard focus, and a click or tap pins it open
 * until it is clicked again, Escape is pressed or something else is touched.
 * Touch screens have no hover, so the tap is what makes it usable there.
 *
 * The bubble is drawn at the top of the document, not next to the button.
 * Tables scroll sideways and cards clip their corners, and either would cut
 * a bubble positioned inside them.
 */
export function InfoTip({
  children,
  title,
  label = "More about this",
  className,
}: {
  /** The explanation. Two or three short sentences. */
  children: React.ReactNode;
  /** An optional bold first line. */
  title?: string;
  /** What a screen reader calls the button. */
  label?: string;
  className?: string;
}) {
  const id = React.useId();
  const button = React.useRef<HTMLButtonElement>(null);
  const bubble = React.useRef<HTMLDivElement>(null);
  const [open, setOpen] = React.useState(false);
  // Opened by a click or tap, as opposed to a hover: it stays until dismissed.
  const [pinned, setPinned] = React.useState(false);
  const [place, setPlace] = React.useState<{ top: number; left: number } | null>(null);

  const close = React.useCallback(() => {
    setOpen(false);
    setPinned(false);
  }, []);

  const position = React.useCallback(() => {
    const anchor = button.current?.getBoundingClientRect();
    const size = bubble.current?.getBoundingClientRect();
    if (!anchor || !size) return;
    // Scrolled out of sight: a bubble pointing at nothing is just in the way.
    if (anchor.bottom < 0 || anchor.top > window.innerHeight) {
      close();
      return;
    }
    const centred = anchor.left + anchor.width / 2 - size.width / 2;
    const left = Math.max(MARGIN, Math.min(centred, window.innerWidth - size.width - MARGIN));
    const below = anchor.bottom + GAP;
    const above = anchor.top - GAP - size.height;
    const fitsBelow = below + size.height <= window.innerHeight - MARGIN;
    setPlace({ top: fitsBelow || above < MARGIN ? below : above, left });
  }, [close]);

  // Measured before the browser paints, so the bubble never flashes in the
  // corner first.
  React.useLayoutEffect(() => {
    if (open) position();
    else setPlace(null);
  }, [open, position]);

  React.useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      // Caught on the way down, so a tip inside a dialog closes itself and
      // leaves the dialog open.
      e.stopPropagation();
      close();
    };
    const onPointer = (e: PointerEvent) => {
      const target = e.target as Node;
      if (button.current?.contains(target) || bubble.current?.contains(target)) return;
      close();
    };
    document.addEventListener("keydown", onKey, true);
    document.addEventListener("pointerdown", onPointer, true);
    window.addEventListener("scroll", position, true);
    window.addEventListener("resize", position);
    return () => {
      document.removeEventListener("keydown", onKey, true);
      document.removeEventListener("pointerdown", onPointer, true);
      window.removeEventListener("scroll", position, true);
      window.removeEventListener("resize", position);
    };
  }, [open, close, position]);

  return (
    <span className={cn("inline-flex shrink-0 align-middle print:hidden", className)}>
      <button
        ref={button}
        type="button"
        aria-label={label}
        aria-expanded={open}
        aria-describedby={open ? id : undefined}
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => {
          if (!pinned) setOpen(false);
        }}
        onFocus={() => setOpen(true)}
        onBlur={close}
        onClick={(e) => {
          // The tip may sit inside a row or a link that has a click of its own.
          e.preventDefault();
          e.stopPropagation();
          if (pinned) {
            close();
          } else {
            setPinned(true);
            setOpen(true);
          }
        }}
        className={cn(
          "-m-1 inline-flex h-6 w-6 items-center justify-center rounded-full text-muted-foreground transition-colors hover:text-foreground focus-visible:focus-ring",
          open && "text-foreground",
        )}
      >
        <Icon name="info" size={16} />
      </button>
      {open &&
        createPortal(
          <div
            ref={bubble}
            id={id}
            role="tooltip"
            // Pressing on the bubble would otherwise take focus from the
            // button, and losing focus closes the tip. Only touching
            // something else should dismiss a pinned tip.
            onMouseDown={(e) => e.preventDefault()}
            style={{
              top: place?.top ?? 0,
              left: place?.left ?? 0,
              visibility: place ? "visible" : "hidden",
            }}
            className="fixed z-[70] w-72 max-w-[calc(100vw-1.5rem)] rounded-xl border border-border bg-popover px-3.5 py-3 text-left text-[13px] font-normal leading-relaxed tracking-normal text-popover-foreground shadow-lg"
          >
            {title && <p className="mb-1 font-semibold">{title}</p>}
            {children}
          </div>,
          document.body,
        )}
    </span>
  );
}
