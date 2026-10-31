---
id: "013"
title: Install, version and uninstall
milestone: M2 First release
depends_on: ["001"]
---

# 013 Install, version and uninstall

## Goal

Make it one step to install and one step to remove, with no `curl | bash` required.

## Spec

- [Product shape](../SPEC.md#product-shape)

## Scope

- `--version`, read from one place.
- A one-line error on Python older than the minimum. `tarfile`'s `filter=` needs
  3.11.4, so the README's "3.11" is slightly wrong.
- `install.sh`, safe to run twice, that refuses to replace a file that isn't its
  own link. The same script with `--uninstall`.
- Document `--target`, `--root`, `--home` and `--channel` in `--help`.
- An AUR package once 0.1.0 is tagged, so `omarchy pkg aur add` works.

## Done when

- [ ] Installing twice is harmless, and an existing regular file is left alone.
- [ ] Uninstall leaves nothing behind but the cache, and says so.
- [ ] An old Python gets one line, not a traceback.
- [ ] `tests/run` passes.
