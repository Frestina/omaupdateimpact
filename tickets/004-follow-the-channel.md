---
id: "004"
title: Follow the update channel
milestone: M1 Trust
depends_on: ["003"]
---

# 004 Follow the update channel

## Goal

Check the release the user would really get. Today the default is the newest
release of any kind, so a stable user at the latest stable version is told about
an RC they aren't due, and exit 1 suggests a problem with an update that isn't
coming.

## Spec

- [Choosing the release](../SPEC.md#choosing-the-release)

## Scope

- Read the channel from `omarchy-version-channel`, and add `--channel`.
- stable uses `/releases/latest`; rc uses the newest release, prereleases included.
- edge, dev or an unknown channel with no tag: exit 2, and say to pass a tag.
- If the target is what's installed, say so, name any newer release on another
  channel with the command to check it, and exit 0.
- The first line of the report names the channel and whether the target is a
  prerelease.

## Done when

- [ ] Each channel picks the right release, with tests against canned API data.
- [ ] Installed `4.0.6-1` and target `v4.0.6` count as the same version, with a
      test.
- [ ] A tag argument overrides the channel, with a test.
- [ ] Up to date gives exit 0 and mentions the newer RC, with a test.
- [ ] `tests/run` passes.
