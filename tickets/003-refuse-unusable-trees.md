---
id: "003"
title: Refuse unusable trees
milestone: M1 Trust
depends_on: ["002"]
---

# 003 Refuse unusable trees

## Goal

Fix the worst bug in the tool: `--root /nonexistent --target /nonexistent` exits 0
and reports nothing to worry about, because every comparison had nothing to read.
A machine linked to a dev checkout gets the same kind of wrong answer, since the
installed tree is hardcoded.

## Spec

- [The two trees](../SPEC.md#the-two-trees)
- [What must never happen](../SPEC.md#what-must-never-happen), rule 1

## Scope

- Check that both trees hold `bin`, `default/hypr`, `migrations` and `shell`.
  Otherwise one line naming what's missing, and exit 2.
- Default the installed tree to `$OMARCHY_PATH`, then `/usr/share/omarchy`.
- Get the installed version from `omarchy-version`, which also handles
  `omarchy-dev`. Today the edge channel reports "unknown".
- Parsing zero default bindings from a tree is exit 2: the format has moved.

## Done when

- [ ] Missing and empty trees exit 2 for both `--root` and `--target`, with tests.
- [ ] `OMARCHY_PATH` is used when set, with a test.
- [ ] A tree with no readable bindings exits 2, with a test.
- [ ] `tests/run` passes.
