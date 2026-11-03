---
id: "021"
title: Plugin design
milestone: M4 Plugin
depends_on: ["016"]
---

# 021 Plugin design

## Goal

Decide what the plugin is before writing QML. Use the `omarchy-plugin-design` skill.

## Spec

- [Product shape](../SPEC.md#product-shape)
- [Open questions](../SPEC.md#open-questions)

## Scope

Decide and record in the spec:

- One repository or two. Default: one, with the manifest beside the CLI, as other
  Frestina plugins do.
- How the plugin gets the CLI: bundled in the plugin or installed separately.
- When the check runs. It should be rarely, such as when an update is available,
  and never on a tight timer: it downloads 200 MB on a new release.
- The bar's states: quiet when clean, a mark when something needs attention.
- The plugin holds no rules. It only renders `--json`.
- The permanent plugin id, which can't change later.
- Review follow-ups: the clone sits where the command looks, so the command leaves
  its own files out. The user chose this, the spec records it, and 028 builds it.

## Done when

- [x] Each decision above is in the spec, with the reason.
- [x] 022 can be built without another design decision.
- [x] `tickets/BACKLOG.md` no longer lists "Two runs at once", which is 027 now.
