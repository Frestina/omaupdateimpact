---
id: "033"
title: Panel polish after the owner's first use
milestone: M4 Plugin
depends_on: ["032"]
---

# 033 Panel polish after the owner's first use

## Goal

Make the panel easier to read and to come back to. The owner asked for each of these
after using 030 and 032 on their own bar.

## Spec

- [Plugin](../SPEC.md#plugin): The panel

The spec already records each decision below.

## Scope

- **A chosen check looks busy.** While "Check it" runs, the panel shows the same
  turning icon as "Check again", and "Checking v4.5.0-rc3…" in the header, with
  whether it downloads. A glance should be enough to see that it runs.
- **"Coming next".** The newer release's row reads "Coming next: v4.5.0-rc3", then
  "A test release on the rc channel. Your updates won't bring it until it reaches
  stable." for a user on stable, with the user's own channel named. The button says
  "Check it".
- **A chosen report is kept.** It stays in memory, by its tag, until the shell
  restarts. Closing the panel stops neither the report nor a check of it. The panel
  always opens on the user's own result. The "Coming next" row then shows what was
  found, such as "10 things need attention", with "Show", which opens it without
  running anything, and "Check again". This changes 032's decision that closing the
  panel drops it.
- **Findings start closed.** Each finding, in every section, shows its title, and a
  click on the title opens the rest. Needs attention and Couldn't check stay open as
  sections, so every title shows.
- **"Worth knowing".** The Notes section is called "Worth knowing", as in the text
  report.
- README and CHANGELOG, under Unreleased.

## Not in this ticket

- `items`, `--unack` and the prompt's new step. Those are 034.

## Done when

- [ ] A chosen check shows the turning icon and "Checking <tag>…" in the header.
      Tested.
- [ ] The row reads "Coming next", names the user's channel, and the button says
      "Check it".
- [ ] A chosen report and its check outlive a closed panel. The panel opens on the
      user's own result, and "Show" opens the chosen one with nothing run. Tested.
- [ ] Every finding starts closed and opens on its title. Needs attention and
      Couldn't check never collapse as sections. Tested.
- [ ] The notes section is "Worth knowing".
- [ ] The plugin still passes `omarchy plugin validate` and CI's QML lint.
- [ ] `tests/run` passes.
