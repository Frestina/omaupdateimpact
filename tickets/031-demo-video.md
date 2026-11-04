---
id: "031"
title: Record the demo video
milestone: M4 Plugin
depends_on: ["023"]
---

# 031 Record the demo video

## Goal

Make the announcement video again with one command, after any change to the report
or the panel, as `demo/run` does for `preview.png`.

The owner asked for this after the video for the 0.2.0 announcement, which was made
by hand from a draft script.

## Spec

- [Plugin](../SPEC.md#plugin): Tests, the demo bullets
- [Docs](../SPEC.md#docs)

## Scope

- `demo/video` records a square MP4 of about 28 seconds:
  1. A title card.
  2. A terminal types `omaupdateimpact v4.5.0-rc2` and the report prints, on the
     fictional home and the trimmed releases, as `tests.demo` runs it.
  3. The frame pans to the bar, whose icon shows the count, and the panel opens on
     the `--json` document of that same run.
  4. An end card with both installs, as in the README.
- Start from the reviewer's working draft in `audits/video-draft/` (git ignores
  it): `record.py` records, and `post.sh` edits with `ffmpeg`. Make it one Python
  script in the shape of `demo/run`. Reuse its functions rather than copy them, with
  no paths from the owner's machine, and with the same promise: a second shell with a
  new `HOME`, an empty workspace, and everything stopped and deleted whatever
  happens.
- What the draft learned:
  - `gpu-screen-recorder -w <monitor>` records the monitor. The GPU encoder here
    refuses h264, so it needs `-encoder cpu`, at 30 fps. Without that, no file is
    written and no error is shown.
  - The demo shell needs `PYTHONDONTWRITEBYTECODE=1`, or a neighbour plugin's first
    run writes `__pycache__` into its folder, the shell reloads it about 40 times,
    and our plugin never shows a result. Reported to fleetlog.
  - Ghostty at `--font-size=9.5`, with `--config-default-files=false` and the demo
    theme's `ghostty.conf`, fits the whole report on a 1280×800 logical screen.
  - Call `check` again once the terminal is up, then wait for a result before
    recording.
  - The owner's bar is cropped off, so only the demo bar shows.
- Find the panel's moment from the footage, or from when `summon` is called, not
  from a fixed time.
- Like `demo/run`, it needs `ffmpeg`, `gpu-screen-recorder` and `ghostty`, and says
  which one is missing. CI doesn't run it.
- The README or `docs/` doesn't embed the video. It is for posts, so it isn't kept
  in the repository.

## Done when

- [x] `demo/video` writes the MP4, with a fictional home and nothing of the owner's
      in it but the neighbour plugins, as committed, as for `preview.png`.
- [x] A run that fails or is stopped leaves no second shell, terminal, recorder or
      folder behind, and goes back to the workspace it started on.
- [x] The spec's Tests bullets name `demo/video`.
- [x] `tests/run` passes.
