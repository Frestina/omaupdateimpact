---
id: "020"
title: An entry in the Omarchy menu
milestone: M3 Better answers
depends_on: ["015"]
---

# 020 An entry in the Omarchy menu

## Goal

Put the check next to the update itself, for people who start updates from the menu
and would never type a command. Omarchy has no pre-update hook, so this is the
closest place to reach them.

## Spec

- [Product shape](../SPEC.md#product-shape)
- [What must never happen](../SPEC.md#what-must-never-happen), rule 3

## Scope

- An optional step in `install.sh` that adds a row to
  `~/.config/omarchy/extensions/omarchy-menu.jsonc` in a marked block.
- The row opens the report in a terminal.
- `install.sh --uninstall` removes exactly that block.
- Follow Omarchy's menu extension format; confirm it against the installed docs.

## Done when

- [x] The row appears in the menu and opens the report.
- [x] The file's other contents are untouched, including after uninstall.
- [x] Running the step twice adds one row.
- [x] `tests/run` passes.
