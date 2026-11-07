---
id: "043"
title: A long command costs no more than its length
milestone: M4 Plugin
depends_on: ["042"]
---

# 043 A long command costs no more than its length

## Goal

The maintainer's third finding on
[14152](https://github.com/omacom/omarchy-plugin-marketplace/issues/14152), at
0.3.3 (`ddd2279`): `package_action()` copies the rest of the command for every
word, and for each `bash`, `sh`, `eval` or `pacman` it scans that rest again. One
command of N such words costs N². 10,000 `bash` words take 12 s, and the
maintainer's 250 KB of 50,000 take about 5 minutes. 042's timed shapes had no
single long command, so the reply's "each now grows in step with its input" was
wrong for this reader.

## Spec

- [Reading migrations](../SPEC.md#reading-migrations)
- [What must never happen](../SPEC.md#what-must-never-happen)

## Scope

- `package_action()` reads a command in one pass: no copy of the rest per word,
  and the shell-string and `pacman` checks found once per command, not once per
  word.
- Measured on one line of 5,000 words, the slow ones were `bash -c` (5.1 s),
  `sh` (3.1 s), `eval` (1.1 s) and `omarchy pkg` (0.5 s). Time each at the size
  limit, with `bash` and `pacman`, and look again at anything else that scans per
  word.
- The timing test gains one long command of each of these words.
- The old and new readers agree on every real script, as in 040 and 042.
- Release 0.3.4 as in 042. The reply on 14152 says what changed, and corrects
  0.3.3's claim. The owner confirms the reply first.

## Done when

- [ ] One command of 50,000 `bash` words, at the size limit, reads in seconds.
- [ ] The timing test covers a long command of each word above.
- [ ] The old and new readers agree on every real script.
- [ ] `v0.3.4` and its GitHub release exist on the commit pushed to `main`, and CI
      passed on it.
- [ ] 14152 names 0.3.4's SHA, and the finding is answered there.
- [ ] `tests/run` passes.
