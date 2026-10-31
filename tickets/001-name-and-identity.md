---
id: "001"
title: Name and project identity
milestone: M1 Trust
depends_on: []
---

# 001 Name and project identity

## Goal

Settle the name once, before anyone outside the project sees it, and make the
repository look like that one project.

## Spec

- [What it is](../SPEC.md#what-it-is)

## Scope

- Apply the chosen name to the command, the README, the spec, the tickets, the
  test file and the cache directory.
- Move the existing `~/.local/bin` link to the new name.
- Create the GitHub repository under the Frestina account and push.
- Write the one-line description used for the repository, the README and later
  the marketplace.

## Not in this ticket

- Any behaviour change.

## Done when

- [x] `git grep` finds the old name only where it is meant to stay.
- [x] The command runs from another directory under its new name.
- [x] The remote exists and `main` is pushed.
- [x] `tests/run` passes.
