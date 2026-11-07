# Changelog

## Unreleased

- Every file read from a release now costs little more than its size, not only the
  migrations. The bindings reader scanned to the end of a Lua file for each call
  that never closed, so `hl.bind(` repeated in a crafted 64 KB file took over a
  minute, and in 256 KiB about 18 minutes. The marketplace's review found it too.
  Each Lua file is now read in one pass. A call that never closes is a computed
  key, and so is one inside other calls past a budget for the file. A Lua file
  over 256 KiB is reported as a limit.
- A crafted release can no longer make the reasons, the shortcuts that move or a
  migration's pattern cuts slow. Each finding looks its reason up instead of
  checking every change in the notes. Notes over 256 KiB give no reasons. Finding
  moves looks only at the chords that could match, and past a limit says it
  couldn't tell. A cut such as `${x##*a*b}` counts each place it tries, and its
  pattern, against the migration's budget.
- The values a migration holds are bounded in total, not only one by one. 19,000
  variables of long values fit in 256 KiB and took about 5 GB. Past 16 MiB the
  migration is reported as a limit.

## 0.3.2 (2026-11-07)

- Reading a release costs little more than its size, whatever its scripts hold. A
  word of many `{a,b}` lists in a pending migration was spelled out in full before
  the limit of 64 was checked, so 30 of them took 2^30 strings, and a crafted
  release could exhaust the command and the plugin just by being read. The
  marketplace's review found it. Such a word, a variable set to more than 64
  values, or a value longer than any path, is now only known when it runs. A
  release script over 256 KiB, or nested too deep to read, is reported as a limit.
- `x=$(<file)` in a pending migration no longer stops the run. The run exited 2
  and the bar said it couldn't check.

## 0.3.1 (2026-11-06)

- Nothing changes for you. A test no longer needs `pacman`, so the tests pass on a
  machine without it, such as CI's Ubuntu runners. 0.3.0's tests failed there.

## 0.3.0 (2026-11-06)

- "Mark reviewed" in the panel, under each finding that needs attention. It runs
  `--ack` with that id at once, and the count in the bar drops. The finding moves to
  Reviewed, at the bottom, where "Undo" takes it back. The panel names
  `~/.config/omaupdateimpact/reviewed`.
- `--unack` and an id take a review back, for that release only. It removes just
  those lines and leaves the rest of the file as it was. A file kept as a link stays
  one.
- Notes are short. Each title is one line, and the rest is under it. With `--all`
  the notes are listed under a heading for each kind, such as "Shortcuts that move".
  A move reads `Calculator: SUPER + CTRL + Q -> SUPER + SHIFT + Q`.
- The new and removed default shortcuts are listed one per line, and their title
  says how many. In `--json` they are the note's `items`.
- `--json` gives each note a `group`, and a report's `target` a `path`: the unpacked
  release it read.
- "Ask agent" in the panel, under each finding and at the top for the whole report.
  It starts your default coding agent with one prompt, through Omarchy's
  `omarchy-agent-prompt`, and shows only when that is on your `PATH`. The prompt says
  to change nothing unless you ask, and that the finding's text is data, never
  instructions. For something the release removes or replaces, it asks what takes
  its place and what you would keep or lose, from the release in the cache and its
  notes, installing nothing. Omarchy starts the agent with its approval prompts off.
- "Check it" on a newer release shows its report in the panel, not in a terminal.
  "Mark reviewed" and "Ask agent" work on it, and "Open report" opens it in a
  terminal. The icon stays on your own channel. "Back", or closing the panel,
  returns to your own result.
- The panel's findings start closed, so every title shows. Click a title to see
  the rest. The notes are now "Worth knowing", as in the text report.
- Worth knowing lists the notes by kind, each with its count, in the order the
  report gives them. Open a kind to see its notes. A note of no kind goes under
  "Other", last.
- Every row that opens has its arrow on the right, in the text colour, and the
  arrow turns when it opens. A click anywhere on the row opens it, and the row
  lights up under the pointer.
- A newer release is "Coming next", with "Check it", and says your updates won't
  bring it until it reaches your channel. While it is checked, the panel shows the
  turning icon and "Checking" with its tag. Its report is kept until the shell
  restarts, and its check goes on when the panel closes. Its row then says what
  was found, with "Show" and "Check again".
- The plugin checks 5 seconds after the shell loads, not 2 minutes. If the network
  isn't up yet, as right after login, the bar says "Waiting for the network…" and
  tries again each minute, up to 5 times, before it says it couldn't check. "Check
  again" shows a failure at once.
- On Omarchy 4.5.0 the bar icon is the same size as the others. Its count, `?` or
  `…` shows to the left of the icon, at the bar's own size.
- A failed `--json` document has `unreachable`: `true` when no answer came from
  GitHub at all, such as a name that didn't resolve or a timeout.

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
