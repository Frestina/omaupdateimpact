# A fictional home

A made-up user for the end-to-end tests. Nothing here is real config. The tests add
the installed packages themselves.

| File | Why it's here |
| --- | --- |
| `.config/imv/config` | v4.0.6's default with a binding added, which a v4.5.0-rc2 migration edits |
| `.config/hypr/bindings.lua` | Two clashes with v4.5.0-rc2, one through `o.bind_hold`, one key with no clash, and an unbind of a shortcut that moves |
| `.config/omarchy/hooks/post-update` | Calls a deleted command |
| `.config/omarchy/hooks/first-run/install-voxtype.hook` | An unchanged copy of Omarchy's own hook, which calls a deleted command |
| `.config/omarchy/plugins/demo` | The fictional plugin from `qmllint-6.12.0` |
| `.config/systemd/user/nightly-backup.service` | Calls a deleted command |
| `.local/bin/end-of-day` | Calls a deleted command, and names another in a comment |
| `.local/state/omarchy/migrations/1780739888.sh` | A migration already run, so what it removes doesn't count |
| `.bashrc` | Calls a deleted command |
