---
id: "022"
title: Bar widget and panel
milestone: M4 Plugin
depends_on: ["021", "028"]
---

# 022 Bar widget and panel

## Goal

Show the result on the desktop, for people who would never run the CLI.

## Spec

- [Product shape](../SPEC.md#product-shape)
- [Plugin](../SPEC.md#plugin), which 021 decided

## Scope

- Build what 021 decided, using the `omarchy-bar-widget` and
  `omarchy-qml-patterns` skills.
- A panel showing attention findings first, each with its fix, and the rest
  collapsed.
- A clear "couldn't check" state for exit 2 and 3. It must never look like clear.
- A button that runs the check again. No button changes the system.
- A fictional demo and preview image, using the `omarchy-plugin-demo` skill.

## Done when

- [ ] Every exit code has a state in the panel, tested with fixture JSON.
- [ ] The plugin passes `omarchy plugin validate` and the `omarchy-plugin-test`
      checks.
- [ ] CI's Arch job lints `plugin/*.qml` with a Qt 6 `qmllint` and fails on a
      warning.
- [ ] It works in every theme tried, using theme tokens only.
- [ ] Nothing in the demo is real data.
