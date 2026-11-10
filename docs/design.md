# Design system

Colour, type, spacing and the component vocabulary.

[&larr; Back to the README](../README.md)

---

## Design system

Tailwind v4 with CSS custom properties in `frontend/src/index.css`. Light is the
default; a `.dark` class on `<html>` flips the tokens, set before paint by an
inline script to avoid a flash. No component library: `src/components/ui/*` holds
small primitives (Button, Card, Table, Modal, Input, Badge) and
`src/components/Icon.tsx` is a dependency-free stroke icon set.

**Colour.** A muted teal brand on warm-sand neutrals in light mode, and a
desaturated teal on soft charcoal in dark - calm enough to sit in front of all
day. Nothing fluorescent, and no coloured glows: the primary button carries an
ordinary elevation shadow, cards have plain surfaces, and table rows highlight
with a neutral wash rather than a tint of the brand.

The teal is readable as text (about 5.6:1 on white), so `--link` and `--primary`
can be the same colour, which the previous neon palette could not manage. Status
colours are muted to match: a warning should read as a warning, not as an
alarm.

The chart tokens are a separate palette, validated for the OKLCH lightness band,
a chroma floor, adjacent-pair separation under colour-vision deficiency, and
contrast against the chart surface. `--chart-1` is a *more saturated* teal than
the UI brand for a reason: at the brand's chroma a thin chart line falls below
the floor and reads as grey. A calm UI colour and a legible data colour are not
the same requirement.

The sign-in and sign-up pages share `src/components/AuthLayout.tsx`: a lime brand
panel beside the form. The panel keeps its colour in both themes, because it *is* the
brand, while the form panel follows the app surface, and below `lg` it collapses
to a banner above the form rather than disappearing.

The sidebar is resizable by dragging the handle on its edge and collapses to an
icon-only rail when that handle is clicked; both the width and collapsed state
persist.

Data loading uses two small hooks in `src/lib/api.ts` (`useApi` for reads,
`useMutation` for writes) rather than a data-fetching library, since the app is almost
entirely "load a page, mutate, reload".

The one thing that pattern misses is a number shown outside the page that
changed it: the unread count on the bell and the Inbox count in the sidebar
live in the app shell, and a page reloading itself does not reload them. So
`request()` announces every write that succeeds, `onDataChanged(listener)`
subscribes to that, and `AppShell` refetches its two counts when it hears one.
Signing in and out are left out of it: they change who is asking, not what the
counts are, and a refetch racing the sign-out would be answered 401.

**Info tips.** `src/components/ui/info-tip.tsx` is the small **i** beside a
label that explains it to someone seeing it for the first time. Every
explanation of that kind goes through this one component, so that help always
looks and behaves the same:

- It opens on hover and on keyboard focus, and a click or tap pins it open
  until it is clicked again, Escape is pressed or something else is touched.
  Touch screens have no hover, so the tap is what makes it usable there.
- The bubble is drawn at the top of the document (a portal to `<body>`,
  `position: fixed`), not beside the button. Tables scroll sideways and cards
  clip their corners, and either would cut it off. It sits below the button,
  flips above when there is no room, stays 12px inside the window, follows
  scrolling, and closes when its button scrolls out of view.
- Inside a dialog, Escape closes the tip and leaves the dialog open.
- It is a real `<button>` with an `aria-label` ("About Payment deadline
  (days)"), and the bubble is a `role="tooltip"` linked by `aria-describedby`,
  so a screen reader announces the explanation when the button takes focus.
- It is hidden when printing.

Use it through the `info` prop on `Field`, `PageHeader` and `SectionCard`
rather than placing it by hand, and keep the text to two or three sentences
about what the thing is and what changing it does. A `hint` under a field is
for what to type; `info` is for what the field means. Where each tip lives is
listed in the [feature reference](features.md#info-tips).

---

