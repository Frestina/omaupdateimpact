# omaupdateimpact

Check your Omarchy setup against a release before you update. It tells you what
the update would do to *your* machine, not what changed in general.

```
omaupdateimpact              # the newest release, including release candidates
omaupdateimpact v4.5.0-rc2   # a specific release
```

It changes nothing on your system, and nothing from the release is ever run:
the release is downloaded to `~/.cache/omaupdateimpact` and read as text.

## What it checks

- **Key bindings:** your `~/.config/hypr/bindings.lua` against the release's
  defaults. It flags a new default that clashes with one of your bindings, and a
  shortcut you turned off that moves to another key and so comes back. It also
  lists moved, new, changed and removed defaults.
- **Packages:** the migrations you haven't run yet, and which installed packages
  they remove. Those are the ones an update takes away; a package that only left
  the default install list stays on your machine.
- **Commands:** `omarchy-*` commands the release deletes that your Hyprland
  config, hooks, extensions, plugins or `.bashrc` still call.
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
- Bindings are read as text, so bindings with computed keys are counted but not
  compared, and a binding inside an `if` counts as always on.
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
