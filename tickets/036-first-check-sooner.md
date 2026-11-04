---
id: "036"
title: Check soon after loading, and wait for the network
milestone: M4 Plugin
depends_on: ["035"]
---

# 036 Check soon after loading, and wait for the network

## Goal

Check within seconds of the shell loading, without a "couldn't check" at every login
before the network is up.

The owner asked why the first check waits 2 minutes. It waits so the network can come
up after login, but after a shell restart the network is already there, and the wait
is only a delay.

## Spec

- [JSON](../SPEC.md#json): `unreachable` on a failed document
- [Plugin](../SPEC.md#plugin): When it checks, What the bar shows

The spec already records each decision below.

## Scope

- **The command.** A failed document has `unreachable`: `true` when no answer came
  from GitHub at all, such as a name that doesn't resolve, a connection refused or
  cut, or a timeout; `false` for every other failure, an answer from GitHub such as a
  rate limit included. That covers the list of releases, the archive and the notes
  wherever they make the run fail. `docs/json.md` and the golden failed document
  change with it. It is an addition, so `schemaVersion` stays 1.
- **The first check** is 5 seconds after the service loads. If its document has
  `unreachable`, the bar stays on "Not checked", with "Waiting for the network…", and
  it tries again a minute later, up to 5 times. After the fifth, or on any other
  failure, it shows "couldn't check" with the reason.
- Only the scheduled first check waits. "Check again", and every later check, show a
  failure at once, as now. With "only when asked", nothing checks by itself, as now.
- README: "It checks 2 minutes after login" changes with it. So does the comment in
  `State.js`.
- CHANGELOG, under Unreleased.

## Done when

- [x] `unreachable` is `true` for a failure with no answer from GitHub, and `false`
      for a rate limit, a rejected token and a failure that isn't a download.
      Tested.
- [x] The first check runs 5 seconds after loading. Tested.
- [x] An unreachable first check keeps "Not checked" with "Waiting for the
      network…", tries again each minute up to 5 times, then shows "couldn't check".
      Tested with fixture JSON.
- [x] "Check again" and later checks show an unreachable failure at once. Tested.
- [x] The plugin still passes `omarchy plugin validate` and CI's QML lint.
- [x] `tests/run` passes.
