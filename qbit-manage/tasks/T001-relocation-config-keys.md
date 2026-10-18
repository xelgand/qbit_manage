---
id: T001
type: task
revision: 1
project: qbit-manage
execution_mode: builder
repository: qbit-manage
epic: E001
derived_from:
  architecture.md: 1
covers:
  - AC-10
execution_budget:
  target_minutes: 30
allowed_paths:
  - modules/config.py
  - config/config.yml.sample
  - docs/Config-Setup.md
  - web-ui/js/config-schemas/settings.js
  - tests/test_config.py
created: 2026-10-18
updated: 2026-10-18
---

# T001: Register the two relocation keys on all four configuration surfaces

## Outcome

`settings.cat_update_relocate` and `settings.cat_change_relocate` exist as booleans that default to
`false`, are documented in the sample configuration and the setup documentation, and are editable
in the web UI's settings form.

## Scope

- Register both keys in the `self.settings` block of `modules/config.py`
  (`check_for_attribute(..., parent="settings", var_type="bool", default=False)`), next to
  `cat_filter_completed` and `cat_update_all`.
- Document both keys in `config/config.yml.sample` with a comment saying what each one enables and
  that relocation moves data on disk.
- Add both keys to the relevant table in `docs/Config-Setup.md` under `settings`.
- Add both keys to `web-ui/js/config-schemas/settings.js` so the config editor renders them.
- Add unit tests to `tests/test_config.py` for the default and for an explicit value.

## Exclusions

- Reading the keys in `modules/core/category.py`: that is T003 and T005.
- Prose about the runtime behavior, its guards and its limitations: that is T007.
- Any change to `modules/qbittorrent.py`.

## Completion criteria

- `Config(...)` loads both keys as `False` when absent from the configuration file.
- Both keys load as `True` when set to `true` in the settings section.
- A non-boolean value for either key fails configuration loading the same way other boolean settings
  do.
- The key names appear in `config/config.yml.sample`, `docs/Config-Setup.md` and
  `web-ui/js/config-schemas/settings.js`.
- Disabling both keys leaves every other setting untouched.

## Verification

- `uv run pytest tests/test_config.py` passes, including the new cases.
- `grep -n "cat_update_relocate\|cat_change_relocate" modules/config.py config/config.yml.sample docs/Config-Setup.md web-ui/js/config-schemas/settings.js`
  lists the two keys in all four files.
- Failure looks like: a key missing from one surface (still `undefined` in the UI form, or absent
  from the sample) or a default of `True`.

Covered by `TST001`.
