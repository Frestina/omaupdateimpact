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
- [Findings and exit codes](../SPEC.md#findings-and-exit-codes)
- [What must never happen](../SPEC.md#what-must-never-happen), rule 1

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
- Keep each computed key's expression. A default whose expression differs between
  the versions is `unknown`, and so is a computed key in the user's bindings. An
  unchanged default stays a note. Today a release can move a computed binding onto
  one of the user's keys and still exit 0.
- Count a computed call once when it is in both versions. On v4.5.0-rc2 the note
  says 12 for 6 calls.
- A `~/.config/hypr/bindings.lua` that exists but can't be read is `unknown`. Today
  a broken symlink reads as having no bindings and exits 0, and a denied file is a
  crash.

## Done when

- [x] On a fixture copied from v4.5.0-rc2, F9 is not reported as removed.
- [x] A clash with `ALT + Alt_R` is found, with a test.
- [x] Press and release on one chord survive parsing, with a test.
- [x] `CONTROL + A` clashes with `CTRL + A`, with a test.
- [x] An unknown `o.bind_foo` helper produces an `unknown` finding, with a test.
- [x] A changed computed key gives `unknown` and exit 3, and an unchanged one can
      still exit 0, with tests.
- [x] A computed key in the user's bindings gives `unknown`, with a test.
- [x] A broken `bindings.lua` symlink gives `unknown`, with a test.
- [x] `tests/run` passes.
