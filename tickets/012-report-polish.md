---
id: "012"
title: A report worth reading
milestone: M2 First release
depends_on: ["010"]
---

# 012 A report worth reading

## Goal

Make the answer readable in five seconds. A real run today prints a dozen lines of
notes after the findings, and one change can appear twice.

## Spec

- [What it is](../SPEC.md#what-it-is)

## Scope

- Stop wrapping inside command names: `textwrap` split `omarchy-voxtype-install`
  across two lines. Use `break_on_hyphens=False`.
- Give each attention finding a line with the exact thing to do, such as the
  `hl.unbind` line, or `omarchy pkg add dua-cli` to bring a package back.
- Merge the moved and "now does" lines when they describe one change.
- Collapse notes to a count, with `--all` to show them.
- Colour on a terminal only, and honour `NO_COLOR`.
- Show what was checked, so a clean result shows its work: bindings, migrations
  and plugins compared.

## Not in this ticket

- Findings from release notes: 018.

## Done when

- [ ] No command name is ever split across lines, with a test.
- [ ] Every attention finding has a fix, or a reason it can't have one.
- [ ] A typical report fits on one screen, with `--all` for the rest.
- [ ] Piped output has no colour codes, with a test.
- [ ] `tests/run` passes.
