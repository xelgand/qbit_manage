---
id: T008
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
  - AC-12
depends_on:
  - T006
execution_budget:
  target_minutes: 45
allowed_paths:
  - tests/core/test_relocation_acceptance_flows.py
created: 2026-10-18
updated: 2026-10-18
---

# T008: Executable acceptance tests for the relocation flows

## Outcome

Every acceptance scenario of `TST008` runs as an automated test over the existing fakes and passes
on the finished feature.

## Scope

- Implement the scenarios of `TST008` as tests in `tests/core/test_relocation_acceptance_flows.py`,
  using the factories extended by T002–T006 and the `Category` class as it is after T006.
- One test per scenario, named so the criterion it proves is readable, with the `given`/`when`/
  `then` of the scenario expressed in the assertions.

## Exclusions

- Any change to `tests/factories.py`: if a fake lacks what a scenario needs, that is a blocker to
  report, not a change to make here.
- The guard scenarios (`TST009`) and the operational scenarios (`TST010`).
- Any production-code change: a scenario that fails reveals a defect in T002–T006 and is reported
  as such.

## Completion criteria

- The three criteria `AC-1`, `AC-2` and `AC-12` each have at least one passing test whose assertions
  match the scenario in `TST008`.
- Each test asserts both the observable move (the recorded `set_location` target) and the category
  expectation of its scenario (changed, or unchanged for the alignment case).
- A test that needs a live qBittorrent instance does not exist here: all of them run on the fakes.

## Verification

- `uv run pytest tests/core/test_relocation_acceptance_flows.py` passes.
- Each criterion is traceable: the test docstring or name states the `AC-N` it proves, and
  `grep -n "AC-1\|AC-2\|AC-12" tests/core/test_relocation_acceptance_flows.py` lists them.
- Failure looks like: a scenario skipped or asserted vacuously, or a criterion with no test.

Covered by `TST008`.
