# qmllint 6.12.0 output

What `qmllint` 6.12.0 really printed for the fictional plugin in `plugin`, kept so
the tests read real output. The only edit is the folder, rewritten to
`/plugins/demo`.

| File | Run | Exit |
| --- | --- | --- |
| `current.txt` | `Demo.qml`, with `shell` as `qs` | 0 |
| `release.txt` | `Demo.qml`, with `qs.Palette` gone from the shell | 0 |
| `syntax-error.txt` | `Broken.qml` | 255 |
| `unreadable-file.txt` | `Demo.qml` and `Gone.qml`, a broken link, with `qs.Palette` gone | 255 |
