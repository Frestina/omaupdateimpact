---
id: "034"
title: Undo a review, short notes, and ask what replaces it
milestone: M4 Plugin
depends_on: ["033"]
---

# 034 Undo a review, short notes, and ask what replaces it

## Goal

Changes the owner asked for after using the panel, each needing the command as
well as the plugin:

- Marking a finding reviewed takes one click, and a Reviewed section at the bottom
  undoes it.
- A note that lists many things, such as the new default shortcuts, shows them one
  per line, not as one paragraph.
- Every note reads as one short line, and says what kind it is, so the panel can
  group them (035). The owner found 27 notes of whole sentences hard to read.
- "Ask agent" finds out what replaces a removed package, command or shortcut, and
  what the user would keep or lose. Asking about Tensaku and Omasnap showed the need.

## Spec

- [Reviewed findings](../SPEC.md#reviewed-findings): `--unack`
- [JSON](../SPEC.md#json): `target.path`, `items`, `group` and short note titles
- [Plugin](../SPEC.md#plugin): The panel
- [What must never happen](../SPEC.md#what-must-never-happen), rule 3
- [Files](../SPEC.md#files)

The spec already records each decision below.

## Scope

- **`--unack <id>`** in the command, as the spec's Reviewed findings says. It removes
  that release's lines for the id, and leaves every other byte as it was. It writes
  the file whole and moves it into place, so a link stays a link. Exit 2, with
  nothing written, when there is no such line or no update. `--ack` with `--unack`
  is bad usage. Tests for each, and for a file kept as a link.
- **No confirmation on "Mark reviewed".** It runs `--ack` at once. The Reviewed
  section lists each reviewed finding, closed as the others are, with "Undo", which
  runs `--json --unack <id>` with the release the panel shows. A failed one keeps
  the last result and shows its reason, as a failed `--ack` does.
- **`items`.** "New default shortcuts" and "Default shortcuts removed" put each
  shortcut in `items`, as `SUPER + M: Minimize window to the dock`, and their titles
  say how many: "18 new default shortcuts." Other findings with a long list in their
  title can follow, if one reads the same way. The text report prints the items one
  per line under the title. The panel shows them one per line when the finding is
  open. `docs/json.md` and the golden files change with it. It is an addition, so
  `schemaVersion` stays 1.
- **Short note titles and `group`**, as the spec's JSON section says. Every note
  gets a `group` heading for its kind, named by the command. A note's title becomes
  one short line, and the rest moves to its detail: a move is
  `Calculator: SUPER + CTRL + Q -> SUPER + SHIFT + Q`, and a changed default is
  `SUPER + ALT + SPACE: "Apps menu" -> "Apps"`. Go through every note the command
  makes, in each check, and give each a group and a short title. `--all` prints the
  notes under their group headings. The README's report and `docs/demo.svg` change
  with it, through `python3 -m tests.demo`.
- **`target.path`**: the unpacked release the command read, in every document that
  compares.
- **The prompt's new step**, after "explain first": when a finding is about something
  the release removes, replaces or renames, find out what takes its place and what it
  does, and say what the user would keep, gain or lose. Read the unpacked release at
  `target.path` and its notes, and install nothing. The test of the prompt's order
  covers it.
- README and CHANGELOG, under Unreleased.

## Done when

- [x] `--unack` removes only that release's lines for the id, byte for byte, keeps a
      link a link, and is exit 2 with nothing written otherwise. Tested.
- [x] "Mark reviewed" runs at once, and "Undo" under Reviewed takes it back. Tested
      with fixture JSON.
- [x] Both shortcut notes have `items` and a short title, in `--json`, the text
      report and the panel. The golden files and `docs/json.md` match.
- [x] Every note has a `group` and a one-line title, with the rest in its detail,
      in `--json` and under `--all`. Tested for each kind of note.
- [x] `target.path` is in the document, and the prompt names it in its new step.
      Tested.
- [x] The plugin still passes `omarchy plugin validate` and CI's QML lint.
- [x] `tests/run` passes.
