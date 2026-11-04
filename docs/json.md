# JSON output

`omaupdateimpact --json` prints one JSON document on stdout, and nothing else. It is
for scripts and for the bar plugin. Progress and errors still go to stderr, and the
exit codes are the same as for the report.

The document carries what the report works out, so a reader needs no rules of its
own. `--all` changes nothing: every finding is always there. `--help` and
`--version` print text, as usual.

`schemaVersion` is `1`. A breaking change bumps it. A new key is not a breaking
change, so ignore keys you don't know.

## Every document

| Key | Value |
| --- | --- |
| `schemaVersion` | The version of this schema, a number. |
| `result` | What the run came to. It says which other keys are there. |

| `result` | Exit | Meaning |
| --- | --- | --- |
| `clear` | 0 | Every check ran and nothing needs attention. |
| `noUpdate` | 0 | The release is already installed. Nothing was compared. |
| `attention` | 1 | Something needs attention, that you haven't reviewed. |
| `failed` | 2 | No verdict: bad usage, a failed download, an unusable tree or a crash. |
| `incomplete` | 3 | Nothing needs attention, but at least one check couldn't run in full. |

`attention` can come with checks that didn't run in full. Their states say so.

## A report

`clear`, `attention` and `incomplete` are reports.

| Key | Value |
| --- | --- |
| `installed` | The installed version, as `omarchy-version` prints it, or `unknown`. |
| `channel` | The update channel, or `unknown`. |
| `target` | The release compared with: `name`, `prerelease` and `path`. |
| `checks` | Each check, with its `state` and what it `checked`. |
| `findings` | Every finding, check by check. The report groups them by level. |

`target.name` is the tag. With `--target` and no tag, it is the folder's name.
`target.prerelease` is `true`, `false` or `null` when the name isn't a tag.
`target.path` is the unpacked release the command read, as an absolute path, so a
reader can open its files. Its notes are there too, as `.omaupdateimpact-notes.md`.

### Checks

`checks` has the same five keys every time: `bindings`, `packages`, `commands`,
`plugins` and `edits`.

| `state` | Meaning |
| --- | --- |
| `ran` | The check ran in full. |
| `ranInPart` | It still compared something, around what it couldn't read. |
| `didNotRun` | It compared nothing. |

`checked` holds counts of what was really looked at. A count is `null` when that
wasn't looked at, so it can never read as zero.

| Check | Count | What it counts |
| --- | --- | --- |
| `bindings` | `defaults` | The release's default bindings. |
| `bindings` | `yours` | Your bindings. `null` when your file can't be read. |
| `packages` | `pendingMigrations` | Migrations you haven't run, that could be read. |
| `commands` | `deletedCommands` | `omarchy-*` commands the release deletes. |
| `commands` | `yourFiles` | Your files read for them. `0` when nothing is deleted. |
| `plugins` | `linted` | Plugins linted. `0` when there are no plugins. |
| `edits` | `pendingMigrations` | Migrations you haven't run, read for the files they write. |

### Findings

Each finding has every field below, even an empty one.

| Field | Value |
| --- | --- |
| `id` | Seven hex digits. It stays the same while what the finding says does. |
| `check` | Which check found it. |
| `level` | `attention`, `note` or `unknown`. |
| `title` | What was found. A note's is one short line. |
| `evidence` | The files or lines behind it. Never empty. |
| `detail` | More about it, or `""`. |
| `fix` | What to do, or `""`. Every `attention` finding has one. |
| `partial` | On an `unknown`, `true` when the rest of its check still stood. |
| `reason` | The change in the release notes it comes from, or `null`. |
| `reviewed` | `true` when you marked it with `--ack` for this release, and `--unack` hasn't taken it back. Only `attention` can be. |

Two fields are there only on the findings they fit.

| Field | Value |
| --- | --- |
| `group` | On every note, a short heading for its kind, such as `Shortcuts that move`. Other levels have none. |
| `items` | On a finding that lists things, one string per thing, such as `SUPER + M: Minimize window to the dock`. Its title says how many. |

The report shows `title` and `detail` together, then the `reason`, then the `fix`.
With `--all` it lists the notes under their `group` headings, each title on a line
of its own and its detail under it. A finding's `items` are printed one per line
under its title.

The command names the groups, in the order they first come, so a reader needs no
rules to sort the notes:

| `group` | What its notes are |
| --- | --- |
| `Your bindings` | Your unbinds and bindings that now meet another default. |
| `Shortcuts that move` | A default that moves to another key, such as `Calculator: SUPER + CTRL + Q -> SUPER + SHIFT + Q`. |
| `Shortcuts that change` | A key whose default does something else, such as `SUPER + ALT + SPACE: "Apps menu" -> "Apps"`. |
| `New default shortcuts` | The new defaults, as `items`. |
| `Default shortcuts removed` | The defaults that go, as `items`. |
| `Computed keys` | Keys worked out when Lua runs, the same in both versions. |
| `Deleted commands in Omarchy's own files` | Omarchy's own files, unchanged, that call a deleted command. |
| `Plugins` | New `qmllint` warnings, and what `qmllint` can't prove. |
| `Files a migration may edit` | Your files that a pending migration looks like it writes. |

A new group isn't a breaking change. Put a note in a group you don't know under a
heading of your own.

A reviewed finding doesn't count for `result`, so `attention` means one that isn't
reviewed. The report counts reviewed findings at the end, and `--all` lists them.

A `reason` is there only when one change in the notes clearly names what the finding
is about. Otherwise it is `null`, and so it is when the notes couldn't be fetched.

| Field | Value |
| --- | --- |
| `text` | The change, as the notes list it, without who made it. |
| `reference` | Where it was made, such as `#14426` or `omacom/omarchy-iso#310`. |
| `evidence` | The line in the notes, such as `.omaupdateimpact-notes.md:328`. |

Evidence in your home starts with `~`, and a line is `path:line`. Other paths are
inside an Omarchy tree, such as `migrations/1700000001.sh`. The notes are kept in the
release's tree, as `.omaupdateimpact-notes.md`. A name that isn't
UTF-8 is escaped as `\udcXX`, as JSON allows.

This report is from small fictional trees:

```json
{
  "schemaVersion": 1,
  "result": "attention",
  "installed": "1.2.3-1",
  "channel": "stable",
  "target": {
    "name": "v1.3.0",
    "prerelease": false,
    "path": "/fictional/v1.3.0"
  },
  "checks": {
    "bindings": {
      "state": "ran",
      "checked": {
        "defaults": 3,
        "yours": 1
      }
    },
    "packages": {
      "state": "ranInPart",
      "checked": {
        "pendingMigrations": 2
      }
    },
    "commands": {
      "state": "ran",
      "checked": {
        "deletedCommands": 1,
        "yourFiles": 2
      }
    },
    "plugins": {
      "state": "ran",
      "checked": {
        "linted": 0
      }
    },
    "edits": {
      "state": "ran",
      "checked": {
        "pendingMigrations": 3
      }
    }
  },
  "findings": [
    {
      "id": "9d67629",
      "check": "bindings",
      "level": "attention",
      "title": "SUPER + M: your \"Music\" will clash with the new default \"Minimize window\".",
      "evidence": [
        "default/hypr/bindings.lua",
        "~/.config/hypr/bindings.lua"
      ],
      "detail": "Both will fire.",
      "fix": "Add hl.unbind(\"SUPER + M\") above your binding, or choose another key.",
      "partial": false,
      "reason": null,
      "reviewed": false
    },
    {
      "id": "61e5cbb",
      "check": "bindings",
      "level": "note",
      "group": "New default shortcuts",
      "title": "1 new default shortcut.",
      "evidence": [
        "default/hypr/bindings.lua"
      ],
      "detail": "",
      "items": [
        "SUPER + N: Notifications"
      ],
      "fix": "",
      "partial": false,
      "reason": null,
      "reviewed": false
    },
    {
      "id": "1354b03",
      "check": "packages",
      "level": "attention",
      "title": "The update will remove fictional-editor, which is installed here.",
      "evidence": [
        "migrations/1700000001.sh"
      ],
      "detail": "",
      "fix": "After the update, run omarchy pkg add fictional-editor (aur-add for an AUR package).",
      "partial": false,
      "reason": {
        "text": "Replace Fictional Editor with Fictional Writer",
        "reference": "#101",
        "evidence": ".omaupdateimpact-notes.md:3"
      },
      "reviewed": false
    },
    {
      "id": "e1c345b",
      "check": "packages",
      "level": "unknown",
      "title": "Couldn't read what migrations/1700000002.sh removes, so check it by hand.",
      "evidence": [
        "migrations/1700000002.sh"
      ],
      "detail": "",
      "fix": "",
      "partial": true,
      "reason": null,
      "reviewed": false
    },
    {
      "id": "b2c1f5a",
      "check": "commands",
      "level": "attention",
      "title": "~/.local/bin/sync-all calls omarchy-sync-notes, which the release deletes.",
      "evidence": [
        "~/.local/bin/sync-all:2"
      ],
      "detail": "",
      "fix": "Change or remove line 2. This tool can't tell what replaces the command.",
      "partial": false,
      "reason": null,
      "reviewed": false
    },
    {
      "id": "16c9791",
      "check": "edits",
      "level": "note",
      "group": "Files a migration may edit",
      "title": "migrations/1700000003.sh may edit ~/.config/fictional-app/theme.conf",
      "evidence": [
        "migrations/1700000003.sh:1",
        "~/.config/fictional-app/theme.conf"
      ],
      "detail": "It looks like it edits the file on line 1. Omarchy has no default for it. It is read, not run, so the result isn't known. omaforecast can show it by running the migration in a sandbox.",
      "fix": "",
      "partial": false,
      "reason": null,
      "reviewed": false
    }
  ]
}
```

## No update

`noUpdate` has `installed`, `channel` and `target`, as a report does, and no checks
or findings.

| Key | Value |
| --- | --- |
| `newer` | Newer releases on other channels, each with its `tag`, `channel` and `cached`. `[]` when there are none. |
| `newerProblem` | Why `newer` is `null`, or `null`. |

`newer` is `null` when the list of releases couldn't be fetched. That still exits 0,
as there is no update.

`cached` is `true` when the release is already in the cache, so checking it would
download nothing. A cache that can't be read counts as `false`.

```json
{
  "schemaVersion": 1,
  "result": "noUpdate",
  "installed": "1.3.0-1",
  "channel": "stable",
  "target": {
    "name": "v1.3.0",
    "prerelease": false
  },
  "newer": [
    {
      "tag": "v1.4.0-rc1",
      "channel": "rc",
      "cached": false
    }
  ],
  "newerProblem": null
}
```

## A failure

`failed` has only `reason`: the line printed on stderr. Bad usage starts with
`Bad usage:`.

```json
{
  "schemaVersion": 1,
  "result": "failed",
  "reason": "Can't pick a release: the channel is edge, and only stable and rc have tagged releases. Pass a tag, such as omaupdateimpact v4.5.0."
}
```
