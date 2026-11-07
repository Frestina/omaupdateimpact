# Tickets

The work to release omaupdateimpact, one file per ticket. [SPEC.md](../SPEC.md)
is the source of truth; each ticket links the sections it builds. Things left for
later are in [BACKLOG.md](BACKLOG.md).

## How this works

- **Status lives only in the tables below.** Ticket files hold no status, so the
  two can never disagree.
- **Next ticket:** the lowest-numbered `todo` whose dependencies are all `done`.
- **Starting:** set it to `in progress`. **Finishing:** every box under "Done
  when" ticked, `tests/run` passes, set it to `done`.
- **Commits** start with the ticket number: `006: read o.bind_hold`.
- **Statuses:** `todo`, `in progress`, `done`, `blocked`.
- New work found along the way goes to the backlog or a new ticket, never into
  the current one.
- **Nothing is pushed while an update is in review.** `omarchy plugin add` clones
  `main` as it is, so a push reaches users before the marketplace verifies it, and
  moves `main` off the SHA in review. 039's update request
  ([issue 14152](https://github.com/omacom/omarchy-plugin-marketplace/issues/14152))
  asks for the commit tagged `v0.3.2`, which the issue names in full. Commits wait
  on `main` here until it is verified.
- **Fixtures are fictional.** No real paths, hostnames or personal config in the
  tests, the docs or the demo. The exception is unchanged Omarchy release files,
  kept with Omarchy's license and their source tag.

Every ticket has the same parts: front matter (`id`, `title`, `milestone`,
`depends_on`), then Goal, Spec, Scope, sometimes Not in this ticket, and Done
when.

## Milestones and status

### M1 Trust: every answer is right, or says it doesn't know

| # | Ticket | Depends on | Status |
| --- | --- | --- | --- |
| 001 | [Name and project identity](001-name-and-identity.md) | | done |
| 002 | [Typed findings and exit codes](002-findings-and-exit-codes.md) | 001 | done |
| 003 | [Refuse unusable trees](003-refuse-unusable-trees.md) | 002 | done |
| 004 | [Follow the update channel](004-follow-the-channel.md) | 003 | done |
| 005 | [Downloads and the cache](005-downloads-and-cache.md) | 002 | done |
| 006 | [Read every binding helper](006-binding-helpers.md) | 002 | done |
| 007 | [Read every package removal](007-package-removals.md) | 002 | done |
| 008 | [Find every call to a deleted command](008-command-coverage.md) | 002 | done |
| 009 | [Failed lints are unknown](009-plugin-lint-failures.md) | 002 | done |
| 010 | [Tests against real releases](010-real-release-tests.md) | 003, 006, 007, 008, 009 | done |
| 011 | [CI and the drift watch](011-ci-and-drift-watch.md) | 010 | done |

### M2 First release: someone else can install and trust it

| # | Ticket | Depends on | Status |
| --- | --- | --- | --- |
| 012 | [A report worth reading](012-report-polish.md) | 010 | done |
| 013 | [Install, version and uninstall](013-install-and-version.md) | 001 | done |
| 014 | [README and project docs](014-readme-and-docs.md) | 012, 013 | done |
| 024 | [Only a Qt 6 `qmllint` counts](024-qt6-qmllint.md) | 009 | done |
| 015 | [Release 0.1.0](015-release-0-1-0.md) | 011, 014, 024 | done |

### M3 Better answers

| # | Ticket | Depends on | Status |
| --- | --- | --- | --- |
| 016 | [JSON output](016-json-output.md) | 002 | done |
| 017 | [Migrations that touch files you changed](017-migrations-touching-your-files.md) | 002 | done |
| 018 | [Say why, from the release notes](018-reasons-from-release-notes.md) | 002 | done |
| 019 | [Reviewed findings stay quiet](019-reviewed-findings.md) | 002 | done |
| 020 | [An entry in the Omarchy menu](020-omarchy-menu-entry.md) | 015 | done |
| 025 | [The install tests don't use the developer's PATH](025-install-tests-own-path.md) | 013 | done |
| 026 | [Follow function arguments into migration writes](026-function-arguments-in-writes.md) | 017 | done |

### M4 Plugin: on the desktop and in the marketplace

| # | Ticket | Depends on | Status |
| --- | --- | --- | --- |
| 021 | [Plugin design](021-plugin-design.md) | 016 | done |
| 028 | [The command leaves its own files out](028-skip-own-files.md) | 021 | done |
| 022 | [Bar widget and panel](022-plugin-panel.md) | 021, 028 | done |
| 027 | [Two runs share the cache](027-two-runs-share-the-cache.md) | 005 | done |
| 029 | [Check a newer release, and choose how often, from the panel](029-panel-release-and-interval.md) | 022 | done |
| 023 | [Marketplace listing](023-marketplace-listing.md) | 015, 022, 027, 029 | done |
| 030 | [Mark reviewed, and ask your agent, from the panel](030-panel-review-and-agent.md) | 023 | done |
| 031 | [Record the demo video](031-demo-video.md) | 023 | done |
| 032 | [A newer release's report in the panel](032-chosen-release-in-panel.md) | 030 | done |
| 033 | [Panel polish after the owner's first use](033-panel-polish.md) | 032 | done |
| 034 | [Undo a review, short notes, and ask what replaces it](034-undo-items-and-replacements.md) | 033 | done |
| 035 | [Notes in groups, and arrows that show](035-panel-groups-and-arrows.md) | 034 | done |
| 036 | [Check soon after loading, and wait for the network](036-first-check-sooner.md) | 035 | done |
| 037 | [Lint and check against v4.5.0](037-lint-against-v4-5-0.md) | 011 | done |
| 038 | [The bar's mark is the icon's label](038-bar-mark-as-label.md) | 037 | done |
| 039 | [Release 0.3.0 and update the listing](039-release-0-3-0.md) | 023, 038, 040, 041, 042 | in progress |
| 040 | [The migration reader's work is bounded](040-bounded-migration-reader.md) | 038 | in progress |
| 041 | [A $(...) with no command doesn't stop the run](041-empty-command-substitution.md) | 040 | done |
| 042 | [Every reader of release text is bounded](042-bounded-release-reading.md) | 040 | todo |
