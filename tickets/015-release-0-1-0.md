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
- The owner types `/audit`, since it can't be started for them. Clear everything High
  or above.
- Run a history scan for secrets and personal data before publishing.
- Confirm the drift watch runs on its schedule, before the tag. The audit on
  2026-11-02 found no scheduled run, and free accounts may not get scheduled runs in a
  private repo, so going public doesn't wait for it. Leave the cron at every 15
  minutes until a scheduled run passes, then set it back to `17 6 * * *`: each run
  downloads a release. If none has run a day after the repo goes public, find out why.
- Stop and wait for the owner's go-ahead before making the repo public, and again
  before the tag.
- Once the repo is public, make CI's jobs required checks on `main`, with admins
  exempt, so ticket commits still go directly to `main`.
- Turn on private vulnerability reporting once the repo is public, or the link in
  `SECURITY.md` leads nowhere.
- Tag `v0.1.0` with release notes taken from the changelog, and give the changelog
  its date.
- Share it where Omarchy users are, after the owner has reviewed the text.

## Done when

- [x] Both machine runs have been read by a person, and every finding was right or
      became a ticket.
- [x] The audit has nothing High or above.
- [ ] The drift watch has passed at least once on its schedule, and its cron is back
      to `17 6 * * *`.
- [x] A pull request with a red check can't be merged.
- [ ] The tag and release exist.
