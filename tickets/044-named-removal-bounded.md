---
id: "044"
title: NAMES_REMOVAL costs no more than the words it reads
milestone: M4 Plugin
depends_on: ["042", "043"]
---

# 044 NAMES_REMOVAL costs no more than the words it reads

## Goal

The maintainer's fourth finding on
[14152](https://github.com/omacom/omarchy-plugin-marketplace/issues/14152), at
0.3.4 (`53b607d`): 043 fixed the copies of the rest of a command, but each word
is still read with one unbounded `NAMES_REMOVAL.search(word)`
(`bin/omaupdateimpact:145–148,1137`). The third branch of the regex,
`\b(?:pacman|yay|paru)\b.*[\s\"'](?:-[a-zA-Z]*R|--remove)`, backtracks the
greedy `.*` over the rest of the word for every name that matches the
`\bpacman\b`-shaped part. One quoted argument of 35,000 `pacman`-named words
separated by spaces — about 245 KB, below the file limit, with no removal
option — pays that suffix scan once per name: the square, in one regex call.
Measured here, 1,000 names took 0.10 s, 2,000 took 0.43 s and 4,000 took
1.73 s, so each doubling of names quadruples the time; 35,000 extrapolates to
about 2 minutes. The writer of a release can put such a word in a migration's
string, and the plugin's check runs it with no deadline of its own
(`plugin/Service.qml` supplies none — a limit the backlog already holds).

The same regex runs once over a whole file that isn't a shell script
(`bin/omaupdateimpact:1265`), where the file is the word: a 256 KiB file of
`pacman` names with no flag costs the same backtracking in one call, so both
call sites need the bound.

## Spec

- [Reading migrations](../SPEC.md#reading-migrations)
- [What must never happen](../SPEC.md#what-must-never-happen)

## Scope

- `NAMES_REMOVAL`'s answer is the same for every word and every file it read
  before, and the work of one search is no more than the length of what it
  searches: no scan of a suffix per candidate. What the search says may not
  change: a word still turns "unread" when its text names a removal behind a
  shell string, and a file that isn't a script is still `unread` exactly when
  its text names one.
- Timing test gains the shape: one long command of one `bash -c` word holding
  thousands of `pacman` names and no flag, and the non-shell-script file of
  names, each at the size limit.
- The old and new readers agree on every real script, as 040, 042 and 043 agreed.
- Release 0.3.5 as in 042 and 043: version, changelog, README's clone, tag,
  GitHub release, push with the hold note naming it, CI watched, and the reply
  on 14152 says what changed, with numbers no more than the tests show, and
  names 0.3.5's SHA. The owner confirms the reply first.

## Not in this ticket

- A deadline on the plugin's check. Backlog, since 042: it waits for the
  marketplace asking again or a real report.

## Done when

- [ ] One command whose one `bash -c` word holds 35,000 `pacman` names, within
      the size limit, reads in seconds.
- [ ] The timing test covers the long word and the non-shell-script file of names.
- [ ] The old and new readers agree on every real script.
- [ ] `v0.3.5` and its GitHub release exist on the commit pushed to `main`, and
      CI passed on it.
- [ ] 14152 names 0.3.5's SHA, and the finding is answered there.
- [ ] `tests/run` passes.
