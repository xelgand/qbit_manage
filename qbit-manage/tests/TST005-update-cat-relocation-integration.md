---
id: TST005
type: test
revision: 1
project: qbit-manage
kind: unit
verifies:
  - T005
derived_from:
  tasks/T005-update-cat-relocation-integration.md: 1
execution:
  mode: automated
  environment: local
  command: uv run pytest tests/core/test_category_relocation_update_cat.py
created: 2026-10-18
updated: 2026-10-18
---

# TST005: The category-change path relocates after the change, refuses before it, and stays inert when disabled

## Purpose

Proves the call order that keeps the feature safe: a refusal must reach the client before
`set_category`, and a relocation must follow a successful category change. It also proves the
feature is invisible when the keys are off, which is the promise made to every existing user.

## Preconditions

- The `Category` and fake torrent from `tests/factories.py`.
- `update_cat` integrated by T005.

## Procedure

1. Relocate: with the key enabled, assert the recorded call order is `set_category` then
   `set_location` with the configured path.
2. Refusal: assert neither call was made for the torrent, and the refusal reason was logged.
3. No-op (already in place, incomplete, ambiguous path, ATM): assert `set_category` was called,
   `set_location` was not, and the skip was reported once with its reason (one log line, one reason
   counter).
4. Dry run: assert the intended move or refusal was logged and neither call was made.
5. Disabled: with both keys absent, assert no `relocation_plan` call, no `set_location` ever, and
   the same log lines as the pre-change code for the same input.
6. Path selection: assert the plan is told which path it is on, so the `force_auto_tmm` rule applies
   to the category-change path and not to the alignment pass.

## Expected result

All cases pass. Failures report the wrong order or a leaked call: a refused torrent receiving
`set_category` would let qBittorrent move the files the guard refused to move.
