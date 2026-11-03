---
id: "017"
title: Migrations that touch files you changed
milestone: M3 Better answers
depends_on: ["002"]
---

# 017 Migrations that touch files you changed

## Goal

Close the biggest gap in coverage: a migration that rewrites a config file you
customized isn't reported today. omaforecast finds these by running migrations.
This finds likely ones by reading them, and says that's what it's doing.

## Spec

- [Where it stops](../SPEC.md#where-it-stops)
- [What must never happen](../SPEC.md#what-must-never-happen), rule 2

## Scope

- Read paths under `~/.config` and `$HOME` from pending migrations, along with
  writers such as `sed -i`, `cp`, `mv`, `rm` and `>`.
- Compare each with Omarchy's default of that file, where there is one, to tell
  whether you changed it.
- A match is a note saying the migration "looks like it edits" the file, with the
  line. It can't say what the result will be, and suggests omaforecast if the user
  wants that.
- Review follow-ups: read writes behind a wrapper function, as the packages check
  does, and `ln -f` and `find -delete`, and name what is still not read. Round 2:
  a writer counts only behind a command that runs its arguments, not behind any
  command, and `find -exec` only when what it runs writes.

## Not in this ticket

- Running anything, or predicting file contents.

## Done when

- [x] A migration with `sed -i` on a customized file gives a note, with a test.
- [x] The same migration on an unchanged file says nothing, with a test.
- [x] Paths built from variables are reported as unknown, not skipped.
- [x] Run over v4.5.0-rc2's migrations, the output has been read for false alarms.
- [x] A write behind a wrapper function, such as `as_root rm`, is read. A function
      that runs `sudo "$@"` counts as `sudo`. With a test.
- [x] `ln -f` onto a file of yours gives a note, and `find -delete` or `-exec` in
      your files is `unknown`. With tests.
- [x] The spec and the README's limits name the writers that still aren't read, and
      the README doesn't say "and the like".
- [x] `mise install node` and `notify-send "cp" "$HOME/.bashrc"` give nothing, and
      `retry 3 rm` behind a function of the migration's own still gives a note.
      With tests.
- [x] `find -exec grep` in your files gives nothing, and `find -exec rm` is
      `unknown`. With a test.
- [x] `tests/run` passes.
