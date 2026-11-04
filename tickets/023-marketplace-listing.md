---
id: "023"
title: Marketplace listing
milestone: M4 Plugin
depends_on: ["015", "022", "027", "029"]
---

# 023 Marketplace listing

## Goal

List the plugin where Omarchy users look for tools.

## Scope

- Prepare the version with the `omarchy-plugin-release` skill. It is the next
  version after 0.1.0, as the changelog's Unreleased holds `--json`, the edits
  check, reasons, `--ack`, the menu row and the plugin. `__version__` and
  `manifest.json` both say it, and the tag is made from it.
- The CHANGELOG names the plugin under the new version: the bar icon, its panel,
  checking a newer release and choosing how often. 022 left it out.
- Remove the AUR package. It was never published, and publishing needs an AUR
  account, which the owner doesn't have. The plugin and the clone with
  `install.sh` are the two ways to install. Delete `packaging/aur` and its version
  test, and take it out of the spec's Install section. Replace the backlog's "The
  AUR package" with a line saying it was removed and can come back from git
  history if someone gets an account. 028's rule for a command in `/usr/bin` stays,
  as it guards any packaged install.
- Prepare the listing with the `omarchy-plugin-publish` skill. The owner confirms
  the attestations before the issue is created.
- Answer review comments until it's listed.
- README, Install: the plugin first, then the terminal. Say plainly that each works
  on its own: the plugin brings its own command, and the clone with `install.sh` is
  only for the terminal and the menu row.
- Say where a plugin-only user finds the command, for `--ack`: it is
  `bin/omaupdateimpact` in the plugin's folder, and `./install.sh` there links it
  onto `PATH`. Found by the audit of 2026-11-03.
- README, Install: the clone names the release tag, as
  `git clone --branch v<version> ...`, so a terminal install gets the version that
  was reviewed. The scanner wants `git checkout --detach <full sha>`, which a commit
  can't hold for itself, so `remote-git-execution-unpinned` stays. The issue says
  why: `install.sh` makes one link and runs nothing else from the network.
- Settle the advisory scan with the release and publish skills, on the committed
  tree (`git archive`, or a fresh clone), since the working tree holds files git
  ignores. The ticket wording that matched `curl-pipe-shell` is gone. Answer the rest
  in the issue, honestly, and never by hiding a real command: the capability notes on
  `install.sh`, the plugin's `Process`, `sudo` in Omarchy's release files under
  `tests/fixtures`, and `AGENTS.md`, `CLAUDE.md` and `.claude/` in the tree, which
  are development notes that nothing loads. The demo preflight wants a bash harness
  and a `demo/fixtures` folder: `demo/run` is Python, cleans up in `finally`,
  replaces no config, and reads the golden documents.
- A new `preview.png`: the icon in the top bar, just left of the owner's fleetlog
  icon, not in a bar at the bottom. Every plugin on the owner's bar is in a public
  repository, so they may show. Their data must still be fictional.

## Done when

- [ ] The owner has confirmed the attestations.
- [ ] `--version` and `manifest.json` give the new version, and the tag matches.
- [ ] The README tells a plugin-only user how to run `--ack`.
- [ ] `packaging/aur` is gone, and nothing in the spec, README or tests names it.
- [ ] The README's Install section puts the plugin first, and says the plugin and
      the terminal install each work on their own.
- [ ] The README's clone names the release tag.
- [ ] The scan of the committed tree has no `FINDING` but
      `remote-git-execution-unpinned`, and the issue answers it and each capability.
- [ ] `preview.png` shows the icon in the top bar, left of the fleetlog icon, and
      no real data.
- [ ] The plugin is listed, and installs with `omarchy plugin add` on a clean
      machine.
