---
id: "041"
title: A $(...) with no command doesn't stop the run
milestone: M4 Plugin
depends_on: ["040"]
---

# 041 A $(...) with no command doesn't stop the run

## Goal

`x=$(<file)` in a pending migration fails the whole run. It reads a file in bash,
and is common. `substituted()` takes the command's first word, and `$(<file)` and
`$( )` have none, so it raises `IndexError`. The run exits 2 and the bar says it
couldn't check, so it is never shown as clear, but no check's answer is given. 040
found it, by reading every real Omarchy script with the old and new reader: eight
commands in v4.5.0's `bin` have it. The edits check reads only migrations, so no
release has hit it yet. It has been there since 017.

## Spec

- [Reading what migrations write](../SPEC.md#reading-what-migrations-write)

## Scope

- A `$(...)` with no command names no path, as one this can't tell.
- A test that fails without it, and every real script in the cached releases reads
  with no error.

## Done when

- [x] A migration with `x=$(<file)` or `x=$( )` reads, and the run goes on.
- [x] `tests/run` passes.
