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
- [Choosing the release](../SPEC.md#choosing-the-release)
- [Downloads](../SPEC.md#downloads)

## Scope

- Stop wrapping inside command names: `textwrap` split `omarchy-voxtype-install`
  across two lines. Use `break_on_hyphens=False`, and drop the hyphen rule from
  `flat()` in `tests/test_end_to_end.py`.
- Give each attention finding a line with the exact thing to do, such as the
  `hl.unbind` line, or `omarchy pkg add dua-cli` to bring a package back.
- Merge the moved and "now does" lines when they describe one change.
- Collapse notes to a count, with `--all` to show them.
- Colour on a terminal only, and honour `NO_COLOR`.
- Show what was checked, so a clean result shows its work: bindings, migrations
  and plugins compared.
- Reword the closing line for a check that ran in part. "These checks didn't run:
  bindings." overstates it when only one computed key couldn't be compared.
- When the mirror and the packages disagree, say so instead of "the channel is
  stable / rc, and only stable and rc have tagged releases". Name which is which:
  `omarchy-version-channel` prints `mirror / packages`. It stays exit 2.
- Name the token on a rejected `GITHUB_TOKEN`: a 401 with a token set says the token
  was rejected, rather than `HTTP Error 401`. The token itself is never printed.

## Not in this ticket

- Findings from release notes: 018.

## Done when

- [x] No command name is ever split across lines, with a test.
- [x] Every attention finding has a fix, or a reason it can't have one.
- [x] A typical report fits on one screen, with `--all` for the rest.
- [x] Piped output has no colour codes, with a test.
- [x] The mismatch message names the mirror and the packages, with a test.
- [x] A 401 with a token set names the token and doesn't print it, with a test.
- [x] `tests/run` passes.
