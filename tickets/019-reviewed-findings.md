---
id: "019"
title: Reviewed findings stay quiet
milestone: M3 Better answers
depends_on: ["002"]
---

# 019 Reviewed findings stay quiet

## Goal

Let someone say "I've seen that, it's fine" so a real finding doesn't get lost among
ones they've already accepted. Without this, exit 1 stops meaning anything for a
user who has decided to let a package go.

## Spec

- [Files](../SPEC.md#files)
- [What must never happen](../SPEC.md#what-must-never-happen), rule 3

## Scope

- A stable id for each finding.
- `--ack <id>` records it in `~/.config/omaupdateimpact/reviewed`, a plain text
  file a person can edit. This is the only write to the user's config directory,
  and only on request.
- A reviewed finding moves to a count at the end of the report and no longer
  affects the exit code.
- A review applies to one target release, so a new release asks again.
- `install.sh --uninstall` names that file and leaves it, as it does the cache, so
  it never says nothing is left behind while the file is there.

## Done when

- [ ] A reviewed finding doesn't affect the exit code, with a test.
- [ ] A new release raises it again, with a test.
- [ ] `--ack` with an unknown id fails and writes nothing, with a test.
- [ ] `tests/run` passes.
