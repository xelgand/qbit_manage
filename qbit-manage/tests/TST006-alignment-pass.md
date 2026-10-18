---
id: TST006
type: test
revision: 1
project: qbit-manage
kind: unit
verifies:
  - T006
derived_from:
  tasks/T006-alignment-pass.md: 1
execution:
  mode: automated
  environment: local
  command: uv run pytest tests/core/test_category_relocation_alignment.py
created: 2026-10-18
updated: 2026-10-18
---

# TST006: The alignment pass moves mislocated torrents without touching their category

## Purpose

Proves the part of the library the category filters never reach is actually covered, and that
covering it writes no category. It also pins the call-site order that prevents a double move of a
`cat_change` candidate.

## Preconditions

- The `Category` and fake torrent from `tests/factories.py`.
- The alignment pass of T006, with the guards of T003 and the reporting of T004.

## Procedure

1. A completed, non-ATM torrent with a category whose configured path differs from its save path:
   assert exactly one `set_location` with that path and no `set_category`.
2. `Uncategorized`, a category absent from `cat:`, a glob value and a list value: assert no call, the
   reason logged, and the corresponding counter incremented.
3. An incomplete torrent and an ATM torrent: assert no call, the reason logged and counted.
4. A torrent already at its configured path: assert no call and the already-in-place count.
5. Order: construct a `Category` whose torrent is a `cat_change` candidate and assert it is
   relocated once, to the new category's path.
6. Payload: assert the pass's relocations and skips reach the run payload built after it.
7. Disabled: with `cat_update_relocate` false, assert the pass is not invoked and no extra client
   list is fetched.

## Expected result

All cases pass. Failures report either a category written by the alignment pass, a double move, or
results that never reach the run payload because the pass ran after the notification call.
