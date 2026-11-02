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
| `attention` | 1 | Something needs attention. |
| `failed` | 2 | No verdict: bad usage, a failed download, an unusable tree or a crash. |
| `incomplete` | 3 | Nothing needs attention, but at least one check couldn't run in full. |

`attention` can come with checks that didn't run in full. Their states say so.

## A report

`clear`, `attention` and `incomplete` are reports.

| Key | Value |
| --- | --- |
| `installed` | The installed version, as `omarchy-version` prints it, or `unknown`. |
| `channel` | The update channel, or `unknown`. |
| `target` | The release compared with: `name` and `prerelease`. |
| `checks` | Each check, with its `state` and what it `checked`. |
| `findings` | Every finding, check by check. The report groups them by level. |

`target.name` is the tag. With `--target` and no tag, it is the folder's name.
`target.prerelease` is `true`, `false` or `null` when the name isn't a tag.

### Checks

`checks` has the same four keys every time: `bindings`, `packages`, `commands` and
`plugins`.

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

### Findings

Each finding has every field, even an empty one.

| Field | Value |
| --- | --- |
| `check` | Which check found it. |
| `level` | `attention`, `note` or `unknown`. |
| `title` | What was found, in one sentence. |
| `evidence` | The files or lines behind it. Never empty. |
| `detail` | More about it, or `""`. |
| `fix` | What to do, or `""`. Every `attention` finding has one. |
| `partial` | On an `unknown`, `true` when the rest of its check still stood. |

The report shows `title` and `detail` together, then the `fix`.

Evidence in your home starts with `~`, and a line is `path:line`. Other paths are
inside an Omarchy tree, such as `migrations/1700000001.sh`. A name that isn't
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
    "prerelease": false
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
        "pendingMigrations": 1
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
    }
  },
  "findings": [
    {
      "check": "bindings",
      "level": "attention",
      "title": "SUPER + M: your \"Music\" will clash with the new default \"Minimize window\".",
      "evidence": [
        "default/hypr/bindings.lua",
        "~/.config/hypr/bindings.lua"
      ],
      "detail": "Both will fire.",
      "fix": "Add hl.unbind(\"SUPER + M\") above your binding, or choose another key.",
      "partial": false
    },
    {
      "check": "bindings",
      "level": "note",
      "title": "New default shortcuts: SUPER + N (\"Notifications\").",
      "evidence": [
        "default/hypr/bindings.lua"
      ],
      "detail": "",
      "fix": "",
      "partial": false
    },
    {
      "check": "packages",
      "level": "attention",
      "title": "The update will remove fictional-editor, which is installed here.",
      "evidence": [
        "migrations/1700000001.sh"
      ],
      "detail": "",
      "fix": "After the update, run omarchy pkg add fictional-editor (aur-add for an AUR package).",
      "partial": false
    },
    {
      "check": "packages",
      "level": "unknown",
      "title": "Couldn't read what migrations/1700000002.sh removes, so check it by hand.",
      "evidence": [
        "migrations/1700000002.sh"
      ],
      "detail": "",
      "fix": "",
      "partial": true
    },
    {
      "check": "commands",
      "level": "attention",
      "title": "~/.local/bin/sync-all calls omarchy-sync-notes, which the release deletes.",
      "evidence": [
        "~/.local/bin/sync-all:2"
      ],
      "detail": "",
      "fix": "Change or remove line 2. This tool can't tell what replaces the command.",
      "partial": false
    }
  ]
}
```

## No update

`noUpdate` has `installed`, `channel` and `target`, as a report does, and no checks
or findings.

| Key | Value |
| --- | --- |
| `newer` | Newer releases on other channels, each with its `tag` and `channel`. `[]` when there are none. |
| `newerProblem` | Why `newer` is `null`, or `null`. |

`newer` is `null` when the list of releases couldn't be fetched. That still exits 0,
as there is no update.

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
      "channel": "rc"
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
