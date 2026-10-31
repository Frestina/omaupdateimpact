---
id: "018"
title: Say why, from the release notes
milestone: M3 Better answers
depends_on: ["002"]
---

# 018 Say why, from the release notes

## Goal

Turn "the update will remove dua-cli" into "...because Disk Usage is replaced by
Disktree (#14426)". A reason changes what a person does about a finding.

## Spec

- [Findings and exit codes](../SPEC.md#findings-and-exit-codes)

## Scope

- Fetch the release notes for the target and cache them with the release.
- Link a finding to a note line when the match is clear, such as a package name, a
  command or a shortcut. The migration's own comments are a second source.
- Show nothing when it's unsure. A wrong reason is worse than none.
- Work offline: with no notes, the finding appears without a reason.

## Done when

- [ ] On v4.5.0-rc2 the `dua-cli` removal shows its reason, with a fixture.
- [ ] A finding with no clear match shows no reason, with a test.
- [ ] Missing notes don't change the exit code, with a test.
- [ ] `tests/run` passes.
