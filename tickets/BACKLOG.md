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

## Limits to keep watching

- **User bindings outside `bindings.lua`.** Only that file is parsed. Any Lua file
  under `~/.config/hypr` could call `o.bind`. Omarchy's template keeps them there,
  so this waits for a real report.
- **`omarchy_default_bindings = false`.** Documented as unread. Reading it would
  remove every default from the comparison, and it's a small change if anyone
  uses it.
- **A binding inside an `if` counts as always on.** v4.5.0-rc2's dictation
  bindings depend on the installed backend. Reading that would mean running Lua.
- **The first line shows this machine's version, even with `--root`.** Pointing
  `--root` at another tree still prints what `omarchy-version` says. Only people
  testing the tool use it that way, so it waits for 012.
- **Installed newer than the target.** Someone who moves from rc to stable has a
  version past the latest stable. The report treats that as an update, though
  nothing would be delivered until stable catches up. Waits for a real report.
- **The message when the mirror and packages disagree.** It says "the channel is
  stable / rc, and only stable and rc have tagged releases", which reads as a
  contradiction. The exit 2 is right. 012 could reword it.
- **Scratch left by a killed run.** A run killed mid-download leaves its `tmp*`
  folder in the cache. Pruning skips those, since one may belong to a live run.
  Waits for a real report.
- **Two runs at once.** One run can prune the release another is reading. A tree
  that vanishes mid-run reads as no package removals, which looks clean. Rare from
  a terminal, more likely once the plugin (022) runs it in the background, so fix
  it before then.
- **A relative `XDG_CACHE_HOME`.** The XDG spec says to ignore it, and it's used as
  given. Waits for a real report.
- **A rejected `GITHUB_TOKEN`.** A stale token shows as `HTTP Error 401`, with no
  mention of the token. 012 could name it.
- **Evidence in the text report.** Findings carry evidence, but only `--json` (016)
  will show it. 012 could print it, if it doesn't crowd the report.
