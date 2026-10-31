---
id: "006"
title: Read every binding helper
milestone: M1 Trust
depends_on: ["002"]
---

# 006 Read every binding helper

## Goal

Stop misreading the release. On v4.5.0-rc2 the tool says F9 "Stop dictation" was
removed. It wasn't: it moved to `o.bind_hold`, which the parser doesn't know, and
`ALT + Alt_R` is never compared at all. One chord can also hold two binds, press
and release, and the dict keeps only the last.

## Spec

- [Reading release formats](../SPEC.md#reading-release-formats)
- [Checks](../SPEC.md#checks)

## Scope

- Read `o.bind_hold(keys, press_description, press, release_description, release)`.
- Keep every bind on a chord, so a press and release pair is one action and not
  an overwrite.
- Apply `hl.unbind` and `o.rebind` found inside the defaults themselves.
- Treat Hyprland's modifier spellings as the same key, such as `CTRL` and
  `CONTROL`, and `SUPER` and `WIN`. Confirm the full list against Hyprland's docs.
- Read `function o.*bind*` from the tree's `helpers.lua`. A helper with no rule
  becomes an `unknown` finding that names it.
- Read commands that are Lua tables as a whole value, such as
  `{ webapp = "https://..." }`, and long strings as literals.

## Done when

- [ ] On a fixture copied from v4.5.0-rc2, F9 is not reported as removed.
- [ ] A clash with `ALT + Alt_R` is found, with a test.
- [ ] Press and release on one chord survive parsing, with a test.
- [ ] `CONTROL + A` clashes with `CTRL + A`, with a test.
- [ ] An unknown `o.bind_foo` helper produces an `unknown` finding, with a test.
- [ ] `tests/run` passes.
