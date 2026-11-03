---
id: "028"
title: The command leaves its own files out
milestone: M4 Plugin
depends_on: ["021"]
---

# 028 The command leaves its own files out

## Goal

Installing the plugin doesn't make the command report on itself.

Found in the review of 021. The plugin is the whole repository, cloned into
`~/.config/omarchy/plugins/<id>/`, and the command reads that folder. With this repo
cloned there in a fictional home, v4.0.6 against v4.5.0-rc2 gave 10 commands
`attention` findings and 3 notes, all from `tests/`. So the bar would flag the plugin
itself.

## Spec

- [Reading your files](../SPEC.md#reading-your-files)
- [Linting plugins](../SPEC.md#linting-plugins)
- [Plugin](../SPEC.md#plugin)

## Scope

- The checkout the running command is in, by real path, is left out of the
  commands and plugins checks, and of the "Checked" counts.
- So is a plugin folder whose `manifest.json` has this tool's id, wherever it is
  linked from.
- A folder that holds your home is never left out.
- Note which constant holds the id, so 022's manifest and the command can't drift.
- Review follow-ups: the folder above `bin/` is the tool's own only when it is
  recognisably this tool, so a copy in `~/.local/bin` or a package in `/usr/bin`
  leaves none of your files out.

## Not in this ticket

- The manifest and QML. They are 022. A test can use a fictional `manifest.json`
  with the id.

## Done when

- [x] A clone of this repository in a fictional home's plugins folder adds no
      findings, and a test fails without the change.
- [x] A second clone, with this tool's id but not the running checkout, adds none
      either.
- [x] A plugin that isn't this tool, beside it, is still read and linted.
- [x] Running from a checkout that holds the fictional home leaves nothing out.
- [x] `tests/run` passes.
- [x] A copy of the command in a fictional `~/.local/bin` still reads the other
      files in `~/.local/bin` and `~/.local/share/applications`, and a test fails
      without the change.
- [x] A command in a fictional `/usr/bin` still reads a file of yours linked to
      `/usr/local/bin`.
- [x] The spec says what makes the folder above `bin/` the tool's own.
