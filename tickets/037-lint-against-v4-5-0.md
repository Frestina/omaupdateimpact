---
id: "037"
title: Lint and check against v4.5.0
milestone: M4 Plugin
depends_on: ["011"]
---

# 037 Lint and check against v4.5.0

## Goal

Check the plugin against the stable release people now run. v4.5.0 came out on
2026-11-05, and the owner's machine updated to it. CI still lints the plugin against
v4.0.6 and v4.5.0-rc2, and the spec says the plugin and the menu row were checked
against those two. Nobody stays on rc2: the rc channel moved on to v4.5.0.

A check by hand on the day of the update found nothing broken. The plugin loaded in
the 4.5.0 shell, and `tests/lint-plugin /usr/share/omarchy` passed. The shell
functions the plugin calls were still there. From v4.5.0-rc3 to v4.5.0,
`omarchy-menu.jsonc` only added and reordered rows. The launcher,
`omarchy-agent-prompt` and `omarchy-version-channel` didn't change. This ticket makes
that check part of CI, and repeats it against rc2, which the spec names.

## Spec

- [Install](../SPEC.md#install): the menu row's format
- [Plugin](../SPEC.md#plugin): what it was checked against, What it runs and touches,
  Tests

## Scope

- CI's "Lint the plugin's QML" step lints against v4.0.6 and v4.5.0, in place of
  v4.5.0-rc2. v4.0.6 stays, as someone who hasn't updated may still install the
  plugin. The comment above the step and the example in `tests/lint-plugin` change
  with it.
- Read v4.5.0's own files, not memory or this ticket, against what the spec says
  Omarchy does:
  - The menu row: `default/omarchy/omarchy-menu.jsonc` and the menu code that reads
    `~/.config/omarchy/extensions/omarchy-menu.jsonc`.
  - The launcher `omarchy-launch-floating-terminal-with-presentation`, which joins its
    arguments and runs them in a second `bash -c`. The comment in
    `tests/test_plugin.py` names v4.0.6 and v4.5.0-rc2.
  - `omarchy-agent-prompt` and `omarchy-agent`, as "Ask agent" uses them.
  - The shell functions the plugin calls: `serviceFor`, `updateEntryInline` and
    `Util.execArgv`. Also how the shell counts a plugin as enabled from `shell.json`.
- If they still hold, the spec's two "checked against … v4.0.6 and v4.5.0-rc2" lines
  name v4.5.0 instead of rc2, and so does the comment in `tests/test_plugin.py`. If
  one doesn't hold, stop and tell the reviewer. Don't change the plugin in this
  ticket.

## Not in this ticket

- The trimmed release fixtures in `tests/fixtures/releases`, and the README's report
  and recording, stay on v4.0.6 and v4.5.0-rc2. They are real release files, and they
  still test the parser. Moving them would rewrite the golden files, the demo and the
  README. The drift watch already reads v4.5.0 every day, and passed on the day it
  was published. See the backlog.
- The spec's examples from v4.5.0-rc2, such as its migrations, stay. They are
  examples of formats, not claims about the current release.

## Done when

- [x] CI's lint step names v4.0.6 and v4.5.0, and `tests/lint-plugin` passes on both
      trees locally. `main` isn't pushed while the listing is in review (see the
      README), so CI's own run is checked when it is.
- [x] `tests/lint-plugin` names v4.5.0 in its example.
- [x] Each item under "Read v4.5.0's own files" was checked in v4.5.0's files, and
      the message to the reviewer says what was read.
- [x] The spec and `tests/test_plugin.py` say v4.0.6 and v4.5.0 where they said what
      was checked.
- [x] `tests/run` passes.
