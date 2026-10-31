---
id: "009"
title: Failed lints are unknown
milestone: M1 Trust
depends_on: ["002"]
---

# 009 Failed lints are unknown

## Goal

A broken lint must not look like a clean plugin. `lint()` ignores the exit status
and the output format: running it with `/bin/false` as `qmllint` returns no
warnings, the same result as a perfect plugin.

## Spec

- [Checks](../SPEC.md#checks)
- [What must never happen](../SPEC.md#what-must-never-happen), rule 1

## Scope

- Treat these as `unknown`, naming the plugin: `qmllint` dies from a signal, it
  exits non-zero with no parseable warnings, or it runs past a timeout.
- Add a timeout. There is none today, so a hung `qmllint` hangs the tool.
- Fix "1 new qmllint warnings".
- Lint with an absolute path to each tree. With a relative `--root`, `--target` or
  `$OMARCHY_PATH`, the `qs` symlink points nowhere, so new warnings never show.

## Done when

- [ ] A failing `qmllint` gives `unknown` and exit 3, with a test.
- [ ] A hanging `qmllint` is stopped, with a test.
- [ ] Warning parsing is tested against captured real output, not a stub.
- [ ] Relative tree paths find the same new warnings as absolute ones, with a test.
- [ ] `tests/run` passes.
