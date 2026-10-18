---
id: T010
type: task
revision: 1
project: qbit-manage
execution_mode: builder
repository: qbit-manage
epic: E001
derived_from:
  architecture.md: 1
covers:
  - AC-3
  - AC-8
  - AC-9
  - AC-10
  - AC-11
depends_on:
  - T006
execution_budget:
  target_minutes: 45
allowed_paths:
  - tests/core/test_relocation_acceptance_operation.py
created: 2026-10-18
updated: 2026-10-18
---

# T010: Executable acceptance tests for the operational behavior

## Outcome

Every operational scenario of `TST010` runs as an automated test over the existing fakes and
passes: the disabled default, dry run, failure isolation, the reporting contract and the
configuration surfaces.

## Scope

- Implement the scenarios of `TST010` as tests in
  `tests/core/test_relocation_acceptance_operation.py`.
- Cover: both keys absent or false producing no relocation call and the unchanged log lines; a dry
  run reporting intended moves and refusals with no client call; a failed relocation being logged
  and notified without stopping the remaining torrents; per-torrent reporting for relocations and
  refusals; the per-run skip summary carrying counts per reason through
  `config.send_notifications`; and the two keys being present in `modules/config.py`,
  `config/config.yml.sample`, `docs/Config-Setup.md` and `web-ui/js/config-schemas/settings.js`,
  with an invalid value rejected at configuration load.

## Exclusions

- Any change to `tests/factories.py`: a missing fake is a blocker to report.
- The flow scenarios (`TST008`) and the guard scenarios (`TST009`).
- Any production-code change: a failing scenario is a defect in T001 or T004–T006 and is reported.

## Completion criteria

- The five criteria `AC-3`, `AC-8`, `AC-9`, `AC-10` and `AC-11` each have at least one passing test
  matching its scenario.
- The disabled case asserts the absence of every relocation call and compares the produced log lines
  with the pre-feature behavior for the same input.
- The failure case asserts that the remaining torrents of the same run are still processed.
- The reporting case asserts one attribute per relocation and per refusal, no per-torrent attribute
  for skips, and exactly one summary attribute per run, sent through `config.send_notifications`.
- The configuration case asserts the four surfaces from the repository files, not from a mocked
  configuration.

## Verification

- `uv run pytest tests/core/test_relocation_acceptance_operation.py` passes.
- `grep -n "AC-3\|AC-8\|AC-9\|AC-10\|AC-11" tests/core/test_relocation_acceptance_operation.py`
  lists every criterion.
- Failure looks like: a disabled-default test that never enables the keys (proving nothing), or a
  summary asserted on `notify_attr` instead of the direct send.

Covered by `TST010`.
