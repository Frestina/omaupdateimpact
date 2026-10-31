# Working in this repo

omaupdateimpact is a read-only check that tells you what an Omarchy release would
do to your machine, before you update. [SPEC.md](SPEC.md) is the source of truth:
read the sections a ticket links before changing anything, and change the spec in
the same commit when a decision changes.

## Picking up work

1. Open [tickets/README.md](tickets/README.md). Status lives only in its tables.
2. Take the lowest-numbered ticket marked `todo` whose dependencies are all
   `done`, unless the user names one.
3. Set it to `in progress` in the table, read the ticket and the spec sections it
   links, and do only what its scope says.
4. A ticket is done when every box under "Done when" is ticked and `tests/run`
   passes. Tick the boxes in the ticket file and set the table to `done`.
5. Commit with the ticket number first: `006: read o.bind_hold`.

Something the ticket didn't foresee goes to
[tickets/BACKLOG.md](tickets/BACKLOG.md) or becomes a new ticket, not into the
current one.

## Rules that outrank everything

These come from [What must never happen](SPEC.md#what-must-never-happen):

- A check that didn't run is never shown as clear. When unsure, report `unknown`.
- Nothing from a release is ever run. Its files are only read as text.
- Nothing changes outside the tool's own cache, unless the user asked for an
  optional install step.
- Nothing leaves the machine except GET requests to GitHub.
- Every finding can name the line or file behind it.

## Conventions

- Python standard library only, no dependencies. `qmllint` stays optional.
- Tests are `unittest`, run by `tests/run`. Each bug fix gets a test that fails
  without it.
- Omarchy's formats change, so check real release files, not memory. A release can
  be read from `~/.cache/omaupdateimpact/<tag>`.
- Fixtures, docs and demos are fictional: no real paths, hostnames, personal config
  or private project names. This repo goes public at 0.1.0.
- Docs use plain, short sentences.
- The command keeps the project's name, `omaupdateimpact`.
