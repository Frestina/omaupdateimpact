# omaupdateimpact

Check your Omarchy setup against a release before you update. It tells you what
the update would do to *your* machine, not what changed in general.

```
omaupdateimpact               # the release your update channel would deliver
omaupdateimpact --channel rc  # the release another channel would deliver
omaupdateimpact v4.5.0-rc2    # a specific release
```

If you already have that release, it says so, names any newer release on another
channel, and exits 0. The `edge` and `dev` channels have no tagged releases, so
those need a tag.

It changes nothing on your system, and nothing from the release is ever run:
the release is downloaded to `~/.cache/omaupdateimpact` and read as text. Two
releases stay there and older ones are removed. If GitHub's rate limit gets in the
way, set `GITHUB_TOKEN`.

## What it checks

- **Key bindings:** your `~/.config/hypr/bindings.lua` against the release's
  defaults. It flags a new default that clashes with one of your bindings, and a
  shortcut you turned off that moves to another key and so comes back. It also
  lists moved, new, changed and removed defaults.
- **Packages:** the migrations you haven't run yet, and which installed packages
  they remove. Those are the ones an update takes away; a package that only left
  the default install list stays on your machine.
- **Commands:** `omarchy-*` commands the release deletes that your own files still
  call: Hyprland config, hooks, extensions, plugins, `shell.json`, `shell.toml`,
  `~/.local/bin`, systemd user units, `~/.local/share/applications` and your bash,
  zsh or fish startup files. A file Omarchy put there, unchanged, is a note.
- **Plugins:** `qmllint` warnings that are new with the release's shell.

## Exit codes

| Exit | Meaning |
| --- | --- |
| 0 | Every check ran and nothing needs attention, or there is no update |
| 1 | Something needs attention |
| 2 | No verdict: bad usage, a failed download, an unusable tree or a crash |
| 3 | Nothing needs attention, but at least one check couldn't run |

Exit 3 names the checks that didn't run. A failure prints one line, and `--debug`
adds the traceback.

## Limits

- `qmllint` can't prove a plugin works. Most plugin breaks only show when the
  shell runs them, so new warnings are a hint and a clean result isn't a promise.
- Bindings are read as text, so a computed key can't be compared. In the defaults
  it is a note while its expression stays the same in both versions, even if a
  loop's range changes. If the expression changes, or the key is in your own
  bindings, it is reported as a limit. A binding or an unbind inside an `if` counts
  as always on.
- Migrations are read as text. A removal it can't name, such as
  `"${targets[@]}"`, or one in a string for `bash -c` or `eval`, is reported as a
  limit, and you check that migration by hand. A removal in a heredoc fed to a
  shell isn't seen.
- A migration can remove packages through other release files. Commands in `bin`,
  and `$OMARCHY_PATH` scripts it sources or runs, are read too. What they remove is
  "may remove", because it depends on arguments that aren't followed. A file named
  by a variable isn't followed, and of the `omarchy` command only `omarchy pkg` is
  read.
- A removal is "will remove" unless it sits inside an `if`, a loop, a `case`, a
  function, or after `&&` or `||`. A migration that exits early, as with
  `x || exit 0`, still says "will remove".
- Your files are read as text. A command called from a binary isn't seen. A file
  that can't be read, or a text file over 10 MiB, is reported as a limit. A broken
  link counts, so remove the ones you don't need.
- It doesn't read `omarchy_default_bindings = false` from your `hyprland.lua`.
- It won't catch a failure during the update itself.

## Install

Needs Python 3.11 or newer. `qmllint` is optional and comes with Qt.

```
ln -s "$PWD/bin/omaupdateimpact" ~/.local/bin/omaupdateimpact
```

## Tests

```
tests/run
```
