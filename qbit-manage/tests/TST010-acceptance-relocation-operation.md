---
id: TST010
type: test
revision: 1
project: qbit-manage
kind: acceptance
verifies:
  - spec.md#AC-3
  - spec.md#AC-8
  - spec.md#AC-9
  - spec.md#AC-10
  - spec.md#AC-11
derived_from:
  spec.md: 1
execution:
  mode: automated
  environment: local
  command: uv run pytest tests/core/test_relocation_acceptance_operation.py
created: 2026-10-18
updated: 2026-10-18
---

# TST010: Acceptance — the feature is off by default, safe under dry run and failure, and reported

## Purpose

Proves the promises that protect existing users and operators: nothing changes without the opt-in,
a rehearsal moves nothing, one failure does not stop a run, and the run says what it did.

## Preconditions

- The feature implemented and merged (T001–T006).
- Runnable with `uv run pytest tests/core/test_relocation_acceptance_operation.py`.

## Scenario

```gherkin
Feature: Operating the relocation feature

  Scenario: AC-3 without the keys nothing is relocated and the run behaves as before
    Given the relocation keys are absent or disabled
    When cat_update or cat_change runs
    Then no location change is requested for any torrent
    And the logged behavior matches the pre-feature behavior

  Scenario Outline: AC-8 a dry run reports the intended moves and refuses to make them
    Given dry_run is active and relocation is enabled
    And the relocation would apply through <entry point>
    When the run proceeds
    Then the intended move is logged
    And no location change is requested

    Examples:
      | entry point           |
      | the category change   |
      | the alignment pass    |

  Scenario: AC-9 one failed relocation does not stop the run
    Given the relocation request fails for one torrent
    When the run continues
    Then the failure is logged and notified
    And the remaining torrents are still processed

  Scenario: AC-10 the keys are validated and documented on every surface
    Given an invalid value for a new relocation key
    When the configuration is loaded
    Then it is rejected with the same error behavior as other invalid configuration keys
    And the keys appear in the sample config, the setup docs and the web UI schema

  Scenario: AC-11 the run reports what it moved, refused and skipped
    Given relocation is enabled
    When a run relocates torrents, refuses a relocation or skips one for any reason
    Then the log identifies each affected torrent with its reason
    And relocations and refusals each appear in the notification payload
    And every other skip appears in a single per-run summary entry carrying the count per reason

  Scenario: AC-11 a run that enables only cat_change still reports its skips
    Given cat_change_relocate is enabled and cat_update_relocate is disabled
    And the category-change path skips torrents for at least one reason
    When the run proceeds
    Then a single per-run summary entry carries the count per reason
    And the alignment pass did not run
```

## Expected result

All scenarios pass. A failure reports which criterion is unmet: a default that moves data, a dry run
that issues a call, an aborted run after one failure, or a run whose skips are invisible.
