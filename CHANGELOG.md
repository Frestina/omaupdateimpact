# Changelog

## Unreleased

- `--json` prints one document for scripts and the coming bar plugin: what was
  checked, each check's state, and every finding with its evidence. Every exit code
  has one. See [docs/json.md](docs/json.md).
- A new check reads the migrations you haven't run for files of yours they look like
  they edit or remove. A file that is still Omarchy's default says nothing. The rest
  are notes, and a path it can't place is a limit. A function's arguments are
  followed from its calls, and `${name##*/}` and its like are read.
- A finding says why, from the release notes, when one change there clearly names
  its package, command or keys, or the change its migration describes. The notes are
  kept with the release in the cache. Without them findings give no reason, and
  nothing else changes.
- Each finding that needs attention has an id. `--ack <id>` marks one you've seen
  and accepted, for that release only. It no longer counts for the exit code, and the
  report counts it at the end. Reviews are kept in
  `~/.config/omaupdateimpact/reviewed`, a file you can edit. `install.sh
  --uninstall` names it and leaves it.

## 0.1.0 (2026-11-02)

The first release.

- Compares your setup with an Omarchy release before you update, and changes
  nothing. Nothing from the release is run.
- Follows your update channel, or takes `--channel` or a tag. It says so when you
  already have the release.
- Reads your bindings against the release's defaults, including `o.bind_hold`. It
  flags clashes and shortcuts you turned off that come back.
- Reads the migrations you haven't run, and the release files they reach, for
  installed packages they remove.
- Finds deleted `omarchy-*` commands still called from your files, and names the
  line.
- Reports new `qmllint` warnings in your plugins, as notes.
- A report that fits a screen, with a `Fix:` line for what needs attention. `--all`
  shows the notes.
- Exit codes tell a clean result from one where a check couldn't run in full.
- `install.sh` links the command into `~/.local/bin`, and `--uninstall` removes it.
