---
id: T009
type: task
revision: 1
project: qbit-manage
execution_mode: builder
repository: qbit-manage
epic: E001
derived_from:
  architecture.md: 1
covers:
  - AC-4
  - AC-5
  - AC-6
  - AC-7
  - AC-13
  - AC-14
depends_on:
  - T006
execution_budget:
  target_minutes: 45
allowed_paths:
  - tests/core/test_relocation_acceptance_guards.py
created: 2026-10-18
updated: 2026-10-18
---

# T009: Executable acceptance tests for the relocation guards

## Outcome

Every guard scenario of `TST009` runs as an automated test over the existing fakes and passes,
including the distinction between a refusal and a no-op.

## Scope

- Implement the scenarios of `TST009` as tests in `tests/core/test_relocation_acceptance_guards.py`,
  using the factories extended by T002–T006 and the `Category` class as it is after T006.
- Cover, one test each: a cross-seed refusal withholding both the category change and the move in
  the category-change path, and withholding only the move in the alignment pass; an ambiguous
  configured path (glob and `Uncategorized` list) skipped with the category change still applied; a
  torrent already at its configured path not moved and still categorized; an incomplete torrent not
  moved and still categorized; an ATM-on torrent not moved, categorized, and reported with the
  Automatic Torrent Management reason; a `force_auto_tmm` torrent with no ignore tag not moved in
  the category-change path while one with an ignore tag is moved.
- Assert the reported reason for each skip, so the ordering rule that decides it is pinned.

## Exclusions

- Any change to `tests/factories.py`: a missing fake is a blocker to report.
- The flow scenarios (`TST008`) and the operational scenarios (`TST010`).
- Any production-code change: a failing scenario is a defect in T003–T006 and is reported.

## Completion criteria

- The six criteria `AC-4`, `AC-5`, `AC-6`, `AC-7`, `AC-13` and `AC-14` each have at least one
  passing test matching its scenario.
- The refusal tests assert that `set_category` was not called for the refused torrent, while the
  no-op tests assert that it was.
- The reason asserted for each skip matches the guard that decided it, including the Automatic
  Torrent Management reason for a torrent that is also incomplete.
- No test asserts on a live client.

## Verification

- `uv run pytest tests/core/test_relocation_acceptance_guards.py` passes.
- `grep -n "AC-4\|AC-5\|AC-6\|AC-7\|AC-13\|AC-14" tests/core/test_relocation_acceptance_guards.py`
  lists every criterion.
- Failure looks like: a refusal test that only checks the absent `set_location` without checking
  `set_category`, or an ATM skip asserted with the incomplete reason.

Covered by `TST009`.

## Evidence

- Pull request: https://github.com/xelgand/qbit_manage/pull/13
- Commit: `f29376f` (test(T009): cover every relocation guard and its reason)
- Merge: `92edb17cc0b94fd6f4dae14bd1e997ab20f61364` into `specbound/E001-relocate-torrents-to-category-path`
