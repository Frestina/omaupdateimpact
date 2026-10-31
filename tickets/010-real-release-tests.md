---
id: "010"
title: Tests against real releases
milestone: M1 Trust
depends_on: ["003", "006", "007", "008", "009"]
---

# 010 Tests against real releases

## Goal

Test the whole tool on real Omarchy files. The 27 unit tests all use small strings,
which is how `o.bind_hold` got past them. `main()` and `fetch_release` have no tests
at all.

## Spec

- [How it works](../SPEC.md#how-it-works)
- [Findings and exit codes](../SPEC.md#findings-and-exit-codes)

## Scope

- `tests/fixtures/`: trimmed copies of real release files, MIT-licensed upstream,
  with the source tag noted.
- A fictional home directory with bindings, hooks and a plugin, including clashes.
- End-to-end tests that run the real command and assert on output and exit code,
  for each exit code.
- A download test against a local HTTP server, including a truncated archive.
- `tests/run` also runs `shellcheck` when installed, and `ruff` when installed.

## Done when

- [ ] Every exit code is reached by an end-to-end test.
- [ ] Reverting the fix from 006 makes a fixture test fail.
- [ ] The download path is tested without the internet.
- [ ] Nothing in the fixtures is real personal config.
- [ ] `tests/run` passes.
