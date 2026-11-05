---
id: "038"
title: The bar's mark is the icon's label
milestone: M4 Plugin
depends_on: ["037"]
---

# 038 The bar's mark is the icon's label

## Goal

Keep the bar icon the same size as every other icon in Omarchy 4.5.0. Its bar fits
all of a `BarIconButton`'s `text` into one icon's box. The widget put the mark (the
count, `?` or `…`) in that text, so the glyph and the mark were scaled down
together, and the icon looked smaller than the rest. The owner saw the same bug in
fleetlog and cronward-omarchy, which are already fixed the same way.

## Spec

- [What the bar shows](../SPEC.md#what-the-bar-shows)

## Scope

- On a horizontal bar, the mark goes in the button's `labelText`, as the battery's
  percentage does. It shows to the left of the glyph, at the bar's own size.
- A shell from before 4.5.0 has no `labelText`. Assigning it there fails the whole
  icon, so it is set only where the button has it (`"labelText" in button`). On
  such a shell, the mark stays in `text`, which that shell draws at its own size.
- The slot widens with the mark's length, as fleetlog's does.
- A vertical bar is unchanged: the glyph alone, and the mark as a badge under it.
- The spec says where the mark goes, and why.

## Not in this ticket

- Seeing it on a 4.0.6 shell. The lint covers the QML; the installed plugin only
  gets the fix once `main` is pushed, after the listing is decided.

## Done when

- [x] On a horizontal bar, the mark is the button's `labelText` from 4.5.0, and
      stays in `text` where the button has no `labelText`.
- [x] A test fails without the fix: `test_the_mark_is_the_icons_label_so_the_glyph_keeps_its_size`.
- [x] `tests/lint-plugin` passes against v4.5.0. v4.0.6 isn't in the local cache,
      so CI's lint covers it when `main` is pushed.
- [x] The spec's "What the bar shows" says where the mark goes.
- [x] `tests/run` passes.
