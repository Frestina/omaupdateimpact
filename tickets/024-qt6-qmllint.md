---
id: "024"
title: Only a Qt 6 qmllint counts
milestone: M2 First release
depends_on: ["009"]
---

# 024 Only a Qt 6 qmllint counts

## Goal

Stop reporting plugins as linted when they weren't. On a real machine with
`qt5-declarative`, `qmllint` on `PATH` is Qt 5's. It prints nothing. Two plugins
came back `unknown`, and two that pass its syntax check counted as "linted", with
nothing compared. With only such plugins the result would read as clear, which
breaks [rule 1](../SPEC.md#what-must-never-happen).

## Spec

- [Linting plugins](../SPEC.md#linting-plugins)
- [What must never happen](../SPEC.md#what-must-never-happen), rule 1

## Scope

- Pick `qmllint` as the spec says: the first of `PATH` and `/usr/lib/qt6/bin/qmllint`
  whose `--version` reads 6 or newer. Qt 5's prints `qmllint 1.0`, and Qt 6.12's
  prints `qmllint 6.12.0`.
- A `--version` that fails, hangs or can't be read doesn't count.
- If neither counts, plugins are `unknown`, and the line names what was found. "Not
  found" stays as it is.
- `REAL_QMLLINT` in the tests picks the same way, so they run on a machine with Qt 5.
- The stubs in the tests and in `tests/demo.py` answer `--version`.
- Check what the older Qt in CI's Ubuntu job prints, rather than assuming.

## Done when

- [x] A Qt 5 `qmllint` first on `PATH` isn't used when the Qt 6 one exists, with a test.
- [x] With only a Qt 5 `qmllint`, plugins are `unknown` and never exit 0, with a test.
- [x] A `--version` that can't be read counts as not Qt 6, with a test.
- [ ] The desktop-style setup gives "4 plugins linted" on a real machine with both.
- [x] `tests/run` passes.
