---
id: "007"
title: Read every package removal
milestone: M1 Trust
depends_on: ["002"]
---

# 007 Read every package removal

## Goal

Find removals however a migration writes them. Only a helper call at the start of
a line counts today. That caught everything in the 91 migrations pending on the
test machine, but older migrations use `sudo pacman -Rns "${targets[@]}"`, so the
gap is real, and it isn't listed in the README's limits.

## Spec

- [Checks](../SPEC.md#checks)

## Scope

Read with `shlex`-style tokens rather than a line regex. A probe showed each of
these wrong today:

- Missed: `x && omarchy-pkg-drop b`, `if x; then omarchy-pkg-drop f; fi`, a list
  continued with `\`, and `pacman -R*`.
- Wrong: `2>/dev/null` adds a package called `2`, and text in a heredoc counts as
  a command.
- `omarchy-pkg-aur-add` should cancel a drop, as `omarchy-pkg-add` does.
- Whether a removal is conditional comes from enclosing `if` or `&&`, not from
  indentation.
- An argument it can't read, such as `"$pkg"` or `"${targets[@]}"`, gives one
  `unknown` finding naming the migration, not silence.
- Review follow-ups: follow removals through the release files a migration reaches,
  as [Reading migrations](../SPEC.md#reading-migrations) says. `command` only hides
  a command with `-v` or `-V`. A command given by path counts, and so does
  `omarchy pkg drop`. A removal in a string for `bash -c`, `sh -c` or `eval` is
  `unknown`. An apostrophe in `"${x:-it's}"` doesn't swallow what follows, and an
  unclosed backtick is `unknown`. A later conditional drop doesn't soften a certain
  one. The fixture folder carries Omarchy's full license.
- Second review follow-ups: an unknown from a reached file names that file, a
  release script run directly is followed, and `omarchy pkg present` doesn't read
  the `omarchy` dispatcher.

## Not in this ticket

- A full shell parser. Tokens and a small state machine are enough.

## Done when

- [x] Every case above has a test.
- [x] v4.5.0-rc2's pending migrations give the same removals as before, with a
      fixture.
- [x] A removal in a release command a migration calls is "may remove" and names
      both files, with a test.
- [x] A command reached through another command is followed, and a loop of commands
      finishes, with tests.
- [x] A removal in a sourced `$OMARCHY_PATH` script is found, and so is one in a
      sourced migration already run, with tests.
- [x] A reached file that loses the reader, or hides a removal argument, gives
      `unknown` naming the migration, with a test.
- [x] A reached Python file that names a removal gives `unknown`, and one that
      doesn't gives nothing, with tests.
- [x] A real run with `--target` set to v4.5.0-rc2 lists `t3code-bin` as "may
      remove" when it's installed.
- [x] `command omarchy-pkg-drop a` is a removal and `command -v` isn't, with a test.
- [x] `/usr/bin/pacman -Rns a`, `$OMARCHY_PATH/bin/omarchy-pkg-drop a` and
      `omarchy pkg drop a` are removals, with a test.
- [x] `bash -c 'omarchy-pkg-drop a'`, `sudo sh -c 'pacman -Rns a'` and
      `eval "omarchy-pkg-drop a"` give `unknown`, with a test.
- [x] Text between two apostrophes in quoted `${...}` is still read, with a test.
- [x] An unclosed backtick gives `unknown`, with a test.
- [x] A certain drop stays certain after a later conditional one, with a test.
- [x] The README's limits match all this.
- [x] `tests/fixtures/v4.5.0-rc2-migrations/LICENSE` is Omarchy's own, unchanged.
- [x] An unknown from a reached file names that file in its title and evidence, with
      a test.
- [x] `"$OMARCHY_PATH/install/x.sh"` and `sudo "$OMARCHY_PATH/install/x.sh"` are
      followed, and the same path as an argument to `cp` isn't, with tests.
- [x] `omarchy pkg present x` follows `omarchy-pkg-present`, not `bin/omarchy`, with
      a test.
- [x] `tests/run` passes.
