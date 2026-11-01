---
id: "011"
title: CI and the drift watch
milestone: M1 Trust
depends_on: ["010"]
---

# 011 CI and the drift watch

## Goal

Find out from CI, not from a user, when Omarchy changes a format this tool reads.
That is the project's biggest long-term risk.

## Spec

- [Reading release formats](../SPEC.md#reading-release-formats)

## Scope

- GitHub Actions on push and pull request: `tests/run` on the oldest supported
  Python and the newest. Actions pinned to full commit SHAs. `qmllint` is installed
  there, so `RealQmllint` runs and a change in its output fails the build. So are
  `shellcheck` and a pinned `ruff`, so a new ruff can't fail an unchanged commit.
- A scheduled job that fetches the newest release, including RCs, runs the parser
  and fails if it finds an unknown helper, zero bindings or a missing tree
  directory. A failed run notifies the owner.
- The job needs read access only and runs no release code.

## Done when

- [x] CI runs on a pull request and fails on failure. Making it block is in 015,
      since GitHub refuses branch protection on a private free-plan repo.
- [x] The scheduled job has been run by hand once and passes.
- [x] A deliberately unknown helper in a fixture makes the job fail.
