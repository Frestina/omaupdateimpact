# Backlog

Things deliberately not in the tickets yet. Each line says why it waits. To take
one on, turn it into a numbered ticket and add it to the table in
[README.md](README.md).

Paths already ruled out are not here; they are under
[Rejected](../SPEC.md#rejected) in the spec, with the reasons.

## Ideas worth a real look

- **Check a plugin against an RC, for plugin authors.** `--plugin PATH` plus a
  GitHub Action. It would flag `qs.*` imports and properties the release removed,
  which says more than `qmllint`'s general warnings, and it needs no Omarchy
  machine. The catalog listed 6196 plugins on 2026-10-31, so the audience is
  large. Waits until the plugin check is solid on real releases.
- **Check the prediction afterwards.** After an update, compare what was reported
  with what happened: did those packages go, did that clash fire? It proves the
  tool right or finds its bugs, and could feed a test corpus. Waits for 0.1.0,
  since it needs a stored report and a post-update hook.
- **A pre-update nudge.** If Omarchy gains a pre-update hook, an optional hook
  could show the result before the update starts. Blocked on upstream
  ([PR #10398](https://github.com/omacom/omarchy/pull/10398)). Worth commenting on
  that PR with this use case once the tool is public.
- **What the update adds.** New packages, new services, download size. Waits
  because it isn't what breaks things, and Update Review covers packages.

## Later

- **`edge` and `dev` channels.** No tags exist, so the target would be the branch
  tip. Waits for someone on those channels to ask.
- **Removed config keys.** Keys in `shell.toml` or `shell.json` that the release no
  longer reads. Needs a reliable list of keys per version, which doesn't exist yet.
- **Replacement hints for deleted commands.** When a release renames a command,
  say what to call instead. Needs a way to tell a rename from a deletion.
- **Compare any two releases without a machine.** `--from A --to B` as a general
  "what changed" report. Waits because being personal is the point of this tool.
- **Markdown output for bug reports.** A paste-ready report for an Omarchy issue.
  Waits for someone to need it.
- **Several machines.** Run the check on every machine you own. Waits for 0.1.0
  and `--json`.
- **Trimmed fixtures from a newer release.** The end-to-end tests, the golden files,
  the demo and the README's report read v4.0.6 and v4.5.0-rc2. Moving them to v4.5.0
  rewrites all of those, and rc2's files still test every format the parser reads.
  The drift watch reads the newest release every day. Waits for a release whose
  format rc2 can't show.
- **The AUR package.** Removed in 023: it was never published, and publishing needs
  an AUR account. `packaging/aur` can come back from git history if someone gets
  one. The rule that a command in `/usr/bin` leaves none of your files out stays.

## Limits to keep watching

- **A very long prompt.** "Ask agent" for the whole report puts every finding in one
  argument, and Linux caps one at 128 KiB. A report of the fixtures' size is about
  3 KiB, so it would take hundreds of findings. Then nothing opens, and nothing says
  why. Worth a cap, such as leaving out the notes, if a real report comes near it.

- **Writes made by release commands.** The edits check reads only the migration, so
  `omarchy-bar put`, `omarchy-mise-install` or `mise settings unset` editing your
  files isn't seen. The packages check already follows `bin` commands; the same walk
  could look for writes, with the "may" wording, as their arguments aren't followed.
- **Arrays in migration writes.** The reader takes `files=(a b)` as only known when
  it runs, so v4.5.0-rc2's 1791723398 stays `unknown`. It installs `${files[0]}` and
  `${files[1]}` through a function. With 1791470456, whose path comes from a
  `$(...)`, it keeps v4.5.0 at exit 3 wherever it is pending. Reading a literal array
  means changing the tokenizer the packages check shares, so it needs its own ticket.
  It waits because 1791470456 is pending wherever this one is, so reading arrays
  wouldn't bring anyone on v4.0.6 to exit 0.
- **Wildcards in the release.** v4.5.0-rc2's 1786719479 and 1787843905 link each
  folder in `$OMARCHY_PATH/default/agents/skills`. The wildcard is matched in your
  home, so the note names every file in your skills folder, not only Omarchy's
  skills, and it can't tell a link that already points there. Matching it in the
  release would name the links one by one.
- **Loops that edit only some files.** v4.5.0-rc2's 1791696584 and 1791875754 go
  through every launcher and change only web apps. The note names every launcher
  that isn't Omarchy's, so on a real machine it named three that aren't web apps.
  The note says it may change only some. Watch whether that is enough.

- **User bindings outside `bindings.lua`.** Only that file is parsed. Any Lua file
  under `~/.config/hypr` could call `o.bind`. Omarchy's template keeps them there,
  so this waits for a real report.
- **`omarchy_default_bindings = false`.** Documented as unread. Reading it would
  remove every default from the comparison, and it's a small change if anyone
  uses it.
- **`omarchy_preinstalled_bindings = false`.** Not read either, and the README's limits
  don't name it. v4.5.0-rc2 turns off `bindings/applications.lua` with it, so a clash
  with one of those defaults is a false alarm, not a miss. Name it in the README with
  the line above, and read it with that one.
- **`OMARCHY_MIGRATION_STATE`.** `omarchy-migrate` reads its state folder from it when
  it's set, and this tool always reads `~/.local/state/omarchy/migrations`. Someone
  who sets it gets every migration counted as pending, so removals can be false but
  none are missed. Waits for a real report.
- **The stable target goes by GitHub's prerelease flag.** `releases/latest` skips
  releases flagged as prereleases, while the spec says the tag decides. All 71
  releases agreed on 2026-11-02, and a mismatch still shows as "prerelease" in the
  report. Say in the spec that stable goes by GitHub's latest release, or check the
  tag.
- **The README's exit 3 says "couldn't run".** The spec says "couldn't run in full",
  and a check that ran in part also gives 3. A one-line fix with the next README
  change.
- **`hl.unbind("all")` in your bindings.** It removes every default, like
  `omarchy_default_bindings = false`. In the defaults it is applied, but in your
  file the defaults are still compared, so clashes can be false. Waits for a real
  report, and should go with that limit.
- **Default files are read in path order.** An unbind only reaches binds made before
  it, and `omarchy.lua` loads the binding files in its own order. No release unbinds
  anything in its defaults yet, so this waits until one does.
- **A default that changes spelling.** `hl.unbind` goes by text, so a release that
  rewrites `CTRL + A` as `CONTROL + A` undoes your unbind and the shortcut comes
  back. The chord looks unchanged, so it isn't reported. Rare; waits for a real
  report.
- **`ignore_mods` on a default.** v4.5.0-rc2's `ALT + Alt_R` fires with any
  modifiers held, so it also reaches a binding of yours such as `SUPER + Alt_R`.
  Only the exact chord is compared. Waits for a real report.
- **A binding inside an `if` counts as always on.** v4.5.0-rc2's dictation
  bindings depend on the installed backend. Reading that would mean running Lua.
- **The first line shows this machine's version, even with `--root`.** Pointing
  `--root` at another tree still prints what `omarchy-version` says. Only people
  testing the tool use it that way, so it waits for a real report.
- **Installed newer than the target.** Someone who moves from rc to stable has a
  version past the latest stable. The report treats that as an update, though
  nothing would be delivered until stable catches up. Waits for a real report.
- **`qmllint` output that stops parsing with exit 0.** A format change would read
  as no warnings, the same as a clean plugin. A non-zero exit is caught, and exit 0
  can't be told from Info lines alone without knowing the new format. The real
  `qmllint` test catches it where `qmllint` is installed, and CI runs that on Arch.
- **CI's oldest Python is the newest 3.11.** The minimum is 3.11.4, and `3.11` in the
  matrix follows the patch releases. The suite passed on 3.11.4 by hand when 013
  set it. Pinning it is small; waits to see if a later change touches `tarfile`.
- **A new `qmllint` waits for the next push.** Arch's `qmllint` only runs in CI on a
  push or a pull request, not daily like the drift watch. A quiet repo could miss a
  new Qt for a while. Adding the Arch job to a schedule is small; waits to see how
  quiet the repo gets after 0.1.0.
- **A new tag shape hides from the drift watch.** Tags that don't look like `v1.2.3`
  or `v1.2.3-rc1` are dropped from the list, so a `v4.6.0-beta1` would leave the
  watch reading the release before it, and passing. Waits for Omarchy to change its
  tags.
- **The watch stops if the repo goes quiet.** GitHub turns off scheduled workflows
  after 60 days with no activity in a public repo, and warns by email first. Waits
  for 0.1.0, since it only applies once the repo is public.
- **A plugin folder named like a systemd one.** The walk shared with the commands
  check skips `.wants` and `.requires` folders, so QML in one isn't linted. No QML
  project names a folder that way, so this waits for a real report.
- **A plugin's own `.qmllint.ini`.** `qmllint` runs in the plugin's folder and reads
  it, so a plugin can turn warnings off. That's the same in both runs, so it only
  hides warnings. `--ignore-settings` would stop it. Waits for a real report.
- **Scratch left by a killed run.** A run killed mid-download leaves its `tmp*`
  folder in the cache. Pruning skips those, since one may belong to a live run.
  Waits for a real report.
- **A cache where `flock` doesn't work.** Some network and FUSE file systems refuse
  `flock`. A run there fails with exit 2, where it used to work without the lock.
  Exit 2 is honest, so this waits for a real report.
- **A relative `XDG_CACHE_HOME`.** The XDG spec says to ignore it, and it's used as
  given. Waits for a real report.
- **Control characters in text from a release.** A description in a binding, or a
  reason from the release notes (018), goes to the terminal as written, so an escape
  code in one would reach it. It only shows text, and nothing runs. Strip them in the
  report, and in `--json` (016) if it matters there.
- **A migration's own description as the reason.** Every v4.5.0-rc2 migration echoes
  what it does on its first line, but only 2 of 211 match a change in the notes word
  for word. The echo could be the reason when no change names the finding, and it
  would work offline. 018 left it out: the ticket keeps reasons to the notes, and
  "Use dua for Disk Usage TUI" on a migration that also drops `dust` says less than
  it seems to. Waits to see how often findings come without a reason.
- **Notes edited after they're kept.** The notes are fetched once per release, and an
  RC's notes are sometimes edited later. A change added since isn't seen until the
  release leaves the cache. Waits for a real miss.
- **"Is now" on a key you turned off.** `hl.unbind` goes by text, so yours also turns
  off the default that lands on that key, and `SUPER + CTRL + T is now "Theme menu"`
  isn't true for you. It's a note and needs no action. Say the new default stays off.
- **A removal in a heredoc fed to a shell.** `bash <<EOF` isn't seen. Neither v4.0.6
  nor v4.5.0-rc2 does this, and the README lists it. Waits for a release that does.
- **A release file named by a variable.** `source "$x"` isn't followed, and the
  README lists it. No migration in either release does this, but release commands
  do, so making each `unknown` would make exit 0 close to impossible. Waits for a
  real miss.
- **Other `omarchy` subcommands.** Only `omarchy pkg drop` is read, so
  `omarchy install ai t3-code` isn't followed the way `omarchy-install-ai-t3-code`
  is. Neither v4.0.6 nor v4.5.0-rc2 calls `omarchy` this way.
- **An early exit is not read.** `omarchy-hw-aarch64-n1x || exit 0` at the top of a
  migration makes everything after it conditional, but it still says "will remove".
  Real migrations do this, and the README lists it. Reading it means following
  `exit` and `return`, which waits for a report that it misleads.
- **`pacman -S` doesn't cancel a drop.** Only the helpers do. Nothing does this
  after a drop yet, and the error is a false removal, not a missed one.
- **An `if` condition counts as conditional.** `if omarchy-pkg-drop a; then` always
  runs the drop, but says "may remove". Rare, and "may" is still honest.
- **A shipped file from an older release.** Omarchy's own check goes by the installed
  tree, so a hook an older release copied and this one no longer ships needs
  attention. Waits for a real report, and the error is a false alarm, not a miss.
- **Block comments in your files.** Only whole-line comments are skipped, so a call
  inside `/* */` or `--[[ ]]` counts, and so does one after `;` in a systemd unit. The
  error is a false alarm, not a miss.
- **Other places a call can live.** `~/.config/uwsm`, `~/.config/autostart`, fish's
  `conf.d`, a zsh `ZDOTDIR` and cron aren't read. Waits for a real report.
- **A link in a `.wants` folder to a unit outside it.** Those folders are skipped, so
  a unit linked only from there isn't read. `systemctl --user enable` also links it
  at the top of the folder, so this takes a link made by hand. Waits for a real
  report.
- **A folder link in `~/.local/bin`.** Links are followed and every file is read, so
  a link to a large folder makes the run slow, and paths show through the link.
  Waits for a real report.
- **Evidence in the text report.** Findings carry evidence, but only `--json` shows
  it. Printing it could crowd the report, so it waits for someone to miss it.
- **Which tree a default's evidence is in.** A binding's evidence names a file such
  as `default/hypr/bindings.lua`, the same path in both trees. A move or a removed
  default can name either. The plugin can't open the right one without knowing.
  Waits for the plugin (021) to need it.
- **`TERM=dumb`.** Colour goes to any terminal, so a dumb one gets the codes.
  `NO_COLOR` covers it. Waits for a real report.
- **A check that never ends.** The service starts no new check while one runs, and
  sets no deadline on it. The command has timeouts on its requests, so a hang is
  unlikely, but one would leave the bar on its last state until the shell restarts.
  Stopping it mid-download leaves scratch in the cache (see above). 045 caps
  reading a release at 2 minutes of CPU, so what is left is waiting: a download
  that keeps trickling, or the lock's 15 minutes. A deadline in the service on the
  whole run would cap those. Waits for a real report.
- **The plugin's timer doesn't count sleep.** Qt's timers run on a clock that stops
  while the machine sleeps, so a laptop that sleeps most of the day checks less often
  than every 6 hours. A login or an update restarts the shell, which checks again.
  Comparing the wall clock on a short timer would fix it. Waits for a real report.
- **The plugin reads all of stdout.** The command is the plugin's own, so its output
  is trusted and isn't cut while it is read, only the stderr line it shows. Marketplace
  reviewers ask for limits while receiving. Revisit in 023 if review asks.
