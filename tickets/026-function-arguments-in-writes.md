---
id: "026"
title: Follow function arguments into migration writes
milestone: M3 Better answers
depends_on: ["017"]
---

# 026 Follow function arguments into migration writes

## Goal

Make exit 0 reachable again for someone updating to v4.5.0. The edits check reports
`unknown` for a write it can't place, and most v4.5.0-rc2 machines get one, so the
check runs in part and the exit is 3. Most of those writes go to a function's `"$1"`,
and the function is called with a literal path. Reading the call gives the path, so
the write becomes a note or nothing.

## Spec

- [Reading what migrations write](../SPEC.md#reading-what-migrations-write)
- [What must never happen](../SPEC.md#what-must-never-happen), rule 1

## Scope

- When a migration calls a function it defines, the function's `$1`, `$2` and `"$@"`
  hold what each call passes, read as any other word is. A function called more than
  once holds each call's values, as a variable set in more than one place does.
- A call whose argument is only known when it runs still leaves that write
  `unknown`. So does a function that is never called with literal arguments.
- `${name##pattern}`, `${name#pattern}`, `${name%pattern}` and `${name%%pattern}` are
  read for a value that is known, as v4.5.0-rc2's 1786719479 links to
  `skills/${name##*/}`.
- Record the rules in the spec section above.

## Not in this ticket

- Writes made by release commands, or arguments followed into other release files.
- Running anything to learn a value.

## Done when

- [ ] A write to `"$1"` in a function called with a changed file of yours gives a
      note, and one called with an unchanged default says nothing. With tests.
- [ ] A call with an argument only known when it runs is still `unknown`, with a
      test.
- [ ] `${name##*/}` and its three neighbours are read, with tests.
- [ ] Run over v4.5.0-rc2's and v4.5.0-rc3's migrations, the unknowns left have
      been read, and each is a path that is only known when the migration runs.
- [ ] `tests/run` passes, with `ruff` run, from a scratch venv if it isn't installed.
