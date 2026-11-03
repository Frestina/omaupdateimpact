# Omarchy release files

Trimmed copies of two real Omarchy releases, for the end-to-end tests. Every file is
unchanged, and sits at the path it has in the release. Files are only left out.

| Folder | Source tag |
| --- | --- |
| `v4.0.6` | [v4.0.6](https://github.com/omacom/omarchy/tree/v4.0.6) |
| `v4.5.0-rc2` | [v4.5.0-rc2](https://github.com/omacom/omarchy/tree/v4.5.0-rc2) |

Omarchy is MIT licensed. Its license is in [LICENSE](LICENSE), unchanged.

What was kept:

- `default/hypr/helpers.lua`, `default/hypr/bindings/` and, in v4.5.0-rc2,
  `default/hypr/monitor-workspaces.lua`: every file that binds a key or names a
  binding helper.
- In v4.5.0-rc2, `migrations/`: the 29 that touch packages. With no migrations run,
  these give the same removals as the whole release.
- `bin/`: the six commands v4.5.0-rc2 deletes, `omarchy-system-lock` in both, and the
  `omarchy-install-ai-t3-code` that a migration reaches.
- `install/user/first-run/install-voxtype.hook`, which the fictional home holds a
  copy of.
- `config/imv/config` in both: the default of a file a v4.5.0-rc2 migration edits,
  which the fictional home holds a changed copy of.
- One migration in v4.0.6 and `shell/README.md` in both, because a tree needs
  something in each folder.

With an empty home, the report on these trees was the same as on the full releases
when they were trimmed.

These files are read as text. Nothing in them is run.
