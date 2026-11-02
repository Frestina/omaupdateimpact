---
id: "025"
title: The install tests don't use the developer's PATH
milestone: M3 Better answers
depends_on: ["013"]
---

# 025 The install tests don't use the developer's PATH

## Goal

Make `tests/run` pass on a developer's machine whatever tools sit on its `PATH`. A
ticket is only done when `tests/run` passes, so a machine where it fails blocks
every ticket.

On the owner's machine, 11 install tests fail. They run `install.sh` with only `PATH`
and a made-up `HOME`. `PATH` is the developer's own, and there `python3` can be a
`mise` shim. Under a made-up `HOME`, `mise` takes its real config for a project's
config and refuses it as untrusted. So `install.sh` can't run `--version`, and stderr
holds `mise` errors. This started when `mise` installed a Python and made a `python3`
shim. CI has no `mise`, so it passes.

## Spec

- [Install](../SPEC.md#install)

## Scope

- The install tests build their own `PATH`: the folder they link into, the folder of
  the Python running the tests (`sys.executable`), and the system folders `install.sh`
  needs. Nothing else from the developer's `PATH`.
- That includes the test that checks the "isn't on your PATH" line, which uses the
  inherited `PATH` today.
- The CI matrix still tests each Python it lists, since the tests run under it.

## Done when

- [x] A `python3` first on the inherited `PATH` that only prints an error doesn't
      change the install tests, with a test that fails without the fix.
- [x] `tests/run` passes on the owner's machine with `mise`'s shims on `PATH`.
- [ ] CI passes on all three jobs.
