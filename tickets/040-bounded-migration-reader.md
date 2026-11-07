---
id: "040"
title: The migration reader's work is bounded
milestone: M4 Plugin
depends_on: ["038"]
---

# 040 The migration reader's work is bounded

## Goal

Reading a release never costs more than a few seconds, whatever its scripts hold.
The marketplace's review of 0.3.1
([issue 14152](https://github.com/omacom/omarchy-plugin-marketplace/issues/14152))
found that `braces()` spells out every `{a,b}` list before the 64-result limit is
checked. 30 lists in one word of a pending migration are 2^30 strings, so a
crafted release, or a tree passed to `--target`, can exhaust the CPU and memory of
the command, and of the plugin's service that runs it, just by being read. It has
been there since 017.

## Spec

- [Reading what migrations write](../SPEC.md#reading-what-migrations-write)
- [Reading migrations](../SPEC.md#reading-migrations)
- [What must never happen](../SPEC.md#what-must-never-happen)

## Scope

- `braces()` stops as soon as a word would spell out more than 64, and the word is
  only known when it runs, as too many values already are. It counts a list's items
  before it builds them, and finds each `{`'s match in one pass, not one scan per
  `{`.
- The same check, timed on crafted migrations of growing size, found more work
  that grows faster than the script. Each is bounded the same way:
  - A variable or a function's argument holds at most 64 values. Past that it also
    holds a value only known when it runs. Before, a variable set N times and used
    N times cost N².
  - A value longer than 4096 characters, the longest path Linux takes, is only
    known when it runs. Before, `v2=$v1/a` and its like, line after line, built
    values whose total length grew as the square of the script.
  - A release script over 256 KiB isn't read: what it writes or removes is
    `unknown`. Omarchy's largest migration is 13 KiB, in v4.5.0.
  - A script nested too deep to read, such as `${x:-` 500 times, is `unknown`, as one
    the reader loses its place in. Before, it stopped the command with a
    `RecursionError`.
- A test for each, and one that times every crafted shape at the size limit.
- Release 0.3.2 with the `omarchy-plugin-release` skill: version, changelog, the
  README's clone, tag, GitHub release, push and CI, as in 039.
- Edit 14152's target commit to 0.3.2's SHA, which runs the checks again, and
  answer the finding there. The owner confirms the edited request first.
  The owner moved this to 042, which releases 0.3.3 with the follow-ups below.
- Review follow-ups: the values a script holds are bounded one by one, but not in
  total. 19,000 variables, each 64 values just under 4096 characters, fit in
  256 KiB and take about 5 GB. Past a budget for the whole script, it is
  `unknown`. The timing test also measures memory. The spec drops the line on
  what the review found, as the spec holds no history.

## Not in this ticket

- Anything else the review of 14152 raises. It goes to a new ticket.

## Done when

- [x] A word of 30 `{a,b}` lists reads at once, as only known when it runs.
- [x] Every crafted shape, at the size limit, reads in seconds, and a test times
      them.
- [x] A script over the size limit, or nested too deep, is `unknown`.
- [x] The spec says each limit.
- [x] `v0.3.2` and its GitHub release exist on the commit pushed to `main`, and CI
      passed on it.
- [x] A script whose values would hold more than the budget in total is `unknown`,
      and the 19,000-variable shape reads in seconds and well under 100 MB.
- [x] The timing test measures peak memory for every shape too.
- [x] The spec's 64-values bullet says the limit, not what the review found.
- [x] `tests/run` passes.
