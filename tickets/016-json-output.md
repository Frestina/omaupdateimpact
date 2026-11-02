---
id: "016"
title: JSON output
milestone: M3 Better answers
depends_on: ["002"]
---

# 016 JSON output

## Goal

Give the plugin, and anyone else, a stable way to read a result.

## Spec

- [JSON](../SPEC.md#json)

## Scope

- `--json` prints one document to stdout, and progress and errors go to stderr.
- Exit codes stay the same.
- Failures that end in exit 2 also print a JSON document with the reason.
- "There is no update" is a document too, with any newer release on another channel.
- Carry what the report works out, so the plugin needs no rules of its own: what was
  checked as data, each check's state (ran, ran in part, didn't run), and every
  finding with its evidence.
- Document the schema in `docs/json.md`.

## Done when

- [ ] Output parses for every exit code, with tests.
- [ ] Nothing but JSON reaches stdout, with a test.
- [ ] The document holds what the text report shows: what was checked, each check's
      state and every finding with its evidence, with a test.
- [ ] The schema doc matches a golden file that a test checks.
- [ ] `tests/run` passes.
