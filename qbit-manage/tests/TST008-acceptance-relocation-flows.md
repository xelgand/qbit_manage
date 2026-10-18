---
id: TST008
type: test
revision: 1
project: qbit-manage
kind: acceptance
verifies:
  - spec.md#AC-1
  - spec.md#AC-2
  - spec.md#AC-12
derived_from:
  spec.md: 1
execution:
  mode: automated
  environment: local
  command: uv run pytest tests/core/test_relocation_acceptance_flows.py
created: 2026-10-18
updated: 2026-10-18
---

# TST008: Acceptance — relocating on category assignment, on category change and by alignment

## Purpose

Proves the three ways a torrent is moved to its category's configured path, from the outside: the
observable result is a location change, and the category is changed only where the criterion says
so.

## Preconditions

- The feature implemented and merged (T001–T006).
- Runnable with `uv run pytest tests/core/test_relocation_acceptance_flows.py`.

## Scenario

```gherkin
Feature: Relocating a torrent to its category's configured path

  Scenario: AC-1 relocation follows a category assigned by cat_update
    Given relocation is enabled for cat_update and Automatic Torrent Management is disabled for the torrent
    And the torrent is assigned a category whose configured path differs from its save path
    When cat_update applies the category
    Then the torrent's location is set to that configured path

  Scenario: AC-2 relocation follows a category change
    Given relocation is enabled for cat_change and Automatic Torrent Management is disabled
    And a completed torrent is switched to a category with a different configured path
    When cat_change applies the switch
    Then the torrent's location is set to the new category's configured path

  Scenario: AC-12 an already-categorized torrent is aligned without changing its category
    Given relocation is enabled for cat_update and Automatic Torrent Management is disabled
    And a completed torrent carries a category whose configured path differs from its save path
    When cat_update runs
    Then the torrent's location is set to that configured path
    And its category is left unchanged
```

## Expected result

All three scenarios pass. A failure reports which criterion is unmet: a category change without a
move, a move to the wrong path, or the alignment pass rewriting a category it must leave alone.
