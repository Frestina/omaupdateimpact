# omaupdateimpact

An Omarchy update can change your shortcuts, remove packages you use and delete
commands your scripts call. Release notes say what changed for everyone. They can't
say what it means for your machine, so you find out afterwards.

omaupdateimpact tells you before you update. This is its report for a made-up machine
on v4.0.6, looking at v4.5.0-rc2:

```
$ omaupdateimpact v4.5.0-rc2
Omarchy 4.0.6-1 -> v4.5.0-rc2 (rc channel, prerelease). Nothing was changed.
Checked 207 default bindings, 3 of yours, 27 pending migrations for packages and 28 for
file edits, 7 of your files for 6 deleted commands, 1 plugin linted.

Needs attention
  - ALT + ALT_R: your "Scratchpad" will clash with the new default "Start dictation
    (push-to-talk) / Stop dictation (push-to-talk)". Both will fire.
    Fix: Add hl.unbind("ALT + Alt_R") above your binding, or choose another key.
  - SUPER + M: your "Music" will clash with the new default "Minimize window to the
    dock". Both will fire.
    Fix: Add hl.unbind("SUPER + M") above your binding, or choose another key.
  - SUPER + CTRL + T: you turned off "Activity" here, but it moves to SUPER + SHIFT + T,
    so it comes back.
    Fix: Add hl.unbind("SUPER + SHIFT + T") too.
  - The update will remove dua-cli, which is installed here.
    Fix: After the update, run omarchy pkg add dua-cli (aur-add for an AUR package).
  - The update may remove t3code-bin, which is installed here.
    Fix: If it goes, run omarchy pkg add t3code-bin (aur-add for an AUR package).
  - The update will remove tensaku, which is installed here.
    Fix: After the update, run omarchy pkg add tensaku (aur-add for an AUR package).
  - ~/.bashrc calls omarchy-voxtype-remove, which the release deletes.
    Fix: Change or remove line 1. This tool can't tell what replaces the command.
  - ~/.config/omarchy/hooks/post-update calls omarchy-voxtype-status, which the release
    deletes.
    Fix: Change or remove line 4. This tool can't tell what replaces the command.
  - ~/.config/systemd/user/nightly-backup.service calls omarchy-system-shutdown, which
    the release deletes.
    Fix: Change or remove line 7. This tool can't tell what replaces the command.
  - ~/.local/bin/end-of-day calls omarchy-system-reboot, which the release deletes.
    Fix: Change or remove line 4. This tool can't tell what replaces the command.

Worth knowing: 12 notes. Add --all to see them.

Limits of this check
  - Couldn't read what migrations/1785351479.sh removes, so check it by hand.

These checks ran in part: packages.
```

It changes nothing, and nothing from the release is ever run. Each finding says what
to do, and you do it.

omaupdateimpact is unofficial. It isn't affiliated with Omarchy or 37signals.

## Install

Needs Python 3.11.4 or newer. `qmllint` is optional, and comes with `qt6-declarative`.

```
git clone https://github.com/Frestina/omaupdateimpact.git
cd omaupdateimpact
./install.sh
```

That links the command into `~/.local/bin`, so keep the clone where it is. Running
it twice is harmless, and it won't replace a file that isn't its own link.

To update, run `git pull` in the clone. To remove it, run this there:

```
./install.sh --uninstall
```

That removes the link and tells you where the cache is, which it leaves for you to
delete.

## Usage

Run it before `omarchy update`. Omarchy has no pre-update hook, so it can't run by
itself.

```
omaupdateimpact               # the release your update channel would deliver
omaupdateimpact --channel rc  # the release another channel would deliver
omaupdateimpact v4.5.0-rc2    # a specific release
omaupdateimpact --all         # every note, not only how many there are
omaupdateimpact --json        # one JSON document, for scripts: see docs/json.md
```

![A terminal running omaupdateimpact on a made-up machine](docs/demo.svg)

If you already have that release, it says so, names any newer release on another
channel, and exits 0. The `edge` and `dev` channels have no tagged releases, so
those need a tag.

The release is downloaded to `~/.cache/omaupdateimpact`. Two releases stay there and
older ones are removed. If GitHub's rate limit gets in the way, set `GITHUB_TOKEN`.
Colour shows on a terminal only, and `NO_COLOR` turns it off.

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
- **Edits:** files of yours that the migrations you haven't run look like they edit
  or remove, with `sed -i`, `cp`, `mv`, `install`, `ln -f`, `rm`, `tee`, `>` or `>>`.
  A file that is still
  Omarchy's default says nothing. The rest are notes, because a migration that is
  read and not run can't say what the file will hold.

## Exit codes

| Exit | Meaning |
| --- | --- |
| 0 | Every check ran and nothing needs attention, or there is no update |
| 1 | Something needs attention |
| 2 | No verdict: bad usage, a failed download, an unusable tree or a crash |
| 3 | Nothing needs attention, but at least one check couldn't run |

Exit 3 names the checks that didn't run, and those that ran in part. A failure
prints one line, and `--debug` adds the traceback.
With `--json`, every exit code comes with a document. See [docs/json.md](docs/json.md).

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
- A migration's writes are read as text too. A function's `"$1"` holds what its
  calls pass. A path only known when it runs, such as a `$(...)` or an array, is
  reported as a limit, unless `sudo` writes it, which is taken to be a system file. So is `find` in your files with `-delete`, or with `-exec` running a
  writer. Other writers, such as `xargs`, `awk -i inplace`, `perl -i`, `rsync`,
  `truncate` or a `bash -c` string, aren't read, and neither is a write made by a
  release command, such as `omarchy-bar`. A loop over files may change only some
  of them, and the note can't tell which. `~/.cache` and `~/.local/state` aren't
  counted as your files.
- Your files are read as text. A command called from a binary isn't seen. A file
  that can't be read, or a text file over 10 MiB, is reported as a limit. A broken
  link counts, so remove the ones you don't need.
- It doesn't read `omarchy_default_bindings = false` from your `hyprland.lua`.
- It won't catch a failure during the update itself.

## Safety

It reads your config, so here is what it does with it.

- **It changes nothing.** The only thing it writes is its cache. `./install.sh` adds
  one link, and only when you run it.
- **Nothing from a release runs.** Release files are read as text. A migration is
  split into shell tokens, never run. Key bindings are read without running Lua.
- **Nothing about you leaves the machine.** It makes GET requests to GitHub for the
  list of releases and the archive of a release. There is no telemetry, and the
  report stays in your terminal.
- **`GITHUB_TOKEN` goes to `api.github.com` only.** It isn't sent to the archive or
  on a redirect, and it is never printed.
- **The commands it runs are your own.** It runs `omarchy-version`,
  `omarchy-version-channel`, `pacman -Qq` and, if you have it, `qmllint`. They come
  from your system, never from a release. `qmllint` reads QML and doesn't run it.
- **A check that didn't run is never shown as clear.** It is named in the report, and
  the exit code isn't 0.

It is one Python file, [bin/omaupdateimpact](bin/omaupdateimpact), with no
dependencies, so you can read what it does. To report a problem, see
[SECURITY.md](SECURITY.md).

## Next to omaforecast

[omaforecast](https://github.com/w-mir1/omaforecast) dry-runs migrations in a sandbox
and shows the config diffs. omaupdateimpact reads the release and needs no sandbox.
It can say that a migration looks like it edits a file you changed, but not what the
file will hold. omaforecast runs the release and sees those edits, but its forecast
doesn't cover your bindings or packages. They answer
different questions, so use both if you want both answers.

## Project

- [CHANGELOG.md](CHANGELOG.md) lists what changed.
- [CONTRIBUTING.md](CONTRIBUTING.md) says how to help.
- [SPEC.md](SPEC.md) says how it behaves, and why.
- [LICENSE](LICENSE): MIT.
