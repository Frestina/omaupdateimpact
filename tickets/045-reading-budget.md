---
id: "045"
title: Reading a release has one budget
milestone: M4 Plugin
depends_on: ["044"]
---

# 045 Reading a release has one budget

## Goal

End the review loop on
[14152](https://github.com/omacom/omarchy-plugin-marketplace/issues/14152) by
closing the class, not the next instance. Each of the maintainer's four findings
was one reader of release text that a crafted release could make slow, with the
same consequence: the plugin's check doesn't return, because nothing caps it
(`plugin/Service.qml` supplies no analysis deadline, as the fourth finding says).
040 to 044 bounded each reader they found. A budget for the whole read caps every
reader, including ones nobody has traced yet, and a run past it is never clear.

## Spec

- [Checks](../SPEC.md#checks)
- [Exit codes](../SPEC.md#exit-codes)
- [What must never happen](../SPEC.md#what-must-never-happen)

## Scope

- The checks share one budget of 2 minutes of the command's own CPU time, counted
  from when both trees are ready. Waiting doesn't count: the download, the cache
  lock, and `qmllint`, which runs as its own process with its own 60-second limit.
  A process-CPU timer (`signal.setitimer(signal.ITIMER_PROF, ...)`) fits, since
  children don't inherit it, but the mechanism is the implementer's choice. Real
  runs take about 3 s of CPU on v4.5.0, with a real home and its plugins.
- Past the budget, the run stops with exit 2 and one line that says reading the
  release took too long, so nothing was compared. `--json` gives a `failed`
  document with that reason and `unreachable: false`. `--ack` and `--unack` stop
  the same way and write nothing. A `qmllint` still running is stopped with it, so
  nothing is left behind.
- The plugin needs no change: a `failed` document already shows as "couldn't
  check" with its reason. Check that it does, with a document from a run that ran
  out of budget.
- 044's review follow-up: the timing test passes on 044's old reader on a fast
  machine (37.9 s at the test's 32,768 names, under its 60 s deadline), so it
  doesn't fail without the fix. Give 044's two shapes a deadline that its old
  reader can't meet, a few seconds, as the new one takes 0.01 s. Check that each
  shape from 040 to 043 fails on its old reader too, and tighten any that doesn't.
- Release 0.3.6 as 042 to 044 did: version, changelog, README's clone, tag, GitHub
  release, CI watched. The tag is the commit at the top of `main` on GitHub, and
  stays there: the marketplace's form asks for the current HEAD, and the catalog
  shows "Update unverified" when HEAD moves past the verified commit. Commits
  after the tag, such as ticking this ticket's boxes, stay local until 14152 is
  verified. The hold note and 039's boxes name 0.3.6.
- The update request: edit 14152's "Target commit" to 0.3.6's full SHA, which is
  what reruns the marketplace's checks, and reply once. The reply has a table of
  each of the four findings, the fix and the test that shows it. It says who
  controls the input (a tree the user picks with `--target`, or Omarchy's own
  release, whose author gets root on the next update), that no boundary is
  crossed, and that the budget now caps the cost of any reader. It asks the
  maintainer whether anything else blocks approval. Numbers are no more than the
  tests show. The owner confirms the edit and the reply before either is sent.

## Not in this ticket

- Hunting for more slow readers. The budget caps them, and the timing test keeps
  the ones found.
- A deadline in the plugin on the whole run. The download and the lock wait are
  bounded by the requests' timeouts and the lock's 15 minutes. In the backlog.

## Done when

- [x] A run whose reading passes the budget stops with exit 2, a `failed`
      document and its reason, and never a clear result.
- [x] Time spent waiting, on the network, the lock or `qmllint`, doesn't count.
- [x] `--ack` and `--unack` past the budget write nothing.
- [x] The plugin shows such a document as "couldn't check" with the reason.
- [ ] Each shape in the timing test fails on the reader it was added for.
- [x] Real runs on v4.5.0 and v4.5.0-rc3 give the same results as before.
- [ ] `v0.3.6` and its GitHub release exist on the commit at the top of `main` on
      GitHub, and CI passed on it.
- [ ] The owner confirmed the edit and the reply, 14152 targets 0.3.6's SHA, and
      the marketplace's checks ran on it.
- [x] `tests/run` passes.
