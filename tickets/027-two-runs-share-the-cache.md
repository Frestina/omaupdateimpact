---
id: "027"
title: Two runs share the cache
milestone: M4 Plugin
depends_on: ["005"]
---

# 027 Two runs share the cache

## Goal

Two runs at once both get the right answer, and a release downloads once.

Found in 021. The plugin's service checks on its own, so a run from a terminal or
the menu row can start while it downloads. Today both runs see no release in the
cache and both download it. The first to finish moves it into place. The second
can't, as the folder is there now (`Directory not empty`), so it ends as `failed`,
after downloading 200 MB for nothing. A run's prune can also move away an older
release that the other run is reading. A tree that vanishes mid-run reads as no
package removals, which looks clean, so that half breaks the first rule.

## Spec

- [Downloads](../SPEC.md#downloads)
- [Files](../SPEC.md#files)
- [When it checks](../SPEC.md#when-it-checks)

## Scope

- A run that downloads or prunes holds a lock in the cache, so a second run waits
  and then finds the release there.
- A release that a run is reading isn't pruned under it.
- Record in the spec how long a run waits and what it says while it does.

## Done when

- [x] Two runs at once download a release once, and both finish with the same
      result. A test shows it, and fails without the lock.
- [x] A run reading an older release keeps it while another run prunes.
- [x] The spec says how the cache is shared.
