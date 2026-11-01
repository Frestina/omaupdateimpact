---
id: "015"
title: Release 0.1.0
milestone: M2 First release
depends_on: ["011", "014", "024"]
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
- Once the repo is public, make CI's jobs required checks on `main`, with admins
  exempt, so ticket commits still go directly to `main`.
- Turn on private vulnerability reporting once the repo is public, or the link in
  `SECURITY.md` leads nowhere.
- Tag `v0.1.0` with release notes taken from the changelog, and give the changelog
  its date.
- Publish the AUR package from 013. Its checksum is `SKIP` until the tag exists, so
  set it from the tagged tarball and generate `.SRCINFO` first.
- Add the AUR package to the README's Install section once it installs.
- Share it where Omarchy users are, after the owner has reviewed the text.

## Done when

- [ ] Both machine runs have been read by a person, and every finding was right or
      became a ticket.
- [ ] The audit has nothing High or above.
- [ ] A pull request with a red check can't be merged.
- [ ] The tag and release exist, and the AUR package installs on a clean machine.
