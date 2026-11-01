---
id: "007"
title: Read every package removal
milestone: M1 Trust
depends_on: ["002"]
---

# 007 Read every package removal

## Goal

Find removals however a migration writes them. Only a helper call at the start of
a line counts today. That caught everything in the 91 migrations pending on the
test machine, but older migrations use `sudo pacman -Rns "${targets[@]}"`, so the
gap is real, and it isn't listed in the README's limits.

## Spec

- [Checks](../SPEC.md#checks)

## Scope

Read with `shlex`-style tokens rather than a line regex. A probe showed each of
these wrong today:

- Missed: `x && omarchy-pkg-drop b`, `if x; then omarchy-pkg-drop f; fi`, a list
  continued with `\`, and `pacman -R*`.
- Wrong: `2>/dev/null` adds a package called `2`, and text in a heredoc counts as
  a command.
- `omarchy-pkg-aur-add` should cancel a drop, as `omarchy-pkg-add` does.
- Whether a removal is conditional comes from enclosing `if` or `&&`, not from
  indentation.
- An argument it can't read, such as `"$pkg"` or `"${targets[@]}"`, gives one
  `unknown` finding naming the migration, not silence.

## Not in this ticket

- A full shell parser. Tokens and a small state machine are enough.

## Done when

- [x] Every case above has a test.
- [x] v4.5.0-rc2's pending migrations give the same removals as before, with a
      fixture.
- [x] `tests/run` passes.
