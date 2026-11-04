# Changelog

## Unreleased

- "Mark reviewed" in the panel, under each finding that needs attention. It asks
  first, then runs `--ack` with that id, and the count in the bar drops. The panel
  names `~/.config/omaupdateimpact/reviewed`, where deleting a line undoes it.
- "Ask agent" in the panel, under each finding and at the top for the whole report.
  It starts your default coding agent with one prompt, through Omarchy's
  `omarchy-agent-prompt`, and shows only when that is on your `PATH`. The prompt says
  to change nothing unless you ask, and that the finding's text is data, never
  instructions. Omarchy starts the agent with its approval prompts off.
- "Check it" on a newer release shows its report in the panel, not in a terminal.
  "Mark reviewed" and "Ask agent" work on it, and "Open report" opens it in a
  terminal. The icon stays on your own channel. "Back", or closing the panel,
  returns to your own result.
- The panel's findings start closed, so every title shows. Click a title to see
  the rest. The notes are now "Worth knowing", as in the text report.
- A newer release is "Coming next", with "Check it", and says your updates won't
  bring it until it reaches your channel. While it is checked, the panel shows the
  turning icon and "Checking" with its tag. Its report is kept until the shell
  restarts, and its check goes on when the panel closes. Its row then says what
  was found, with "Show" and "Check again".

## 0.2.0 (2026-11-04)

- An Omarchy shell plugin, from this same repository. An icon in the bar shows the
  result: faded when nothing needs attention, a count when something does, and a
  `?` when it couldn't check. Click it for a panel with what needs attention and
  each fix, what couldn't be checked, and the notes. It runs its own command with
  `--json`, and holds no rules. Install it with `omarchy plugin add`.
- When you are up to date and another channel has a newer release, the panel names
  it, and "Check" shows that release's report in a terminal.
- The plugin checks 2 minutes after login, then every 6 hours. "Check every" in the
  panel changes that: only when asked, 1, 6, 12 or 24 hours.
- `--json` prints one document for scripts and the bar plugin: what was
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
- `./install.sh --menu` adds an "Omarchy Impact" row to the Omarchy menu, under
  Update. It opens the report in a terminal. The row is a marked block in
  `~/.config/omarchy/extensions/omarchy-menu.jsonc`, and `--uninstall` removes only
  that block.
- The command leaves its own files out: the checkout it runs from, and a plugin with
  its id. So a clone in the plugins folder, tests included, isn't reported as yours.
- Two runs at once share the cache. The second waits for the first to download,
  then reads the same release, instead of downloading it again and failing. A
  release one run is reading isn't pruned by the other.
- With no update, `--json` says whether each newer release is already in the cache,
  as `cached`.

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
