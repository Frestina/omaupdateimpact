---
id: "023"
title: Marketplace listing
milestone: M4 Plugin
depends_on: ["015", "022", "027"]
---

# 023 Marketplace listing

## Goal

List the plugin where Omarchy users look for tools.

## Scope

- Prepare the version with the `omarchy-plugin-release` skill.
- Prepare the listing with the `omarchy-plugin-publish` skill. The owner confirms
  the attestations before the issue is created.
- Answer review comments until it's listed.
- README, Install: the plugin first, then the terminal. Say plainly that each works
  on its own: the plugin brings its own command, and the clone with `install.sh` is
  only for the terminal and the menu row.
- A new `preview.png`: the icon in the top bar, just left of the owner's fleetlog
  icon, not in a bar at the bottom. Every plugin on the owner's bar is in a public
  repository, so they may show. Their data must still be fictional.

## Done when

- [ ] The owner has confirmed the attestations.
- [ ] The README's Install section puts the plugin first, and says the plugin and
      the terminal install each work on their own.
- [ ] `preview.png` shows the icon in the top bar, left of the fleetlog icon, and
      no real data.
- [ ] The plugin is listed, and installs with `omarchy plugin add` on a clean
      machine.
