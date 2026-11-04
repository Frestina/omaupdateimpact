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
3. **Changes outside its own cache**, unless the user asked for it: an optional
   install step, such as the menu entry, `--ack` and `--unack`, which record a
   reviewed finding and take it back, or a setting chosen in the plugin's panel.
4. **Anything leaving the machine.** It only makes GET requests to GitHub, with no
   telemetry. Findings stay local. The panel's "Ask agent" hands a finding to the
   user's own coding agent when they click it, and what that agent sends to its
   model is the agent's.
5. **A finding without evidence.** Each one can name the line or file behind it.

## Product shape

One repository with a CLI at the core and a thin plugin on top, in this order:

1. **The CLI** does all the work and owns the rules. It is what the tests cover
   and what a terminal user runs.
2. **`--json`** is the contract between the CLI and anything else.
3. **An Omarchy menu row** is the cheap way to reach people who don't live in a
   terminal.
4. **A bar plugin** shows the result on the desktop and in the marketplace, where
   Omarchy users find tools. It holds no rules and only renders the JSON. See
   [Plugin](#plugin).

A separate desktop app is rejected: see [Rejected](#rejected).

## How it works

```
resolve target -> load both trees -> run checks -> findings -> render
  channel, tag     installed,        bindings       typed      text or
                   release, home     packages                  JSON
                                     commands
                                     plugins
                                     edits
```

### Choosing the release

An update delivers what the user's channel delivers, so that is the default.

| Channel | Default target |
| --- | --- |
| stable | the latest non-prerelease release |
| rc | the newest release, prereleases included |
| edge, dev, anything else | no tag exists: exit 2 and ask for an explicit tag |

The channel comes from `omarchy-version-channel`. It is looked up on `PATH`, like
`omarchy-version`. It prints `mirror / packages` when the two disagree, and that
counts as anything else: the message says they disagree and names each. It can't
see a linked checkout, so an installed version of `dev` means the dev channel.
`--channel` overrides it and a tag argument overrides both.

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
even when it's malformed. A 401 with a token set is reported as a rejected token.
A 403 or 429 with no requests left, or with `Retry-After`, is reported as the rate
limit.

On a terminal, stderr says what is downloading and counts the megabytes. GitHub
doesn't send the archive's size, so the count is all there is to show. Off a
terminal the download is silent.

After the archive, the release's notes come from `releases/tags/<tag>`, and are kept
in its folder as `.omaupdateimpact-notes.md`, as GitHub sent them. They are written
whole and then moved into place, so notes cut short never pass for the notes. A
release with no notes, or a tag with no release (a 404), keeps empty notes, so it
isn't asked again. A release already in the cache without notes asks for them
alone. Notes that can't be fetched leave one line on stderr and no file, so the next
run asks again. Nothing else changes: the findings, the "Checked" line and the exit
code are the same, only without reasons. With `--target`, the notes are read from
that folder if they are there, and never fetched.

Two runs can share the cache, such as the plugin's check and one from a terminal.
A run locks the cache folder while it looks for its release, downloads it and
prunes. Another run waits for that lock, even for a release already there, as a
prune could otherwise take it. Then it finds the release in the cache, so a release
downloads once. While it waits, stderr says once, on a terminal or not: "Another
omaupdateimpact run is using the cache. Waiting for it to finish." It waits up to
15 minutes. Then it fails as a download that failed, with exit 2, and says another
run held the cache. A run also holds a shared lock on the release it reads, until
it ends, and a prune leaves a locked release where it is. The locks are `flock` on
the folders themselves, so no lock file is written, and the kernel frees them when
a run ends, however it ends. With `--target`, nothing is locked.

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
- **Edits:** your files that migrations you haven't run yet look like they write,
  unless a file is still Omarchy's default. These are notes, because reading a
  migration can't say what the file will hold. A write it can't place is `unknown`.
  See [Reading what migrations write](#reading-what-migrations-write).

### Linting plugins

Each plugin is linted against both shells, as absolute paths. A plugin is `unknown`,
and named, when `qmllint` can't start, dies from a signal, runs past 60 seconds, or
can't open one of the plugin's files. It is also `unknown` when `qmllint` exits
non-zero with no warnings to read. Warnings on a non-zero exit do count, because
`qmllint` exits 255 on a syntax error, and a broken plugin is still an answer.

Only a `qmllint` from Qt 6 or newer counts, because the shell is Qt 6. Qt 5's prints
nothing and only checks syntax, so a plugin that passes it wasn't compared at all,
and it can come first on `PATH`: `qt5-declarative` puts it at `/usr/bin/qmllint`. So
the first of `qmllint` on `PATH` and `/usr/lib/qt6/bin/qmllint` whose `--version`
reads 6 or newer is used. If neither does, plugins are `unknown` and not linted, and
the line says what was found. Omarchy installs `qt6-declarative`, so this is rare
there.

A plugin is also `unknown` when a folder in it can't be read, because its files
wouldn't reach `qmllint`. A plugin that is a broken link is `unknown`, and so is a
plugins folder that can't be read. A plain file in that folder isn't a plugin.
Warnings go by the file's path inside the plugin, so the evidence names a real file.

One plugin failing doesn't stop the others. Warnings with no file, such as
`Warning: 2:1: Failed to import`, aren't counted: the line with the file comes
just before them. The tests read output captured from `qmllint` 6.12.0.

CI runs the real `qmllint` too. Its `RealQmllint` tests fail if the output stops
reading. Ubuntu's version is frozen at an old Qt, so a CI job on rolling Arch runs
the same version Omarchy users get, and that is the job that sees a change.

### Reading release formats

The tool reads Omarchy's internal formats, and they change. v4.5.0-rc2 added
`o.bind_hold`, which the first version didn't know, and that produced a false
"removed" finding. So the parser must notice what it doesn't understand: a
`function o.*bind*` it has no rule for is reported as a limit, and CI watches new
releases for it. Every Lua file under `default/hypr` is searched, not only
`helpers.lua`, so moving a helper doesn't hide it. A helper assigned to `o`, such
as `o.bind_foo = function`, counts too. `o.preinstalled_bindings_enabled` matches
the name but binds nothing, so it needs no rule.

A daily job, the drift watch, reads the newest release, RCs included. It fails on
a helper with no rule, on zero default bindings and on a missing tree folder, and
also when it can't fetch the release. It has read access only and reads the release
as text, as the tool does. A failed run reaches the owner through GitHub's own
notice for failed scheduled runs. CI and the watch are in `.github/workflows`, and
`python3 -m tests.drift_watch --target PATH` runs the watch on an unpacked tree.

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

### Reading what migrations write

This finds likely edits by reading. omaforecast finds them by running migrations,
which this never does, so a note names it.

Pending migrations are split into shell tokens, as for packages. A write is `sed -i`,
the file `cp`, `install` or `ln -f` writes, both files of `mv`, `rm`, `tee`, and output
sent to a file with `>`, `>>` or `&>`. `mv` and `rm` remove what they name. A copy, a
move or a link into a folder writes the file of the same name there, and `ln -n` or
`-T` replaces a link to a folder rather than going into it. A link that already
points where the new one would says nothing. `ln` without `-f` and `install -d`
write no file.

The writer is the first word of a command, or comes behind commands that run their
arguments. Those are `sudo`, `doas`, `env`, `command`, `exec`, `nohup`, `nice`,
`ionice`, `timeout` and `stdbuf`, past their options and assignments, and functions
the migration defines that run `"$@"`. Behind such a function the next writer word
counts, so `retry 3 rm ~/x` is read. A function that runs `sudo "$@"`, as
v4.5.0-rc2's `as_root` does, counts as `sudo`. A writer's name anywhere else, as in
`mise install node`, `git mv` or a quoted `"cp"`, isn't a write. This differs from
packages, where any wrapper counts, because removal commands never turn up as plain
words and writers' names do.

`find` changes files whose names are only known when it runs when it has `-delete`,
or when `-exec`, `-execdir`, `-ok` or `-okdir` runs a writer, read as above, or a
shell given a string, such as `sh -c`. `find -exec grep` changes nothing. In your
files a find that changes them is `unknown`, and elsewhere, or in a folder you don't
have, it says nothing.

Nothing else is read as a write. That leaves out `xargs`, `awk -i inplace`,
`perl -i`, `rsync`, `truncate`, `dd`, a `bash -c` or `eval` string and any other
command. What a release command such as `omarchy-bar` writes isn't seen, and other
release files aren't read for writes.

A path is read as bash would expand it, without running anything:

- `~`, `$HOME` and the variables the migration sets are followed, wherever it sets
  them. A variable set in more than one place holds each value, and a `for` loop's
  variable holds each word of its list.
- In a function the migration defines, `$1`, `$2` and `"$@"` hold what each call
  passes, read as any other word is. A function called more than once holds each
  call's values, as a variable set in more than one place does. An argument a call
  leaves out is empty, and past a `"$@"` in a call each later argument can hold any
  of them. Arguments pass on through calls to other functions.
- After a function's first `shift` or `set`, its arguments are only known when it
  runs, and so they are anywhere in it when one of those is in a loop. So are the
  arguments of a function nothing calls, and of one whose values never settle, as
  when it calls itself with a longer path each time.
- A variable the migration doesn't set takes its default, so
  `${XDG_CONFIG_HOME:-$HOME/.config}` is `~/.config`. `$OMARCHY_PATH` is the release.
- `${name#pattern}`, `${name##pattern}`, `${name%pattern}` and `${name%%pattern}`
  cut what the pattern matches from a value that is known, as bash does. v4.5.0-rc2's
  1786719479 links to `skills/${name##*/}`. A pattern with both quotes and a `*`, `?`
  or `[` is only known when it runs, as a quoted `*` matches only itself.
- `{a,b}` lists are spelled out, and wildcards are matched in your home.
- `mktemp` makes a file by its template, or one that isn't yours when it has none.
  `realpath` and `readlink -f` name the file they're given.

A path only known when the migration runs, such as `$1` outside a function, a
`$(...)`, an array or a variable from `read`, is `unknown`, once per migration, with
its lines. v4.5.0-rc2's 1791723398 passes `${files[0]}`, an array, so its write is
`unknown`. The title lists up to three lines and counts more. So is a relative
path, as it depends on where the migration runs. A path that is known as far as a
folder outside your home, such as `/etc/$name`, isn't, and neither is one written
under `sudo`, which is for system files. v4.5.0-rc2 removes files that `find` lists
in `/etc` that way. A migration the reader loses its place in, as with a quote that
never closes, is `unknown` too.

Your files are those in your home, but for `~/.cache` and `~/.local/state`: they
hold Omarchy's caches and state, not files you change. Omarchy's default of a file
in `~/.config` is the file at the same place under `config` in a tree, and of a
launcher in `~/.local/share/applications` the one under `applications`. A file
byte-identical to its default in either tree is unchanged and says nothing, and so
does a file you don't have.

Any other file of yours a migration writes is a note. It says the migration "looks
like it edits" or "removes" the file, with the lines, and whether the file differs
from Omarchy's default or has none. The evidence names the lines, the file and the
default. A path with wildcards is one note that names the files of yours it matches.
So is a word that names more than one file of yours, through a loop or a function's
calls: v4.5.0-rc2's 1791382872 removes `~/.local/bin/$command` for 20 tools, but only
the wrappers Omarchy wrote. Migrations often go through every launcher and change
only some, so the note says that it may.

### Reading your files

Commands are looked for in these places:

- Hyprland config and Omarchy's hooks, extensions and plugins, in files with a text
  suffix such as `.lua`, `.sh`, `.hook` or `.jsonc`. A plugin's `README.md` and a
  hook's `.sample` aren't calls.
- `~/.local/bin`, `~/.config/systemd/user` and `~/.local/share/applications`, in
  every file. A script needs no suffix there.
- `shell.json`, `shell.toml` and the startup files of bash, zsh and fish.

The tool's own files aren't your setup, so no check reads them. They are:

- The running command's own file, found by real path. This covers the link
  `install.sh` puts in `~/.local/bin`, and a copy put there by hand.
- The checkout the running command is in: the folder above its `bin/`, found by real
  path. It counts only when it holds a `manifest.json` with this tool's id, as the
  repository does. A copy in `~/.local/bin` would make that folder `~/.local`, and a
  package in `/usr/bin` would make it `/usr`. Both hold files of yours, so without
  the manifest the folder is read as yours.
- A plugin whose `manifest.json` has this tool's id. The plugin is the whole
  repository, tests included, and its tests name deleted commands on purpose. A
  terminal install and the plugin can be two clones, so the id counts as well as the
  path.

They are left out of the commands and plugins checks, and of the "Checked" counts.
The plugin's QML is linted in this project's CI. A file or folder whose real path is
in one of them is left out wherever it is linked from. A folder that holds your home
is never left out, as that would leave out everything. A `manifest.json` that can't
be read, or isn't a plain file, doesn't make a folder this tool's own. It is never
opened if it is a pipe, as that would wait forever.

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

A finding has an id, a check, a level, a title, a detail, a fix when there is one, a
reason when the release notes give one, and evidence. Levels are `attention`, `note`
and `unknown`. An `unknown` also says whether the rest of its check still stood.

### Reviewed findings

Someone who has seen a finding and accepted it can say so, so it doesn't hide a new
one. `--ack <id>` marks it reviewed, for the release compared with only, so a new
release asks again.

The id is the first 7 hex digits of a SHA-256 of the check and what the finding
says, its title and detail. It stays the same while those do, in any release, and
changes when they do. A line number isn't part of it, so editing another line of a
file doesn't ask again.

Only an `attention` finding can be reviewed. A note doesn't count anyway, and a limit
can't be: a check that didn't run is never clear. `--ack` runs the same comparison
first. If any id it is given isn't an `attention` finding in that comparison, or
there is no update, it is exit 2 and nothing is written. It takes more than one
id, and an id in capitals.

`--unack <id>` takes a review back, for the release compared with only. It removes
the lines for that release and id, and leaves every other byte of the file as it
was, comments included. It runs the same comparison first. If the file has no line
for that release and an id it is given, or there is no update, it is exit 2 and
nothing is written. `--ack` and `--unack` together are bad usage. The file is
written whole and then moved into place, in the folder of the file a link points
to, so a file kept as a link stays one.

Reviews are kept in `~/.config/omaupdateimpact/reviewed`, one per line: the
release's name, as `target.name` gives it, the id, and the title then, for a person
to read. `#` starts a comment line. A person can edit it, and deleting a line asks
again. `--ack` appends, so a file kept as a link stays one. A file that can't be
read leaves nothing out and says so on stderr, as more findings is the safe side.

A reviewed finding doesn't count for the exit code or `result`, and the report
leaves it out of "Needs attention". It is counted at the end, before the closing
line, and `--all` lists it. When it was all that needed attention, the closing line
says "Nothing else needs attention."

### Reasons

A reason is the change in the release notes that a finding comes from. A wrong
reason is worse than none, so a finding takes one only when exactly one change names
it. The same change listed in two sections is one change. A change is a list item
as GitHub writes it, `- what changed by @someone in #123`: its text, without who
made it, and its reference. Other lines aren't changes, such as the breaking-changes
bullets, which name no pull request.

What a change can name:

- **A package:** the name as a word, or with a capital first letter, as a name in a
  sentence has, in a change that starts with Remove, Replace, Drop, Switch or Retire,
  and before its first comma. A change that fixes or adds a package isn't why it
  goes: in v4.5.0-rc2 "Turn on hardware video decoding in mpv" would be a wrong
  reason for removing `mpv`. After a comma the sentence is about something else, as
  in "Remove the Azerbaijani keyboard choice, which installed French AZERTY".
  "Replace Tensaku with Omasnap for screenshots" names `tensaku`, and
  `fictional-editor-git` doesn't name `fictional-editor`. A name the notes spell
  another way, such as "Xournal++" for `xournalpp`, isn't found. A package named like
  an ordinary word can still match one: `usage` would take "Replace the Disk Usage
  TUI with Disktree".
- **A migration**, for a removal or an edit it makes: a change whose text is what the
  migration echoes on its first line, as Omarchy's migrations do, case, spacing and
  a full stop aside. v4.5.0-rc2's 1791345484 echoes "Replace the Disk Usage TUI with
  Disktree", which is #14426, and so the `dua-cli` it removes has that reason. An
  echo with a variable in it says nothing.
- **A command:** the deleted command's name as a word.
- **Keys:** a chord in the change, such as `Super + Shift + Q`, read as the
  bindings check reads keys. A move is about both its keys. A list of new or removed
  shortcuts isn't about any one key, so it takes no reason.

An `unknown` takes no reason: a limit of this tool isn't in the notes. A migration's
first line isn't a reason by itself, only a way to find its change, so without notes
no finding has a reason.

The report prints the reason on a `Why:` line, after the finding and before its fix,
with its reference, such as `Why: Replace the Disk Usage TUI with Disktree (#14426).`
Its evidence is the line in the notes.

| Exit | Meaning |
| --- | --- |
| 0 | Every check ran and nothing needs attention, or there is no update |
| 1 | Something needs attention, that you haven't reviewed |
| 2 | No verdict: bad usage, a failed download, an unusable tree or a crash |
| 3 | Nothing needs attention, but at least one check couldn't run in full |

An unexpected exception is exit 2 with one line of explanation. It never falls
through to Python's exit 1, which would read as a finding.

When something needs attention and a check also couldn't run, the exit is 1, and
the closing line still names the checks that didn't run.

The closing line tells a check that didn't run from one that ran in part. It ran in
part when it still compared something: bindings around a computed key or a helper it
can't read, the other migrations, files or plugins around one it couldn't read. A
`~/.config/hypr/bindings.lua` it can't read means your bindings weren't compared, so
that check didn't run. Both count the same for the exit code.

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

### The report

The report answers in five seconds. It goes: the two versions, what was checked,
what needs attention, a count of notes, the limits, and the closing line. `--all`
shows the notes in place of their count. Limits are never collapsed.

The "Checked" line counts only what was really looked at, and leaves out a check
that didn't run, so it can't read as clear. A migration, file or plugin that couldn't
be read isn't counted. Your bindings are left out when the file can't be read. A file
that is skipped as binary counts: it was looked at, and holds nothing to read. The
packages and edits checks both read the pending migrations. When they read as many,
the line counts them once, and otherwise it gives each.

Every attention finding has a `Fix:` line, or says why it can't have an exact one.
It ends with its id in brackets, and the section's title says how to review one.
The id goes on the finding's own line rather than one of its own, so the report
still fits a screen.

- A clash: the `hl.unbind` line, with the default's own spelling, above your binding.
  Below it, the unbind would turn yours off too, as text is all it goes by.
- A shortcut that comes back: the `hl.unbind` line for its new key.
- A package: `omarchy pkg add` after the update. That runs `pacman`, so the line also
  names `aur-add`, as nothing here tells an AUR package from a repository one.
- A deleted command: the lines to change. A release doesn't say what replaces a
  command, and some are renamed and some are gone, so the tool can't say either.

A move is one finding, with what else changed on its two keys: the default it
replaces, and what now sits on the key it left. If another move accounts for one of
those keys, that move's line tells it, so two keys that swap are just two moves.

A command or a line to copy is never split across lines. Colour goes to a terminal
only, and `NO_COLOR` turns it off unless it's empty.

## JSON

`--json` prints one document and nothing else: `schemaVersion`, the installed
version, the target, the channel, what was checked, each check's state, and the
findings. Exit codes don't change. A breaking change bumps `schemaVersion`. A
finding's reason has its text, its reference and its evidence, or is `null`.

The target has `path`, the unpacked release the command read, so an agent can read
its files and notes. A finding that lists things, such as each new default
shortcut, has `items`, one string per thing, such as
`SUPER + M: Minimize window to the dock`, and its title says how many, such as
"18 new default shortcuts." The text report prints the items one per line under the
title. Other findings have no `items`.

The plugin holds no rules, so the document carries what the report works out. What
was checked is data, not the "Checked" line's text. Each check says whether it ran,
ran in part or didn't run, as the closing line does. Each finding has every field,
its evidence included, its `id`, and whether it was `reviewed`.

When there is no update, the document says so and names any newer release on
another channel, with whether it is already in the cache. A failure that ends in
exit 2 is a document too, with the reason.

`result` names the kind of document and maps to one exit code: `clear`, `noUpdate`,
`attention`, `failed` or `incomplete`. A count of something that wasn't looked at is
`null`, as the "Checked" line leaves it out, so it can't read as zero. The text
report is printed from the same document, so the two can't disagree.

While a run goes, anything printed goes to stderr, so stdout holds the document
alone. Bad usage is a document too: `--json` is read before argparse, abbreviations
included, so its error can answer in JSON. So is an old Python. `--help` and
`--version` print text.

The schema is in `docs/json.md`. Its examples are the command's output on small
fictional trees, kept as golden files in `tests/fixtures/json`, and a test fails
when either stops matching. `python3 -m tests.golden` writes them again. There is one
for every result, and one with a reviewed finding, for the plugin's tests. The doc
shows three of them.

## Files

- `~/.cache/omaupdateimpact/<tag>`: unpacked releases, each with its notes as
  `.omaupdateimpact-notes.md`. No release file has that name. `XDG_CACHE_HOME`
  replaces `~/.cache` unless it's empty. After a download, the release it fetched and the
  newest other one by version stay, and the rest go. So an older release someone
  asks for is not removed before it's read. Nor is one that another run is
  reading: the next download removes it. See [Downloads](#downloads). Nothing else
  in the cache is touched.
- `~/.config/omaupdateimpact/reviewed`: [reviewed findings](#reviewed-findings),
  written only by `--ack` and `--unack`. `XDG_CONFIG_HOME` replaces `~/.config`
  unless it's empty, and `--home` moves `~/.config` with it, as it does `~/.cache`.

The command writes nothing else. `install.sh` writes its link, and with `--menu`
one marked block in Omarchy's menu file. See [Install](#install). The plugin changes
only its own setting, when you choose one, and its command writes only these. See
[Plugin](#plugin).

## Install

It needs Python 3.11.4, because `tarfile`'s `filter=` does. An older Python gets one
line on stderr and exit 2. That check comes before the other imports, and the file
has to parse on an old Python for it to run, so it uses no syntax newer than 3.7.
`--version` reads `__version__` in the command, and `manifest.json` repeats it for
the plugin. A test holds the two together. A release's tag is made from it.

`install.sh` links the command into `~/.local/bin`, which Omarchy puts on `PATH`,
and creates that folder if it's missing. It runs `--version` first, so a Python
that's too old stops it with that one line and no link. It only ever touches its
own link, meaning a link that resolves to the checkout the script is in. Anything
else there, including a link to another checkout or a broken one, is left alone and
is exit 1. Finding its own link already there is exit 0.

`install.sh --uninstall` removes that link, and the menu row if `--menu` added it,
and nothing else. It names the cache and the reviewed findings when they are there,
and leaves them for the user to delete. It says nothing is left behind only when
neither is. `~/.local/bin` stays, even if the install created it, because other
tools share it.

`install.sh --menu` does the same, then adds a row to the Omarchy menu, under
Update, for people who don't open a terminal to update. It goes in
`~/.config/omarchy/extensions/omarchy-menu.jsonc`, the file Omarchy's menu reads
for user rows. Omarchy reads that path under `HOME`, so `XDG_CONFIG_HOME` doesn't
move it. The format was checked against the menu code in v4.0.6 and v4.5.0-rc2.

- The row is `update.omaupdateimpact`, labelled "Omarchy Impact". Its action is
  `omarchy-launch-floating-terminal-with-presentation omaupdateimpact`, the launcher
  Omarchy's own update row uses. It finds the command on `PATH`, which Omarchy's
  login shell sets. Omarchy adds user rows after its own, so it is the last row
  under Update.
- The row sits in a block of three whole lines, from
  `// omaupdateimpact: begin. ...` to `// omaupdateimpact: end`. It goes on the
  lines right after the file's opening `{`, with that line's own ending, CRLF
  included. Nothing else in the file changes, and uninstall gives back the file
  byte for byte.
- Two cases keep a change after uninstall. When more follows the `{` on its line,
  as in `{}` or a menu on one line, that line is split after the `{`, and stays
  split. A file that is missing, or holds only comments, gets an object of its own
  after them, and `{` and `}` stay.
- The file is read the way Omarchy reads it: comments on their own lines and
  trailing commas are dropped, then it is parsed as JSON. If Omarchy couldn't read
  it, or wouldn't show the row with the user's other rows unchanged, the file is
  left alone and it's exit 1. So is a begin mark without its end.
- A block already there is rewritten in place to the current row, so running it
  twice adds one row. A file that is a link stays one, and keeps its mode.
- Without `default/omarchy/omarchy-menu.jsonc` in the installed tree, the menu
  that reads the file isn't there, so nothing is installed and it's exit 1. The
  tree is found as the command finds it: `$OMARCHY_PATH`, then `/usr/share/omarchy`
  when that is unset or empty, as from SSH or a TTY. That check comes before the
  link.

`install.sh --uninstall` removes that block, and only it, before the link. A
broken block is left alone with exit 1, and the link still goes. It says nothing
about the menu when there is no block.

There are two ways to install, and each works on its own: the plugin, which brings
its own command (see [Plugin](#plugin)), and the clone with `install.sh`, for the
terminal and the menu row. There is no package. The AUR package was removed in 023,
as publishing one needs an AUR account. It can come back from git history.

## Plugin

The plugin shows the result in the bar, for people who never open a terminal. It
holds no rules. It runs the command and renders its `--json`, so the two can't
disagree. It was checked against the shell in v4.0.6 and v4.5.0-rc2.

- **One repository.** `manifest.json` sits at the root of this one, beside the
  command, as in Frestina's other plugins. `omarchy plugin add` clones the whole
  repository, so the plugin and the command it runs are always the same version. A
  second repository would have to keep a copy of the command in step. The clone
  sits in a folder the command checks, so the command leaves its own files out.
  See [Reading your files](#reading-your-files).
- **The command comes with the plugin.** The plugin runs its own
  `bin/omaupdateimpact`, found from its QML's own path, and never one on `PATH`.
  One on `PATH` could be another version, with another `schemaVersion`. Nothing is
  installed for it: it needs Python 3.11.4, and Omarchy's base packages already
  pull Python in. `install.sh` stays for terminal users and the menu row.
- **The id is `io.github.frestina.omaupdateimpact`.** It can't change once
  published, as it names the plugin's folder and its entry in `shell.json`. It
  follows the other Frestina plugins and stays out of the reserved `omarchy.*`.
  The command holds it as `PLUGIN_ID`, and `manifest.json` must hold the same. Its
  `version` is the command's `__version__`. A test holds each pair together, and
  every id in the QML to `PLUGIN_ID`.
- **No links in the repository.** `omarchy plugin validate` refuses a plugin that
  holds one. There are none now, and a fixture that needs one makes it in the test.
- **No agent files in the repository.** The plugin is the whole clone, and the
  marketplace has turned plugins down for carrying instructions to coding agents.
  `AGENTS.md`, `CLAUDE.md` and `.claude/` stay on the developer's disk, ignored by
  git, and a test fails if git tracks one.

### Kinds

`kinds` is `service` and `bar-widget`. The QML is in `plugin/`: `Service.qml`,
`Widget.qml`, and `State.js`, which they import.

- The **service** is the only thing that runs the command. The shell loads one,
  however many monitors there are, so a check runs once and not once per monitor.
  It keeps the last result in memory and writes nothing.
- The **bar widget** draws the icon on each monitor and opens its own panel on a
  click. It finds the service through the shell's `serviceFor`, with its own id.
  The panel belongs to the widget. It isn't a `panel` kind, as nothing else opens
  it.
- Enabling the widget enables the service. The shell counts a plugin that isn't
  Omarchy's as enabled when its id is anywhere in `shell.json`, and the bar entry
  is one such place.
- A replacement bar gives its widgets no service. The widget then shows that it
  couldn't check, and says why.
- The service answers IPC on its id, with one method, `check`, which does what
  "Check again" does. It is for tests and scripts.

### When it checks

The command already knows when there is an update. With none, it makes one request
to GitHub, for the list of releases, and downloads nothing. With one, it downloads
that release once and keeps it in the cache, so later checks read it from there. So
the download, about 200 MB, happens once, when a new release appears.

- The first check is 2 minutes after the service loads, so the network has time to
  come up after login.
- Then one every `checkEveryHours`, the widget's one setting. It is 6 by default,
  as for Omarchy's own update icon, and goes from 1 to 168. 0 checks only when
  asked, for a metered connection. The widget hands it to the service. The panel
  offers only when asked, 1, 6, 12 and 24 hours. A choice is saved on the widget's
  own entry in `shell.json` through the shell's `updateEntryInline`, as Omarchy's
  clock and weather panels save theirs. A value set by hand in the file is kept and
  shown, even when the panel doesn't offer it. A value outside 0 to 168, or not a
  number, counts as 6, and the panel shows 6. A new choice applies at once: the next
  check is due that long after the last one started, so a shorter one can check
  within seconds.
- "Check again" checks now and starts the wait over. A check already running isn't
  started twice. A run from a terminal or the menu at the same time shares the
  cache, and the release still downloads once. See [Downloads](#downloads).
- An update restarts the shell, so the service loads again and checks the new
  version 2 minutes later. No hook is needed.
- It doesn't use `omarchy-update-available` to decide. That runs `checkupdates`,
  which asks the package mirrors, and only GitHub may be asked. It also follows the
  package, not the tag the command compares with.

### What the bar shows

The service reads `result` and the exit code. If they disagree, if the output isn't
one JSON document, or if `schemaVersion` isn't 1, the check couldn't be read, and
that is shown as "couldn't check", with the last line of stderr.

| State | When | Icon | Tooltip |
| --- | --- | --- | --- |
| Not checked | No result yet | Muted, with `…` | "Checking…", or "Not checked yet" when it checks only when asked |
| Quiet | `noUpdate` or `clear` | Muted, no mark | "Omarchy v4.0.6 is up to date", or "v4.5.0: nothing needs attention" |
| Attention | `attention` | Warning colour, with the count to review | "v4.5.0: 2 things need attention" |
| Couldn't check | `incomplete`, `failed`, output it couldn't read, no service, or no command | Text colour, with `?` | "Couldn't check v4.5.0" and why |

- The icon is always there. A hidden icon would look the same as a widget that
  never ran.
- The count is the attention findings that aren't reviewed, as `result` counts them.
- `attention` with checks that didn't run in full shows as attention. The panel
  lists the limits.
- While a check runs, the last state stays, and the tooltip adds "Checking…".
- Colours are theme tokens, by role: muted text, text, and the warning colour.
  Muted is the text colour faded, as the shell fades its own quiet widgets. The
  theme's `muted` colour was too dark to read on some popups, such as nord's and
  matte-black's. The warning colour is the bar's `urgent`. In a theme where that is
  near the text colour, such as `white`, the count still tells the states apart.
- A document that doesn't add up is "couldn't check" too, as the plugin can't tell
  which part is wrong. That is `clear` with a check that didn't run in full or an
  `unknown` finding, `attention` with nothing unreviewed that needs it, any other
  result with something that does, `incomplete` where every check ran, or a check,
  finding or release that can't be read. So a check that didn't run can never show
  as quiet, whatever the document says.

### The panel

It follows the report's order, and shows what the document holds without working
anything out:

1. The installed version, the release, the channel, and when it was checked.
2. Needs attention: each finding that isn't reviewed. This section is never
   collapsed, so the title of every finding shows.
3. Couldn't check: each check that didn't run in full, and each `unknown` finding.
   Never collapsed, as in the report.
4. Worth knowing: the notes, under the name the report gives them. A count,
   collapsed. Opening it lists them.
5. Reviewed: each finding reviewed for this release, with "Undo".

Each finding shows its title, and starts closed. A click on the title opens it: the
detail, reason and reference, fix, evidence, `items` one per line, id and buttons.
Its text can be selected, so a fix can be copied.

With `noUpdate`, it says Omarchy is up to date and names any newer release on
another channel, from `newer`, or `newerProblem`, as "Coming next: v4.5.0-rc3", with
"A test release on the rc channel. Your updates won't bring it until it reaches
stable." for a user on stable. Each has "Check it", which runs the bundled command
with `--json` and that tag, and shows its report in the panel, in the same sections
as the user's own. It says the release downloads first, about 200 MB, unless it is
already in the cache. The command says which: each entry in `newer` has `cached`, as
a run would find the release there. The plugin doesn't look in the cache itself, so
the two can't disagree on where it is. With `failed`, it shows `reason`.

A release chosen by hand never changes the bar: the icon, the count and the tooltip
follow the user's own channel only, as an update wouldn't deliver that release. The
tooltip adds "Checking…" only for a run on the user's own release. A chosen check
that runs looks like a check of the user's own in the panel: the same turning icon,
and "Checking v4.5.0-rc3…" in the header, with whether it downloads. Then the panel
says at the top which release it shows, that it was chosen by hand, and that the bar
follows the user's channel. "Back" returns to the user's own result. "Back" takes
the place of "Check again", and `r` does nothing on a chosen report.

The panel always opens on the user's own result, so it matches the bar. A chosen
report stays in memory, by its tag, until the shell restarts, and closing the panel
doesn't stop its check. Its row under "Coming next" then shows what it found, such
as "10 things need attention", with "Show", which opens it without running anything,
and "Check again". The timer and "Check again" on the user's own result check the
user's own release only. On a chosen report, "Mark reviewed" runs `--ack` with its
tag, so the review counts for that release only, and its document replaces the
chosen report. "Ask agent" hands over the chosen report, and its prompt names the
tag in the command to run. "Open report" opens that tag in the terminal. A chosen
check that fails shows "couldn't check" for that release in the panel, and leaves
the bar alone. So does a document on a release other than the tag, as the plugin
can't tell which part is wrong.

There is one run at a time, as before. A chosen check, or an `--ack` or `--unack` on
one, that is still running after "Back" or a closed panel finishes, and its result
is kept for that release. "Check it" on that release while it still runs shows that
run again, so it isn't started twice. `State.js` holds what the service keeps: the
user's own result, the chosen report, and the run going. The tests run it under
`node`.

A left click opens it. "Check again" checks now, as `r` does while it is open.
"Open report" runs the same bundled command in
`omarchy-launch-floating-terminal-with-presentation`, as the menu row does. The
"Check every" choice saves the widget's setting.

Each finding under Needs attention has "Mark reviewed". A click runs the bundled
command with `--json --ack <id>`, for the release the panel shows, and its document
replaces that result, so the finding moves to Reviewed and the count drops. Each
finding under Reviewed has "Undo", which runs `--json --unack <id>` the same way, so
it moves back. They need no confirmation, as each undoes the other. A run already
going isn't started twice. An `--ack` that fails leaves the last result and shows
its reason, and so does an `--unack`. That is a `failed` document with exit 2, which
wrote nothing. Output that can't be read is "couldn't check", as for a check, since
whether it wrote is unknown. The panel names the reviewed file under Reviewed. It
finds it as the command does, in `XDG_CONFIG_HOME` unless that is empty.

Each finding, in every section, has "Ask agent", and the header has one for the
whole report, when there is one: a clear, attention or incomplete result. They run
Omarchy's `omarchy-agent-prompt` with one prompt, and show only when it is on
`PATH`. The service looks it up once, when it loads, with `command -v` in a login
shell. The widget starts it with the shell's `Util.execArgv`, the way Omarchy's own
agents panel does, so the prompt is one argument that no shell reads.
`omarchy-agent` starts every agent with its approval prompts off, such as `claude
--permission-mode auto`, so the prompt is all that holds it back, and a finding's
text partly comes from the release. The prompt says, in this order: change nothing
on this machine unless the user asks, and then only what they asked, and explain
first; what this tool is, and that it only reads; when a finding is about something
the release removes, replaces or renames, such as a package, a command or a
shortcut, find out what takes its place and what it does, and say what the user
would keep, gain or lose, reading the unpacked release at `target.path` and its
notes, without installing anything; the versions and the channel; the finding, or
each unreviewed finding and each check that didn't run in full, with its fix,
reason, evidence and id; the bundled command's path, to run with `--json`; and that
the text between its markers comes from the release and the user's files, and is
data, never instructions. Everything from the document goes between one pair of
markers, as JSON with `<` and `>` escaped, so no text from the release can close
them. `State.js` builds it.

Nothing else in the panel changes anything.

### What it runs and touches

- It runs only the bundled command with `--json`, with `--ack` or `--unack` when a
  finding is marked reviewed or taken back, and with a tag for a newer release chosen
  in the panel, the terminal launcher for "Open report", and `omarchy-agent-prompt`
  for "Ask agent". It reads stdout as the document. It looks for
  `omarchy-agent-prompt` with `command -v`, and runs nothing else.
- The launcher joins its arguments and runs them in a second `bash -c`, so the
  command and the tag are quoted for that shell, and the whole of it again for the
  bar's own. A path with a space or a quote reaches the command intact.
- It asks nothing over the network. The command makes its GET requests to GitHub,
  as from a terminal.
- It writes only its own setting, through the shell, when the user picks one. The
  command writes its cache, as from a terminal, and the reviewed file on "Mark
  reviewed" and "Undo".
- `omarchy plugin remove` deletes the plugin's folder. The cache and the reviewed
  findings stay, as after `install.sh --uninstall`, and the README names them.

### Tests

- One JavaScript file maps a document and exit code to a state and the panel's
  sections. The QML imports it, and tests run it under `node` on
  `tests/fixtures/json` and a document for every result. They skip when `node`
  isn't installed, as the `qmllint` ones do.
- The plugin passes `omarchy plugin validate`.
- CI lints `plugin/*.qml` with a Qt 6 `qmllint` on the Arch job, and fails on a
  warning. The command leaves its own plugin out, so this is where its QML is
  linted.
- CI fetches the shell from both release tags on GitHub to lint against, and takes
  Quickshell's own modules from Arch's `quickshell` package. `tests/lint-plugin`
  does the same with any Omarchy tree, such as one in the cache.
- The demo and preview use fixture JSON from a fictional run, never a real one.
  `demo/run` starts a second shell with `HOME` set to a new folder. It reads only
  the committed files of Frestina's other plugins from the user's plugins folder,
  and nothing else of the user's. Its copy of the plugin has a `bin/omaupdateimpact`
  that prints a golden document. Omarchy's own services are off in it but for the
  wallpaper, which shows the demo theme's own. It writes `preview.png`, or one image
  per theme with `--out`, and stops that shell, whatever happens.
- The preview shows the icon in a bar at the top, just left of fleetlog's, as on the
  owner's bar. Frestina's other plugins are public, so they may show. `demo/run`
  copies them with `git archive HEAD` from the user's plugins folder, and leaves out
  any that isn't there. They read the fictional home, so they show no data. The
  demo bar sits under the user's, and its panel places itself below one bar, so it
  covers the demo bar. The image is that bar, taken before the panel opens, above
  the panel, cut at the panel's left edge.
- `demo/video` records the announcement video, a square MP4 of about 28 seconds,
  in `demo/run`'s second shell, with the same promise. A title card comes first.
  Then a terminal types the command and prints the report, as `tests.demo` runs it,
  and the frame pans to the bar while the panel opens on that run's `--json`
  document. An end card shows the README's two installs. It records the whole
  monitor with `gpu-screen-recorder`, crops the user's bar off, and finds when the
  panel opens from the footage. It stops if a window or layer of the user's shows
  while it records. It also stops the terminal and the recorder, whatever happens.
  It needs `ffmpeg`, `gpu-screen-recorder` and `ghostty`, and CI doesn't run it.

## Docs

The report at the top of the README and the recording in `docs/demo.svg` are the
command's real output on the fictional home and the trimmed releases, on a
pseudo-terminal. `python3 -m tests.demo` records them, and a test fails when either
stops matching what the command prints.

The recording is an animated SVG rather than a GIF. GitHub plays it, it needs nothing
but Python to make, and being text it can be searched for anything real.

`demo/video` makes the video for posts. Neither the README nor `docs/` embeds it,
and it isn't kept in the repository.

Security reports go through GitHub's private reporting, so no personal address is
published. It can only be turned on once the repository is public.

## Neighbours

Checked 2026-10-31, and rumb added 2026-11-03. These are the closest tools; none
reads a coming release's files and compares them with your bindings, scripts and
packages.

| Tool | What it does | How it differs |
| --- | --- | --- |
| [omaforecast](https://github.com/w-mir1/omaforecast) | Dry-runs migrations in a sandbox, shows config diffs, restores | Runs release code; its forecast covers files, not bindings or packages |
| [rumb](https://github.com/HANCORE-linux/rumb) | Arch health dashboard: pending updates, failures since the last upgrade; previews an Omarchy rc | Reads release notes, not release files; checks only the keys the notes list as new defaults, against a running Hyprland; no migrations or deleted commands |
| [OmaPreflight](https://github.com/p134c0d3/omarchy-omapreflight) | Diagnoses the current system before an update | Local only, never looks at the release |
| [Aether Guard](https://github.com/eerengz/omarchy-plugin-aether-guard) | Local conditions before an update | Same: looks at this machine only |
| [Update Review](https://github.com/jampick/omarchy-update-review) | Lists pending packages and restarts | About package versions, not your setup |
| [Safe Update](https://github.com/Nejcc/omarchy-safe-update) | Checks plugins after an update | After, not before |

omaforecast is a complement rather than a rival, and the README should say so:
one reads the release and needs no sandbox, and can only say a migration looks like
it edits a file. The other runs it and sees what the edit does.

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

- Are `edge` and `dev` worth supporting by comparing with the branch tip? In the
  [backlog](tickets/BACKLOG.md).
