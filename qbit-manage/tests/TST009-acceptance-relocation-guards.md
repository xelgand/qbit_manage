---
id: TST009
type: test
revision: 1
project: qbit-manage
kind: acceptance
verifies:
  - spec.md#AC-4
  - spec.md#AC-5
  - spec.md#AC-6
  - spec.md#AC-7
  - spec.md#AC-13
  - spec.md#AC-14
derived_from:
  spec.md: 1
execution:
  mode: automated
  environment: local
  command: uv run pytest tests/core/test_relocation_acceptance_guards.py
created: 2026-10-18
updated: 2026-10-18
---

# TST009: Acceptance — every guard refuses or skips exactly what the spec says

## Purpose

Proves the conditions under which the feature does nothing, and the one condition under which it
does nothing at all — including the category change. This is the set of criteria that decides
whether the feature can lose data or fight the client, so each guard is asserted with both its
effect and its reported reason.

## Preconditions

- The feature implemented and merged (T001–T006).
- Runnable with `uv run pytest tests/core/test_relocation_acceptance_guards.py`.

## Scenario

```gherkin
Feature: Guards that stop a relocation

  Scenario: AC-4 a cross-seed sibling withholds the move and the category change
    Given a torrent whose files are shared with a cross-seed sibling
    When relocation would apply in the category-change path
    Then neither the category change nor the relocation is requested for it
    And the skip is logged and notified with the cross-seed reason

  Scenario: AC-4 a cross-seed sibling withholds only the move in the alignment path
    Given a torrent whose files are shared with a cross-seed sibling and a category already set
    When the alignment pass evaluates it
    Then the relocation is withheld and the skip is logged with the cross-seed reason
    And no category is written

  Scenario: AC-5 an ambiguous configured path is skipped and the category change still applies
    Given a category whose configured path is a glob pattern or an Uncategorized list of paths
    When relocation would target it
    Then the relocation is skipped and the ambiguity is logged
    And the category change is applied as before

  Scenario: AC-6 a torrent already in place is not moved
    Given a torrent already located at its category's configured path
    When relocation is evaluated
    Then no relocation request is issued for it
    And the category change is applied as before

  Scenario: AC-7 an incomplete torrent is not relocated
    Given a torrent that has not completed downloading
    When relocation is evaluated
    Then it is not relocated
    And the category change is applied as before

  Scenario: AC-13 an Automatic Torrent Management torrent is not relocated
    Given Automatic Torrent Management is enabled for a torrent
    When relocation is evaluated
    Then no location change is requested for it
    And the skip is logged with the Automatic Torrent Management reason and counted in the run's skip summary

  Scenario: AC-14 a torrent the category change hands to Automatic Torrent Management is not relocated
    Given force_auto_tmm is enabled and the torrent carries no ignore tag from force_auto_tmm_ignore_tags
    When the category-change path evaluates relocation
    Then no location change is requested for that torrent
    And the skip is logged with that reason and counted in the run's skip summary
```

## Expected result

All scenarios pass. A failure reports which criterion is unmet: a refused torrent that still
received a category change is the most serious, because qBittorrent can then perform the move the
guard refused.
