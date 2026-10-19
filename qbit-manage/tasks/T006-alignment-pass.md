---
id: T006
type: task
revision: 1
project: qbit-manage
execution_mode: builder
repository: qbit-manage
epic: E001
derived_from:
  architecture.md: 1
covers:
  - AC-5
  - AC-6
  - AC-7
  - AC-11
  - AC-12
depends_on:
  - T005
execution_budget:
  target_minutes: 45
allowed_paths:
  - modules/core/category.py
  - tests/core/test_category_relocation_alignment.py
  - tests/factories.py
risk: irreversible
created: 2026-10-18
updated: 2026-10-18
---

# T006: Align already-categorized torrents with their category's path

## Outcome

With `cat_update_relocate` enabled, a completed torrent that already carries a category but sits
outside that category's configured path is relocated to it, without its category being changed.

## Scope

- `align_locations()`: iterate the client's torrents with the same status filter the command uses,
  restricted to `self.hashes` when the run was invoked with hashes, take the ones with a non-empty
  category other than the `Uncategorized` mapping, evaluate `relocation_plan` with the alignment
  path selected, and relocate or skip accordingly. No `set_category` call exists in this pass. Under
  `self.config.dry_run` the pass still evaluates and logs the intended move or refusal but calls
  neither `relocate` nor any other client write, exactly as the category-change path does.
- Wire both calls from `Category.__init__`, after `category()` and after `change_categories()`, and
  before the notification call at `modules/core/category.py:25`:
  - `align_locations()` only when `cat_update_relocate` is enabled;
  - `relocation_skip_summary()` (T004) whenever either relocation key is enabled, so a run that
    enables only `cat_change_relocate` still reports the skips its category-change path collected.
- Log a closing summary line with the counts per reason from the same counters the summary uses.
- Unit tests in `tests/core/test_category_relocation_alignment.py`.

## Exclusions

- The guard rules (`T003`), the execution and reporting (`T004`) and the category-change path
  (`T005`).
- Reassigning categories for these torrents: their category is trusted as correct.
- Any change to `change_categories()` beyond the call-site order fixed here.

## Completion criteria

- A completed, non-ATM torrent whose category has a literal configured path different from its save
  path receives exactly one `set_location` with that path, and no `set_category`.
- A torrent whose category is `Uncategorized`, or whose category has no entry in `cat:`, or whose
  entry is a glob or a list, is skipped with the reason logged and counted, and receives no call.
- An incomplete torrent and an ATM torrent are skipped with their reasons and counted, and receive
  no call.
- A torrent already at its category's configured path receives no call and is counted as already in
  place.
- The pass runs after `category()` and after `change_categories()`, and its notifications and
  counters are included in the run payload built at `modules/core/category.py:25`.
- Under `dry_run` the pass logs the intended move or the refusal and calls `set_location` for
  nothing.
- A run with `cat_change_relocate` enabled and `cat_update_relocate` disabled sends exactly one skip
  summary attribute when its category-change path counted a skip, and none when it counted none.
- With `cat_update_relocate` disabled, the pass is not invoked at all and no extra client call is
  made (a torrent list is not fetched).

## Verification

- `uv run pytest tests/core/test_category_relocation_alignment.py` passes.
- `uv run pytest tests/core/test_category.py tests/core/test_category_delay.py` still passes: the
  alignment pass must not perturb the existing paths when disabled.
- Failure looks like: a `cat_change` candidate being relocated twice (first to its old category's
  path, then to the new one), or the pass running after the notification call so its results never
  leave the run.

Covered by `TST006`.
