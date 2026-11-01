# omaupdateimpact spec

The source of truth for what this project is and how it behaves. Tickets link
the sections they build. When a decision changes, change this file in the same
commit.

## The problem

An Omarchy update can change your shortcuts, remove packages you use and delete
commands your scripts call. Release notes describe what changed for everyone.
They can't say what it means for your machine, and you find out afterwards.

The v4.5.0-rc2 notes list the new shortcuts that could collide with "bindings of
your own". That list is general. Only your machine knows whether one of them
hits you.

## What it is

A read-only check that compares your setup with a release before you update, and
answers one question: what will this update do to my machine?

- **Personal.** It reports what touches your setup, not everything that changed.
- **Static.** Nothing from the release runs, so it is safe to point at an RC.
- **Specific.** Each finding names the file or key and says what to do about it.
- **Honest.** "I couldn't check that" is an answer, and it is never shown as clear.

### Who it is for

- People who customize Omarchy and update often.
- People trying an RC who want to know what they would sign up for.
- Later, plugin authors checking a plugin against an RC.

## Where it stops

- It doesn't change your setup. It says what to do, and you do it.
- It doesn't run migrations. Sandboxed dry runs are a different product, and
  [omaforecast](https://github.com/w-mir1/omaforecast) already does that.
- It doesn't take snapshots or roll back. Omarchy already snapshots with Snapper.
- It doesn't check the health of the running system. It compares two versions.
- It doesn't replace `omarchy update` or wrap it.

## What must never happen

1. **A clean result when a check didn't run.** No exit 0 and no "nothing found"
   unless every check really looked at real input.
2. **Release code running.** Release files are read as text. `qmllint` reads QML,
   it doesn't run it.
3. **Changes outside its own cache**, unless the user asked for an optional
   install step, such as the menu entry.
4. **Anything leaving the machine.** It only makes GET requests to GitHub, with no
   telemetry. Findings stay local.
5. **A finding without evidence.** Each one can name the line or file behind it.

## Product shape

One repository with a CLI at the core and a thin plugin on top, in this order:

1. **The CLI** does all the work and owns the rules. It is what the tests cover
   and what a terminal user runs.
2. **`--json`** is the contract between the CLI and anything else.
3. **An Omarchy menu row** is the cheap way to reach people who don't live in a
   terminal.
4. **A bar plugin** shows the result on the desktop and in the marketplace, where
   Omarchy users find tools. It holds no rules and only renders the JSON.

A separate desktop app is rejected: see [Rejected](#rejected).

## How it works

```
resolve target -> load both trees -> run checks -> findings -> render
  channel, tag     installed,        bindings       typed      text or
                   release, home     packages                  JSON
                                     commands
                                     plugins
```

### Choosing the release

An update delivers what the user's channel delivers, so that is the default.

| Channel | Default target |
| --- | --- |
| stable | the latest non-prerelease release |
| rc | the newest release, prereleases included |
| edge, dev, anything else | no tag exists: exit 2 and ask for an explicit tag |

The channel comes from `omarchy-version-channel`. It is looked up on `PATH`, like
`omarchy-version`. It prints two words when the mirror and the packages disagree,
and that counts as anything else. It can't see a linked checkout, so an installed
version of `dev` means the dev channel. `--channel` overrides it and a tag
argument overrides both.

"Newest" goes by version, not date, because the API sorts by date and a stable
patch can come after an RC. Whether a release is a prerelease goes by its tag.

A tag must look like `v1.2.3` or `v1.2.3-rc1`, because it becomes a cache path. A
tag argument of any other shape is exit 2 before anything else happens, even with
`--target`. Tags from the API are held to the same shape.

If the target is what's installed, it says so, names any newer release on another
channel, and exits 0: there is no update. Nothing is downloaded. If the list of
releases can't be fetched, it says so and still exits 0.

The tag `v4.5.0-rc2` is the package `4.5.0rc2-1`. The epoch and the pkgrel don't
make a different release, so `4.0.6-2` and `v4.0.6` are the same version. A dev or
unknown version matches nothing, so the check runs.

With `--root` or `--target` the trees are always compared. `omarchy-version` only
knows this machine, so it can't say a tree given by hand has no update.

### The two trees

- **Installed:** `$OMARCHY_PATH`, falling back to `/usr/share/omarchy`. `--root`
  overrides it.
- **Release:** an unpacked tarball in the cache. `--target` overrides it. The
  whole gzip stream must pass its checksum before anything is unpacked.

Before any check runs, both trees must hold `bin`, `default/hypr`, `migrations`
and `shell`, each with something in it. If one doesn't, that is exit 2, and the
line names what's missing. The installed tree is checked first, so a bad one
stops before any download.

A tree with no readable default bindings is also exit 2: the format has moved.
Computed keys don't count as readable.

The installed version comes from `omarchy-version`, which also handles
`omarchy-dev` and dev checkouts. It is looked up on `PATH`, and its path is never
built from `--root` or `--target`: those can point at a release, and nothing from
a release runs. If it fails, the version shows as "unknown".

### Downloads

`GITHUB_TOKEN`, when it's set, goes to `api.github.com` and nowhere else: a
redirect doesn't carry it on, and the archive doesn't need it. It is never printed,
even when it's malformed. A 403 or 429 with no requests left, or with
`Retry-After`, is reported as the rate limit.

On a terminal, stderr says what is downloading and counts the megabytes. GitHub
doesn't send the archive's size, so the count is all there is to show. Off a
terminal the download is silent.

### Checks

Each check returns findings and says whether it could run.

- **Bindings:** your bindings against both versions of the defaults. Flags clashes
  and shortcuts you turned off that come back, and lists the rest as notes.
- **Packages:** installed packages removed by migrations you haven't run yet. A
  removal it can't read, such as `"${targets[@]}"`, is reported as unknown. See
  [Reading migrations](#reading-migrations).
- **Commands:** deleted `omarchy-*` commands still called from your files. A file
  that Omarchy itself put there, unchanged, isn't your problem to fix. See
  [Reading your files](#reading-your-files).
- **Plugins:** new `qmllint` warnings. If `qmllint` fails, that is unknown, not
  clean. These never count as "needs attention": see the Limits in the README.
  With no plugins there is nothing to lint, so a missing `qmllint` doesn't matter.
  When plugins were linted, a note says `qmllint` can't prove a plugin works. See
  [Linting plugins](#linting-plugins).

### Linting plugins

Each plugin is linted against both shells, as absolute paths. A plugin is `unknown`,
and named, when `qmllint` can't start, dies from a signal, runs past 60 seconds, or
can't open one of the plugin's files. It is also `unknown` when `qmllint` exits
non-zero with no warnings to read. Warnings on a non-zero exit do count, because
`qmllint` exits 255 on a syntax error, and a broken plugin is still an answer.

A plugin is also `unknown` when a folder in it can't be read, because its files
wouldn't reach `qmllint`. A plugin that is a broken link is `unknown`, and so is a
plugins folder that can't be read. A plain file in that folder isn't a plugin.
Warnings go by the file's path inside the plugin, so the evidence names a real file.

One plugin failing doesn't stop the others. Warnings with no file, such as
`Warning: 2:1: Failed to import`, aren't counted: the line with the file comes
just before them. The tests read output captured from `qmllint` 6.12.0.

### Reading release formats

The tool reads Omarchy's internal formats, and they change. v4.5.0-rc2 added
`o.bind_hold`, which the first version didn't know, and that produced a false
"removed" finding. So the parser must notice what it doesn't understand: a
`function o.*bind*` it has no rule for is reported as a limit, and CI watches new
releases for it. Every Lua file under `default/hypr` is searched, not only
`helpers.lua`, so moving a helper doesn't hide it. A helper assigned to `o`, such
as `o.bind_foo = function`, counts too. `o.preinstalled_bindings_enabled` matches
the name but binds nothing, so it needs no rule.

A chord holds every bind made on it, so a press and release pair is one action.
Two chords do the same thing when each bind on one has a match on the other.

Modifiers follow Hyprland's Lua parser (`LuaBindingsToplevel.cpp`, checked at
v0.56.2): `CTRL` and `CONTROL`, `ALT` and `MOD1`, `SUPER`, `WIN`, `LOGO`, `MOD4` and
`META` are the same key. `SHIFT`, `CAPS`, `MOD2`, `MOD3` and `MOD5` have one name.

`hl.unbind` goes by text, not by chord: `removeKeybind` compares the keys as they
were written, ignoring only spaces and case. So `hl.unbind("CONTROL + A")` leaves a
bind written `CTRL + A`, and `SHIFT + SUPER + A` leaves `SUPER + SHIFT + A`. The
same two spellings clash, because the keys are the same, but only an unbind with
the matching text turns a default off. Fixes quote the default's own spelling.
`hl.unbind("all")` removes every bind made so far.

An unbind or `o.rebind` in the defaults removes the binds before it. The default
files are read in path order, not in the order Omarchy loads them.

### Reading migrations

Migrations are split into shell tokens, not matched line by line. A small state
machine follows them, so comments, strings, redirects, heredoc bodies and arrays
are never commands, and what runs in a `$(...)` still counts.

A removal is `omarchy-pkg-drop`, `omarchy-pkg-remove`, or `pacman`, `yay` or `paru`
with `-R` or `--remove`. Any wrapper counts, such as `sudo` or a function called
`as_root`, unless the command only prints or looks up, such as `echo` or
`command -v`. `-p` and `--print` only list what would go, so they don't count. A
command given by path counts by its last part, and `omarchy pkg drop` is
`omarchy-pkg-drop`.

A removal is conditional inside `if`, `while`, `until`, `for`, `case` or a function,
and after `&&` or `||`. Indentation means nothing. `omarchy-pkg-drop a || true`
still removes `a`.

`omarchy-pkg-add` and `omarchy-pkg-aur-add` cancel an earlier drop. A conditional
add may not run, so the package stays listed as "may remove". An add whose argument
can't be read cancels nothing and is not unknown: at worst it leaves a removal
listed, and v4.5.0-rc2 has several, such as `omarchy-pkg-add "$kernel"`.

A migration can remove packages through other release files, so those are read
too, as text, from the same tree: any `omarchy-*` command in `bin`, any
`$OMARCHY_PATH` script it sources or runs, directly or with `bash` or `sh`, and
whatever those reach in turn. v4.5.0-rc2's T3 Code migration removes its package
this way. A path with a variable in it isn't followed: the release's own commands
do that too often for each to be `unknown`, and the README lists it. What is found
there depends on arguments that aren't followed, so a removal is "may remove" and
an add cancels nothing. A migration that sources one already run still counts. The
evidence names the migration and the file. A file that isn't a shell script isn't
parsed: it only matters if its text names a removal, and then it is `unknown`.

A migration is `unknown`, once however many arguments it hides, when an argument
to a removal can't be read, when a removal names nothing, as with `xargs`, when a
string given to `bash -c`, `sh -c` or `eval` names a removal, or when the reader
loses its place, as with a quote that never closes. The same goes for a file it
reaches, and the finding names that file too. What it can read from the same
removal is still reported.

### Reading your files

Commands are looked for in these places:

- Hyprland config and Omarchy's hooks, extensions and plugins, in files with a text
  suffix such as `.lua`, `.sh`, `.hook` or `.jsonc`. A plugin's `README.md` and a
  hook's `.sample` aren't calls.
- `~/.local/bin`, `~/.config/systemd/user` and `~/.local/share/applications`, in
  every file. A script needs no suffix there.
- `shell.json`, `shell.toml` and the startup files of bash, zsh and fish.

Links are followed, and each real folder is read once, so a link loop ends. A folder
both ways of reading can reach is read in full. `.git` is skipped, and so are backups
and systemd's `.wants` and `.requires` folders: those only hold links, and mostly to
units a package owns, such as Omarchy's own.

A file byte-identical to any file in the installed tree is Omarchy's own, wherever
it sits. Hooks are copied from `install/user/first-run` to another path, so the path
can't count. A call in one is a note, and the evidence names the file it matches.
An edited copy needs attention.

The evidence names each line a command is called on. Lines are counted as an editor
counts them, by newlines. Comment lines are skipped.

A file with a NUL byte is binary and is skipped, because there is nothing to read.
Other text counts even if it isn't UTF-8. A text file over 10 MiB is skipped too,
but that is `unknown`: it could hold a call. NUL is looked for in the first 10 MiB,
so a large binary isn't reported.

A file or folder that exists but can't be read is `unknown` and is named: a broken
link, a broken link in a folder above it, a denied one, or the wrong kind, such as a
pipe. With nothing there, there is nothing to check. With no deleted commands
nothing is read, so nothing is unknown.

## Findings and exit codes

A finding has a check, a level, a title, a detail, a fix when there is one, and
evidence. Levels are `attention`, `note` and `unknown`.

| Exit | Meaning |
| --- | --- |
| 0 | Every check ran and nothing needs attention, or there is no update |
| 1 | Something needs attention |
| 2 | No verdict: bad usage, a failed download, an unusable tree or a crash |
| 3 | Nothing needs attention, but at least one check couldn't run |

An unexpected exception is exit 2 with one line of explanation. It never falls
through to Python's exit 1, which would read as a finding.

When something needs attention and a check also couldn't run, the exit is 1, and
the closing line still names the checks that didn't run.

Bindings with computed keys can't be compared, since working out the key would
mean running Lua. Every release has them, so making them all `unknown` would make
exit 0 impossible. A computed key in the defaults is a note while its key
expression is the same in both versions, spacing aside. Each expression is counted
as many times as both versions share it, so a call in both counts once. It is
`unknown` when the expressions differ, and so is a computed key in your own
bindings. An expression in only one version counts as a difference, and a computed
`hl.unbind` is apart from a bind on the same expression. A loop whose range changes
while its key expression stays the same is still a note. They stay listed in the
README's limits.

A `~/.config/hypr/bindings.lua` that exists but can't be read is `unknown`: a broken
link, a broken link in a folder above it, a denied file, or anything that isn't a
file. With no such file there is nothing to compare, which is not a limit.

## JSON

`--json` prints one document and nothing else: `schemaVersion`, the installed
version, the target, the channel, and the findings. Exit codes don't change. A
breaking change bumps `schemaVersion`.

## Files

- `~/.cache/omaupdateimpact/<tag>`: unpacked releases. `XDG_CACHE_HOME` replaces
  `~/.cache` unless it's empty. After a download, the release it fetched and the
  newest other one by version stay, and the rest go. So an older release someone
  asks for is not removed before it's read. Nothing else in the cache is touched.
- Reviewed findings, once they exist, in `~/.config/omaupdateimpact/`.

Nothing else is written.

## Neighbours

Checked 2026-10-31. These are the closest tools; none compares your bindings,
scripts and packages with a coming release.

| Tool | What it does | How it differs |
| --- | --- | --- |
| [omaforecast](https://github.com/w-mir1/omaforecast) | Dry-runs migrations in a sandbox, shows config diffs, restores | Runs release code; its forecast covers files, not bindings or packages |
| [OmaPreflight](https://github.com/p134c0d3/omarchy-omapreflight) | Diagnoses the current system before an update | Local only, never looks at the release |
| [Aether Guard](https://github.com/eerengz/omarchy-plugin-aether-guard) | Local conditions before an update | Same: looks at this machine only |
| [Update Review](https://github.com/jampick/omarchy-update-review) | Lists pending packages and restarts | About package versions, not your setup |
| [Safe Update](https://github.com/Nejcc/omarchy-safe-update) | Checks plugins after an update | After, not before |

omaforecast is a complement rather than a rival, and the README should say so:
one reads the release and needs no sandbox, the other runs it and sees file edits.

Omarchy has no pre-update hook. [PR #10398](https://github.com/omacom/omarchy/pull/10398)
adds one before the dev checkout pull, and was open and quiet at the last check.
So this tool can't gate an update, and users have to run it themselves.

## Rejected

- **A standalone desktop app.** In Omarchy the shell is the app surface. A plugin
  reaches the same people with far less to build and maintain.
- **Running migrations.** It would break the promise that nothing from the release
  runs, and it would compete on omaforecast's ground.
- **Evaluating Lua to read bindings.** Same promise. Text parsing with honest
  limits is the trade.
- **Wrapping `omarchy update`.** It would make this tool a point of failure in the
  update path.
- **Applying fixes.** Being read-only is why people can trust it. It prints the
  exact line instead.
- **A safety score.** It would imply precision that static reading can't give.

## Open questions

- Does a plugin get a second repository, or live in this one? Default: this one.
  Settled in [021](tickets/021-plugin-design.md).
- Are `edge` and `dev` worth supporting by comparing with the branch tip? In the
  [backlog](tickets/BACKLOG.md).
