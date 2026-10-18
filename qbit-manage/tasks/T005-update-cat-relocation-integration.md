---
id: T005
type: task
revision: 1
project: qbit-manage
execution_mode: builder
repository: qbit-manage
epic: E001
derived_from:
  architecture.md: 1
covers:
  - AC-1
  - AC-2
  - AC-3
  - AC-8
depends_on:
  - T004
execution_budget:
  target_minutes: 45
allowed_paths:
  - modules/core/category.py
  - tests/core/test_category_relocation_update_cat.py
  - tests/factories.py
risk: irreversible
created: 2026-10-18
updated: 2026-10-18
---

# T005: Integrate relocation into the category-change path

## Outcome

When `cat_update_relocate` or `cat_change_relocate` is enabled, the category-change path evaluates
the relocation plan before it changes anything, refuses the whole torrent when the plan is a
refusal, and moves the data after the category change succeeded; with both keys disabled, the path
behaves exactly as before.

## Scope

- In `update_cat(torrent, new_cat, cat_change)`:
  - evaluate `relocation_plan` before the existing `if not self.config.dry_run:` block when
    `relocation_enabled(cat_change)` is true, and on a refusal log, notify and return without
    calling `set_category` or `set_location`;
  - after `set_category` has succeeded, inside the same dry-run guard, call `relocate(torrent,
    target)` for a relocate outcome;
  - leave the rest of the method (logging, `notify_attr` for the category update, counters) as it
    is.
- Keep the existing behavior identical when both keys are absent or false: no plan is evaluated, no
  `set_location` is ever called, and the logged lines are the current ones.
- Unit tests in `tests/core/test_category_relocation_update_cat.py` covering: relocation after a
  category change, refusal withholding both calls, no-op leaving the category change alone, dry-run
  reporting without any client call, and the disabled case.

## Exclusions

- The alignment pass: T006.
- The rules and their reasons: T003. The execution, notification shape and counters: T004.
- Changing the existing pre-filters of `category()` (`auto_tmm and category` skip, the
  `cat_update_all` and category filters): they stay exactly as they are.

## Completion criteria

- With the matching key enabled and a relocate outcome, the order of calls on the fake torrent is
  `set_category` then `set_location` with the configured path.
- With the matching key enabled and a refusal, neither `set_category` nor `set_location` is called
  for that torrent, and the refusal is logged and notified with its reason.
- With the matching key enabled and a no-op outcome, `set_category` is called and `set_location` is
  not.
- Under `dry_run` with the key enabled, the intended move or refusal is logged and neither
  `set_category` nor `set_location` is called.
- With both keys absent or false, the recorded calls and the log lines are exactly what the
  pre-change code produced for the same input, and `relocation_plan` is never called.
- `cat_change` passes the category-change path to the plan, so the `force_auto_tmm` rule applies
  there and not in the alignment path.

## Verification

- `uv run pytest tests/core/test_category_relocation_update_cat.py` passes, and
  `uv run pytest tests/core/test_category.py tests/core/test_category_delay.py` still passes
  unchanged, which is the backwards-compatibility evidence for AC-3.
- Failure looks like: `set_location` observed before `set_category`, a refused torrent still
  receiving `set_category`, or a dry run issuing a client call.

Covered by `TST005`.
