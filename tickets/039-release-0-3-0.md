---
id: "039"
title: Release 0.3.0 and update the listing
milestone: M4 Plugin
depends_on: ["023", "038", "040", "041", "042"]
---

# 039 Release 0.3.0 and update the listing

## Goal

Ship the work held on `main` since the listing went into review, as one version,
and get the marketplace to verify it.

## Spec

- [Install](../SPEC.md#install)
- [Plugin](../SPEC.md#plugin)

## Scope

- The marketplace listed `d092046`, which is `v0.2.0` plus spec and ticket edits.
  `omarchy plugin add` clones `main` as it is, so whatever is pushed reaches users
  at once. The listing shows it as unverified until a full-SHA update request is
  approved. So the version, the tag and the push go out together, and the update
  request follows straight after.
- Prepare the version with the `omarchy-plugin-release` skill. It is 0.3.0, as the
  changelog's Unreleased holds new features: "Mark reviewed", `--unack`, "Ask
  agent", a newer release's report in the panel, and notes in groups. `__version__`
  and `manifest.json` both say it. The changelog gives 0.3.0 its date.
- A new `preview.png` from `demo/run`: the panel with "Mark reviewed" and "Ask
  agent", and its findings closed, as 033 left it. Since 033, "Mark reviewed" is
  inside each finding, so the owner chose to open the first one, with the rest
  closed. `demo/run` opens it in its own copy of the widget. The icon stays in the top bar,
  left of the fleetlog icon, as in 023, and the data stays fictional. This is the
  backlog's "A preview with the new buttons".
- Scan the committed tree (`git archive`, or a fresh clone) with the release and
  publish skills. It should find no more than 023's did: no `FINDING` but
  `remote-git-execution-unpinned`. Answer anything new in the update request,
  honestly, as 023 did.
- The README's clone names `v0.3.0`.
- Push `main` and tag `v0.3.0` together, with a GitHub release whose notes come
  from the changelog. Watch CI on that push until every job ends. It is also the
  first CI run for 030 to 038, and 037's lint against v4.5.0 runs there for the
  first time.
- Prepare the update request with the `omarchy-plugin-publish` skill, naming the
  full SHA of the tagged commit. The owner confirms its text and attestations before
  it is sent. Answer review comments until the new SHA is verified.
- When the update request is in review, `tickets/README.md`'s hold note goes back
  on, naming the SHA in review. When it's verified, the note says pushes are open.

- CI failed on `v0.3.0`'s push: a test from 034 ran the real `pacman -Qq`, and
  Ubuntu's runners have none. The command and plugin were fine. A published tag
  never moves, so the owner chose 0.3.1, with only that test fixed. Its tag, its
  green CI and the SHA the marketplace verifies are one commit, and the README's
  clone names `v0.3.1`. `v0.3.0` stays as published.

- The marketplace's review of 0.3.1 on 14152 found the migration reader's brace
  expansion unbounded. The owner chose to fix it in 040 and release 0.3.2, and 14152
  then names 0.3.2's SHA. 040 found 041, an older crash on `$(<file)`, and the
  owner put it in 0.3.2 too.

- The review of 040 found its memory unbounded in total, and the bindings reader
  unbounded, as the migration reader was in 14152. The owner chose to bound both and release
  0.3.3, in 040's follow-ups and 042, and 14152 then names 0.3.3's SHA.

## Not in this ticket

- Any change to the command or the plugin. Something found here goes to the
  backlog or a new ticket, and waits for the version after.

## Done when

- [x] `--version` and `manifest.json` say 0.3.3, and the changelog dates 0.3.0,
      0.3.1, 0.3.2 and 0.3.3.
- [ ] `preview.png` shows the new panel buttons, its first finding open and the
      rest closed, and no real data.
- [ ] The scan of the committed tree has no `FINDING` but
      `remote-git-execution-unpinned`.
- [x] The README's clone names `v0.3.3`.
- [x] `v0.3.0` to `v0.3.3` and their GitHub releases exist, `v0.3.3` on the commit
      pushed to `main`.
- [x] CI passed on that push.
- [ ] The owner confirmed the update request, and the marketplace verified the new
      SHA.
- [ ] `omarchy plugin add` on a clean machine installs 0.3.3.
- [ ] `tests/run` passes.
