# Contributing

Bug reports help the most, above all a finding that was wrong or one that was
missed. The bug report form says what to include.

For a larger change, open an issue first. [SPEC.md](SPEC.md) is the source of truth,
and its [Rejected](SPEC.md#rejected) section lists paths already ruled out. A change
of behaviour changes the spec in the same commit.

## Rules that outrank everything

These come from [What must never happen](SPEC.md#what-must-never-happen):

- A check that didn't run is never shown as clear. When unsure, report `unknown`.
- Nothing from a release is ever run. Its files are only read as text.
- Nothing changes outside the tool's own cache, unless the user asked for an
  optional install step.
- Nothing leaves the machine except GET requests to GitHub.
- Every finding can name the line or file behind it.

## Working on it

Run the tests before you send a change:

```
tests/run
```

That runs the tests, then `shellcheck` and `ruff` if you have them. CI runs them all.

- Python standard library only, no dependencies. `qmllint` stays optional.
- Tests are `unittest`. Each bug fix gets a test that fails without it.
- Omarchy's formats change, so check real release files, not memory. A release can be
  read from `~/.cache/omaupdateimpact/<tag>`.
- Docs use plain, short sentences.

The report at the top of the README and the recording in `docs/demo.svg` are the
command's own output, and a test holds them to it. After a change to the report, run
this and copy the new report into the README:

```
python3 -m tests.demo
```

## Keep it fictional

Fixtures, docs and demos use made-up paths, hostnames and config. Your own stay out
of the repository, and out of issues too. Unchanged Omarchy release files are the
exception, kept with Omarchy's license and their source tag.
