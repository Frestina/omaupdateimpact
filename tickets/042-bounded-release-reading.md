---
id: "042"
title: Every reader of release text is bounded
milestone: M4 Plugin
depends_on: ["040"]
---

# 042 Every reader of release text is bounded

## Goal

040 bounded the migration reader, but the spec and the README now say that
reading a release costs little more than its size. That isn't true yet. The
bindings reader is slower than quadratic: `hl.bind(` repeated with no `)`, in a
Lua file under `default/hypr`, takes 4.5 s at 16 KB, 17 s at 32 KB and 67 s at
64 KB. Each call's `call_arguments()` scans to the end of the file. A 256 KiB file
would take about 18 minutes, in the command and in the plugin's scheduled check.
This is the same kind of issue as 14152's finding, so it ships in the same release,
and 14152 moves once.

The maintainer found it too, on 0.3.2: their second comment on 14152 (2026-11-07,
"rescans the entire remaining Lua text for every unterminated binding call") times
50,000 open `hl.bind(` calls in 400 KB at about 10^10 steps. The same comment says
the brace finding is fixed. The maintainer moves the request's target commit
themselves: they moved it to 0.3.2's SHA three minutes after its tag.

## Spec

- [Reading release formats](../SPEC.md#reading-release-formats)
- [Reading migrations](../SPEC.md#reading-migrations)
- [Reasons](../SPEC.md#reasons)
- [What must never happen](../SPEC.md#what-must-never-happen)

## Scope

- Time every reader of a release's text on crafted input of growing size, as 040
  did: the Lua defaults (`parse_lua`, `call_arguments`, `blank_comments`,
  `parse_helpers`), a migration's first line (`description`), and the notes
  (`read_notes`, `give_reasons`). Bound each one that grows faster than its input
  or reads without limit.
- The migration reader's `${x#pattern}` and its like: 040's budget counts the
  values a cut keeps, not the `fnmatch` it runs for every place it could cut. So
  4,000 lines of `y=${x##*a*b}`, where `x` holds 64 values of 4,000 characters,
  take about 20 s (56 KB) before the budget makes the migration `unknown`. That
  work counts too, so the shape reads in seconds.
- `hl.bind(` with no `)` costs no more than its length. A call the reader can't
  read in full counts as a computed key, never as no binding, so it stays a note
  or `unknown` by the existing rules.
- A limit that makes a reader stop is `unknown`, or exit 2 where the rules already
  say so, such as no readable default bindings. It is never clear. The spec says
  each limit.
- A test for each, and one that times every crafted shape, and measures its peak
  memory, at the size limit.
- On every real Lua file and notes in v4.5.0, v4.5.0-rc3 and the installed tree,
  the old and new readers give the same answer.
- Release 0.3.3, with 040's review follow-ups and this, using the
  `omarchy-plugin-release` skill: version, changelog, the README's clone, tag,
  GitHub release, push and CI, as in 039.
- Make sure 14152's target commit is 0.3.3's SHA (edit it if the maintainer
  hasn't), and answer both findings there. The reply says what 0.3.2 and 0.3.3
  each bounded, and claims no more than the timing tests show. The owner confirms
  the edited request and the reply first.
- Review follow-ups: the timing test fails on a slower machine. On a 2-core
  laptop, "a chain of functions" passes its 60 s limit under `tracemalloc`, so CI
  could fail on 0.3.3's tag, as it did on 0.3.0's. Time each shape without
  `tracemalloc`, and measure its memory in a pass of its own. The spec's link for
  a call that can't be read goes to the computed-key rules, not to Reasons.
  Release only after this is ready.

## Not in this ticket

- `qmllint` on the release's shell. It already stops after 60 seconds per plugin.
- Anything else the review of 14152 raises. It goes to a new ticket.

## Done when

- [x] `hl.bind(` repeated with no `)`, at the size limit, reads in seconds.
- [x] Every crafted shape for every release reader, at the size limit, reads in
      seconds and with bounded memory, and a test measures both.
- [x] The old and new readers agree on every real Lua file and notes.
- [x] The spec says each new limit, and its line on what reading a release costs
      is true.
- [x] The timing test measures time without `tracemalloc`, and passes on the
      2-core laptop as well as here.
- [x] The spec's link for a call that can't be read goes to the computed-key rules.
- [ ] `v0.3.3` and its GitHub release exist on the commit pushed to `main`, and CI
      passed on it.
- [ ] 14152 names 0.3.3's SHA, and the finding is answered there.
- [x] `tests/run` passes.
