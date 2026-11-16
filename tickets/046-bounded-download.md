---
id: "046"
title: A release's download and unpacking are bounded
milestone: M4 Plugin
depends_on: ["045"]
---

# 046 A release's download and unpacking are bounded

## Goal

Answer the maintainer's fifth finding on
[14152](https://github.com/omacom/omarchy-plugin-marketplace/issues/14152), on
0.3.6 (`9993b0a`): `save()` and `download()` take the whole archive, decompress
it and unpack every member with no limit on the total, before 045's budget
starts. A crafted release could fill the cache's file system from the plugin's
automatic check. The finding needs control of Omarchy's own release, not of the
network. As in 045, cap the whole class with fixed limits, so the cap doesn't
depend on finding each path.

## Spec

- [Downloads](../SPEC.md#downloads)
- [Files](../SPEC.md#files)
- [Exit codes](../SPEC.md#exit-codes)
- [What must never happen](../SPEC.md#what-must-never-happen)

## Scope

- Three limits, each checked while the archive is read, never after it is
  written in full:
  - **The download:** at most 1 GiB of archive. `save()` stops when it passes
    that, on a terminal or not.
  - **The unpacked size:** at most 2 GiB. That limit counts the decompressed tar
    stream, which the gzip checksum pass already reads, and the sizes the members'
    headers state, before anything is unpacked. The headers' sizes count because
    a sparse member can state more than the stream holds.
  - **The members:** at most 100,000 entries of any kind: files, folders and
    links.
- Review follow-ups, from the 2026-11-16 handoff: `tarfile` reads each PAX
  record, GNU long name or link, and sparse map whole into memory, and none of
  the three limits stops that below 2 GiB. A 1.8 MB archive with one 400 MiB PAX
  header passed them all at 2 GiB of RAM, and a GNU long name at 2.8 GiB. The
  owner chose a fourth limit in this ticket: at most 16 MiB of headers in all,
  read before anything is unpacked, and a header longer than what is left is
  never read. Measure what v4.5.0's and v4.5.0-rc3's headers come to, and put
  v4.5.0's in the spec with its other sizes.
- Real releases sit far under these. v4.5.0's archive is 172 MiB, its tar stream
  201 MiB, and it has 5,680 entries. v4.5.0-rc3's are about the same. Measure
  them again on a fresh download, and correct the spec's numbers if they differ.
- Past any limit, nothing is unpacked into the cache. The scratch folder goes
  away as it already does, and no folder for the tag is left, so nothing passes
  for a cached release. The run stops with exit 2, and one line says the release
  is too large to read, and which limit it passed. `--json` gives a `failed`
  document with that reason and `unreachable: false`. `--ack` and `--unack` stop
  the same way and write nothing.
- The file system filling up anyway, as on a nearly full disk, is already a
  failed download. Check that it gives exit 2 and leaves no half release, and
  add a test if nothing holds that.
- The plugin needs no change: a `failed` document shows as "couldn't check" with
  its reason. Check that it does, with a document from a run that passed a
  limit.
- Tests serve crafted archives the way the download tests already do: one over
  each limit, a gzip bomb (a small archive whose stream passes 2 GiB) and a
  sparse member that states more than 2 GiB. Each test fails without the fix.
  They stay small and fast: lower the limits in the test rather than writing
  gigabytes.
- Release 0.3.7 as 045 did: version, changelog, README's clone, tag, GitHub
  release, CI watched. The tag is the commit at the top of `main` on GitHub, and
  stays there. Commits after the tag, such as ticking this ticket's boxes, stay
  local until 14152 is verified. The hold note and 039's boxes name 0.3.7.
- The update request: edit 14152's "Target commit" to 0.3.7's full SHA, which is
  what reruns the marketplace's checks, and reply once. The reply names the
  finding, the three limits, what happens past each, and the tests that show it.
  It says one run downloads at a time, under the cache's lock, and a prune keeps
  two releases, so what a crafted release can take is bounded too. It asks whether anything else
  blocks approval. Numbers are no more than the tests and measurements show. The
  owner confirms the edit and the reply before either is sent.

## Not in this ticket

- Remembering a release that was too large, so the next check doesn't download
  it again. In the backlog.
- A deadline on a download that keeps trickling. Already in the backlog under
  "A check that never ends".
- Checking free space before a download. The limits bound what a run can take,
  whatever the disk holds.

## Done when

- [x] A download past 1 GiB stops while it is read, with exit 2 and a `failed`
      document that names the limit.
- [x] An archive whose stream or whose members' stated sizes pass 2 GiB, or
      that holds more than 100,000 members, is not unpacked, and gives the same.
- [x] No folder for the tag is left after any of these, and the scratch folder
      is gone.
- [x] A file system that fills up mid-unpack gives exit 2 and leaves no half
      release.
- [ ] An archive whose headers pass 16 MiB in all is not unpacked, and gives
      the same, and the run's memory stays near 16 MiB above what it uses
      without them: tested with one long PAX record, one long GNU name, and many
      headers that each fit.
- [x] The spec gives v4.5.0's header total with its other sizes.
- [x] `--ack` and `--unack` past a limit write nothing.
- [x] The plugin shows such a document as "couldn't check" with the reason.
- [x] Each test past a limit fails without the fix. The ones at a limit, and
      the full-disk ones, hold what already worked.
- [x] Real runs on v4.5.0 and v4.5.0-rc3, downloaded fresh, give the same
      results as before, and the spec's sizes match what was measured.
- [ ] `v0.3.7` and its GitHub release exist on the commit at the top of `main`
      on GitHub, and CI passed on it.
- [ ] The owner confirmed the edit and the reply, 14152 targets 0.3.7's SHA, and
      the marketplace's checks ran on it.
- [x] `tests/run` passes.
