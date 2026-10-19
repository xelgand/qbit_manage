---
id: TST001
type: test
revision: 1
project: qbit-manage
kind: unit
verifies:
  - T001
derived_from:
  tasks/T001-relocation-config-keys.md: 1
execution:
  mode: automated
  environment: local
  command: uv run pytest tests/test_config.py
created: 2026-10-18
updated: 2026-10-18
---

# TST001: The two relocation keys load as booleans and default to false

## Purpose

Proves that `cat_update_relocate` and `cat_change_relocate` are registered settings with the right
type and default. Without it, a missing registration would surface only as a `KeyError` deep inside
the category command, after a user had already enabled the feature.

## Preconditions

- The configuration fixture used by `tests/test_config.py` and the settings section handling it.
- The keys registered in `modules/config.py` (T001).

## Procedure

1. Load a configuration whose settings section omits both keys and assert both are `False`.
2. Load a configuration with `cat_update_relocate: true` and `cat_change_relocate: true` and assert
   both are `True`.
3. Load a configuration with a non-boolean value for each key in turn and assert the load fails the
   way other boolean settings fail.
4. Assert the two key names appear in `config/config.yml.sample`,
   `docs/Config-Setup.md` and `web-ui/js/config-schemas/settings.js`.

## Expected result

All four checks pass. A failure reports which key and which surface is wrong: a default of `True`
would enable data movement for every existing user, and a missing UI schema entry would hide the
toggle from the config editor.
