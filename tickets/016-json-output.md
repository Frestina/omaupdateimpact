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
- Document the schema in `docs/json.md`.

## Done when

- [ ] Output parses for every exit code, with tests.
- [ ] Nothing but JSON reaches stdout, with a test.
- [ ] The schema doc matches a golden file that a test checks.
- [ ] `tests/run` passes.
