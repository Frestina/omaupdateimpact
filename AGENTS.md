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
5. Commit with the ticket number first: `006: read o.bind_hold`. Tickets are
   committed directly on main, with no branches.
6. Hand it to the reviewer, as below, and wait for its verdict.

Something the ticket didn't foresee goes to
[tickets/BACKLOG.md](tickets/BACKLOG.md) or becomes a new ticket, not into the
current one.

## Handing a ticket to the reviewer

A reviewer session (started with `/reviewer`) reviews every ticket. You and it
work the ticket back and forth until it is ready, without the user relaying
messages.

1. Find it: `.claude/reviewer-session` holds its session name. Check that name is
   listed by `ListAgents`. If the file is missing or the session is not listed,
   tell the user to start one with `/reviewer`, then stop.
2. Send it one message with `SendMessage`. First line: `<ticket> done: <commit>`.
   Then what you built, decisions the ticket did not settle and where the spec
   now records them, test results (and any step skipped), and anything you put in
   the backlog.
3. Wait for its answer. It is one of:
   - **Ready.** The ticket is finished. Stop; do not start another ticket.
   - **Findings.** Fix them and commit as `<ticket>: review follow-ups`. The
     reviewer's edits to the ticket and spec are uncommitted in the tree: commit
     them with yours, unchanged. Tick the new boxes, set the table to `done`, and
     message the reviewer again as in step 2.
   - **Waiting for the user.** A finding needs the user's decision. Wait for the
     reviewer's next message.
4. If you disagree with a finding, say why in your message instead of changing
   the code. The reviewer decides, or asks the user.

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
  or private project names. This repo goes public at 0.1.0. Unchanged Omarchy
  release files are the exception, kept with Omarchy's license and their source tag.
- Docs use plain, short sentences.
- The command keeps the project's name, `omaupdateimpact`.
