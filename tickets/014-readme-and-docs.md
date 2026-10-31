---
id: "014"
title: README and project docs
milestone: M2 First release
depends_on: ["012", "013"]
---

# 014 README and project docs

## Goal

Someone landing on the repository understands it in ten seconds and has reason to
trust a tool that reads their config.

## Spec

- [Neighbours](../SPEC.md#neighbours)
- [What must never happen](../SPEC.md#what-must-never-happen)

## Scope

- README: the problem, a real report as the first thing on the page, install,
  usage, what it checks, limits, safety, and how it sits next to omaforecast.
- A short terminal recording made from the fictional fixtures.
- Note that it's unofficial and not affiliated with Omarchy or 37signals.
- `CHANGELOG.md`, `SECURITY.md` and `CONTRIBUTING.md`, with issue templates. A bug
  report asks for the release tag and a redacted report.

## Done when

- [ ] Every command in the README has been run as written.
- [ ] The recording contains no real paths or names.
- [ ] A person who hasn't seen the project installs it from the README alone.
