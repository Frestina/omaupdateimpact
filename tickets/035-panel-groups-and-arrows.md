---
id: "035"
title: Notes in groups, and arrows that show
milestone: M4 Plugin
depends_on: ["034"]
---

# 035 Notes in groups, and arrows that show

## Goal

Make Worth knowing quick to scan, and make it plain that a title opens.

The owner asked for both after 033. The arrow on the left of each title, in a muted
colour, was easy to miss. And 27 notes of different kinds in one list were hard to
read, even closed.

## Spec

- [Plugin](../SPEC.md#plugin): The panel
- [JSON](../SPEC.md#json): `group`, from 034

The spec already records each decision below.

## Scope

- **The arrow.** On the right of every row that opens: a finding, a group, and the
  Worth knowing section. It's in the text colour, a size larger than now, and it
  turns when the row opens.
- **The whole row opens.** A click anywhere on the title row opens it, and the row
  lights up under the pointer, with the theme's own hover colour.
- **Groups.** Worth knowing lists each `group` with its count, closed, in the order
  the document gives them. Opening a group lists its notes, each one line, which
  opens to its detail, evidence and buttons. A note without a `group` goes under
  "Other", last, so nothing is hidden if the command adds a kind and forgets one.
- Needs attention and Couldn't check stay as they are: never collapsed, every title
  showing, each finding opening on its row.
- README and CHANGELOG, under Unreleased.

## Done when

- [ ] Every row that opens has its arrow on the right, in the text colour, turning
      when it opens, and opens on a click anywhere on it.
- [ ] Worth knowing groups notes by `group`, in the document's order, with counts,
      and a note without one goes under "Other". Tested with fixture JSON.
- [ ] Needs attention and Couldn't check still show every title. Tested.
- [ ] The plugin still passes `omarchy plugin validate` and CI's QML lint.
- [ ] `tests/run` passes.
