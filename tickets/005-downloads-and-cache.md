---
id: "005"
title: Downloads and the cache
milestone: M1 Trust
depends_on: ["002"]
---

# 005 Downloads and the cache

## Goal

Make downloading dull. One release takes 208 MB in the cache and nothing ever
removes it, so an RC cycle fills the disk quietly.

## Spec

- [Files](../SPEC.md#files)

## Scope

- Accept only tags shaped like `v1.2.3` or `v1.2.3-rc1`. `../../x` is a cache path
  today, though GitHub's 404 happens to stop it.
- After a successful download, keep the two newest cached releases and remove the
  rest.
- Treat an empty `XDG_CACHE_HOME` as unset, as the XDG spec says.
- Say when the API rate limit is the reason for a failure, and use `GITHUB_TOKEN`
  when it's set.
- Say that it's downloading, and how large, on a terminal. A first run looks hung
  today.

## Done when

- [x] A bad tag exits 2 without touching the network or cache, with a test.
- [x] A third release prunes the oldest, with a test.
- [x] Empty `XDG_CACHE_HOME` uses `~/.cache`, with a test.
- [x] A 403 with a rate-limit header gives its own message, with a test.
- [x] `tests/run` passes.
