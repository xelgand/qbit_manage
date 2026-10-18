---
id: TST003
type: test
revision: 1
project: qbit-manage
kind: unit
verifies:
  - T003
derived_from:
  tasks/T003-category-relocation-plan.md: 1
execution:
  mode: automated
  environment: local
  command: uv run pytest tests/core/test_category_relocation_plan.py
created: 2026-10-18
updated: 2026-10-18
---

# TST003: Each relocation guard produces its own outcome, in order

## Purpose

Proves the guard ladder and, above all, that only the cross-seed condition refuses. A guard
misclassified as a refusal silently withholds category changes; one misclassified as a no-op moves
data that should stay.

## Preconditions

- The `Category` built through `tests/factories.py` with the fields the rules read.
- The rules of T003 and the primitives of T002.

## Procedure

1. Rule 1: an `auto_tmm` torrent returns the Automatic Torrent Management no-op; an ATM-off torrent
   returns it too when the category-change path is selected, `force_auto_tmm` is on and no ignore
   tag matches; it does not return it when an ignore tag matches, nor when the alignment path is
   selected.
2. Rule 2: an absent category, a list value and a glob value each return the no-configured-path
   no-op.
3. Rule 3: an incomplete torrent returns the incomplete no-op.
4. Rule 4: normalized equal paths return the already-in-place no-op.
5. Rule 5: a shared file returns the refusal; peers with disjoint files do not.
6. Ordering: an ATM torrent that is also incomplete returns the Automatic Torrent Management reason;
   a torrent with an absent configured path and a shared file returns the no-configured-path no-op
   without consulting the peer check.
7. Every case: assert no `set_location` call was recorded, and that no client call was made when
   rules 1–4 already decided.

## Expected result

All cases pass with the exact reason asserted. Failures report the wrong reason or the wrong class:
a no-op reported as a refusal would withhold a category change, and a refusal reported as a no-op
would let a shared file be moved.
