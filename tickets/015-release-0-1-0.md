---
id: "015"
title: Release 0.1.0
milestone: M2 First release
depends_on: ["011", "014"]
---

# 015 Release 0.1.0

## Goal

Put a tagged version in front of other people, and prove it on more than one
machine first.

## Scope

- Run it on at least two real machines, on stable and rc, including one with no
  customization and one with several plugins.
- Run `/audit` again and clear everything High or above.
- Run a history scan for secrets and personal data before publishing.
- Tag `v0.1.0` with release notes taken from the changelog.
- Publish the AUR package from 013.
- Share it where Omarchy users are, after the owner has reviewed the text.

## Done when

- [ ] Both machine runs have been read by a person, and every finding was right or
      became a ticket.
- [ ] The audit has nothing High or above.
- [ ] The tag and release exist, and the AUR package installs on a clean machine.
