---
id: "029"
title: Check a newer release, and choose how often, from the panel
milestone: M4 Plugin
depends_on: ["022"]
---

# 029 Check a newer release, and choose how often, from the panel

## Goal

Let someone who never opens a terminal look at a release before choosing it, and set
how often the plugin checks without editing `shell.json`.

The owner asked for both after 022. Someone on stable sees that rc has a newer
release, but can only check it from a terminal. And the check interval can only be
changed by hand in `shell.json`, since Omarchy has no screen for widget settings.

## Spec

- [Plugin](../SPEC.md#plugin): The panel, When it checks, What it runs and touches
- [Choosing the release](../SPEC.md#choosing-the-release)

## Scope

- With `noUpdate`, each newer release in `newer` gets a "Check" button. It opens
  `omaupdateimpact <tag>` in the terminal launcher, as "Open report" does, with the
  bundled command. The button says the release downloads first, about 200 MB, unless
  it is in the cache.
- The bar and the service's state stay on the user's channel. A chosen release
  never changes the icon.
- A "Check every" choice in the panel: only when asked, 1, 6, 12 or 24 hours. It
  saves through the shell's `updateEntryInline`, and the service takes the new value
  at once. A value set by hand that isn't offered is kept and shown.
- Fix the backlog's "Open report with a space in HOME" here, since the new button
  goes through the same launcher. Remove that backlog line.
- Anything the owner finds when trying the plugin, added here before it starts.

## Not in this ticket

- Checking a chosen release inside the panel. The report in the terminal says it all.
- Marking findings reviewed from the panel. It stays in the backlog.

## Done when

- [ ] Each newer release has a button that opens its report, tested with fixture
      JSON, and the bar's state doesn't change.
- [ ] The interval choice is saved in `shell.json` through `updateEntryInline`, and
      the next check follows it.
- [ ] A tag and a path with a space reach the terminal intact.
- [ ] The plugin still passes `omarchy plugin validate` and CI's QML lint.
- [ ] `tests/run` passes.
