---
id: "008"
title: Find every call to a deleted command
milestone: M1 Trust
depends_on: ["002"]
---

# 008 Find every call to a deleted command

## Goal

Look in the places people really call `omarchy-*` commands from, and stop raising
alarms about files that aren't theirs. The README says extensions are scanned, but
`.jsonc` isn't in `TEXT_SUFFIXES`, so `extensions/omarchy-menu.jsonc` is skipped.

## Spec

- [Checks](../SPEC.md#checks)
- [What must never happen](../SPEC.md#what-must-never-happen), rule 1

## Scope

- Scan `.jsonc` files, `~/.config/omarchy/shell.json`, `~/.local/bin`, systemd user
  units, `~/.local/share/applications` and the common shell startup files.
- A file byte-identical to one the installed release ships is Omarchy's own: report
  it as a note. On the test machine, a first-run hook raises a false alarm: it is
  byte-identical to `install/user/first-run/install-voxtype.hook`, and its
  `omarchy-done ensure` guard means it does nothing anyway.
- Name the line number in the evidence.
- Guard the `followlinks=True` walk against symlink loops, and skip very large
  files.
- A user file that can't be read, such as a broken symlink or a denied one, is
  `unknown` and names the file. This covers the single files too, like `.bashrc`,
  which `is_file()` drops today when the link is broken, and a scanned folder that
  is a broken link, which `is_dir()` drops the same way. A binary file is still
  skipped.

## Done when

- [ ] A deleted command in `omarchy-menu.jsonc` is found, with a test.
- [ ] Each new location has a test.
- [ ] An unchanged shipped file gives a note, and an edited copy gives attention,
      with tests.
- [ ] A symlink loop finishes, with a test.
- [ ] A broken symlink and a denied file each give `unknown` and exit 3, with tests.
- [ ] `tests/run` passes.
