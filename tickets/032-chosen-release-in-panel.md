---
id: "032"
title: A newer release's report in the panel
milestone: M4 Plugin
depends_on: ["030"]
---

# 032 A newer release's report in the panel

## Goal

Let someone on stable look at a newer release's report in the panel, and use "Mark
reviewed" and "Ask agent" on it, without opening a terminal.

The owner asked for this after trying 030. Up to date on stable, the panel shows no
report, so neither button shows, and "Check" on the newer rc only opens the terminal.
029 left this out on purpose. Now it's wanted.

## Spec

- [Plugin](../SPEC.md#plugin): The panel, When it checks, What it runs and touches

The spec records the decisions below.

## Decisions

- **"Check" shows the report in the panel.** With `noUpdate`, each release in `newer`
  has "Check". It runs the bundled command with `--json <tag>`, and the panel shows
  that document in the same sections as the user's own. Before it runs, the button
  says the release downloads first, about 200 MB, unless `cached` says it's there.
  While it runs, the panel says what it is checking.
- **The bar stays on the user's channel.** The icon, the count and the tooltip come
  only from the user's own result. A release chosen by hand never changes them, as an
  update wouldn't deliver it.
- **The panel says which report it shows.** At the top: the release, that it was
  chosen by hand, and that the bar follows the user's channel. "Back" returns to the
  user's own result. Closing the panel returns to it too.
- **Everything else works on it.** "Mark reviewed" runs `--ack` for that tag, so the
  review counts for that release only, as `--ack` already does. Its document replaces
  the chosen report, not the user's own. "Ask agent" hands over the chosen report.
  "Open report" opens that tag in the terminal, as "Check" does today.
- **It isn't kept.** The timer and "Check again" check the user's own release only.
  The chosen report stays in memory until "Back", until the panel closes, or until
  the shell restarts. A chosen check already running isn't started twice, and a
  check of the user's own can't run at the same time, as today.
- **A check that fails** shows "couldn't check" for that release in the panel, and
  leaves the bar alone.

## Scope

- As above, in `State.js`, `Service.qml` and `Widget.qml`.
- `node` tests on the golden documents: a chosen report never changes the bar's
  state, `--ack` on it names its tag, "Back" and closing return to the user's own,
  and a failed chosen check stays in the panel.
- README: "Check" shows the report in the panel, and "Open report" opens it in the
  terminal.
- CHANGELOG, under Unreleased.

## Not in this ticket

- Picking any release by hand. Only the newer releases the command names in `newer`.

## Done when

- [x] "Check" on a newer release shows its report in the panel, with "Mark reviewed"
      and "Ask agent", and the bar's state doesn't change. Tested with fixture JSON.
- [x] "Back" and closing the panel return to the user's own result.
- [x] "Mark reviewed" on a chosen report runs `--ack` with its tag. Tested.
- [x] The plugin still passes `omarchy plugin validate` and CI's QML lint.
- [x] `tests/run` passes.
