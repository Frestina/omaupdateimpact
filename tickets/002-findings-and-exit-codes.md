---
id: "002"
title: Typed findings and exit codes
milestone: M1 Trust
depends_on: ["001"]
---

# 002 Typed findings and exit codes

## Goal

Replace the three string lists in `Report` with real findings, and make the exit
code mean one thing. Today an uncaught exception exits 1, which reads as "needs
attention", and a partial run can exit 0. Most later tickets build on this.

## Spec

- [Findings and exit codes](../SPEC.md#findings-and-exit-codes)
- [What must never happen](../SPEC.md#what-must-never-happen), rule 1

## Scope

- A `Finding` with check, level (`attention`, `note`, `unknown`), title, detail,
  fix and evidence. Checks return findings instead of writing strings.
- `main()` turns any unexpected exception into one line on stderr and exit 2.
  `--debug` shows the traceback.
- `tarfile.TarError`, `http.client.HTTPException` and bad JSON or an empty list
  from the releases API are download failures, exit 2. `except OSError` misses all
  of them today.
- Exit 3 when nothing needs attention but something is `unknown`, and the closing
  line says which checks didn't run instead of "nothing found".
- Remove `Bind.keys`, which nothing reads, and use a set for `found` in
  `compare_commands`.

## Not in this ticket

- New report layout: 012.
- JSON: 016.

## Done when

- [ ] A truncated or corrupt archive gives one line and exit 2, with a test.
- [ ] A forced exception inside a check gives exit 2, not 1, with a test.
- [ ] With `pacman` missing and nothing else found, the exit is 3 and "nothing
      found" isn't printed, with a test.
- [ ] Exit codes in the README match the spec.
- [ ] `tests/run` passes.
