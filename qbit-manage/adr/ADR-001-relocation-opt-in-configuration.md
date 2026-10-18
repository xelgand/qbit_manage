---
id: ADR-001
type: adr
status: accepted
revision: 1
project: qbit-manage
derived_from:
  spec.md: 1
  plan.md: 1
created: 2026-10-17
updated: 2026-10-18
---

# ADR-001: Where the relocation opt-in lives and how its keys are named

## Context

`cat_update` and `cat_change` are one command family driven by three configuration surfaces:

- `settings` — a flat block registered key by key through `check_for_attribute`
  (`modules/config.py:394-449`), holding cross-command switches such as `cat_filter_completed`,
  `cat_update_all` and `force_auto_tmm`.
- `cat` — a flat map of category name to save path, read as raw data by `Qbt.get_category`
  (`modules/qbittorrent.py:448-475`) with exact-match and `fnmatch` wildcard support, special-cased
  for `Uncategorized` as a list, and mirrored by the web UI schema as a flat string map
  (`web-ui/js/config-schemas/cat.js`).
- `cat_change` — a map of old category to either a new category name or an object
  `{new_cat, delay_minutes}`, parsed by the pure function `normalize_cat_change`
  (`modules/config.py:88-128`) and mirrored with the same key names by the web UI schema
  (`web-ui/js/config-schemas/cat_change.js`).

The spec requires that relocation can be enabled for `cat_update` and `cat_change` independently
(RF-1, RF-2) and that each new key reaches all four configuration surfaces (RF-5). The choice fixes
how much of the existing parsing and UI code has to change.

## Question

Which configuration surface holds the relocation opt-in, and what are the exact key names?

## Options

### Option A: Two global `settings` keys

Add `cat_update_relocate` and `cat_change_relocate` (bool, default `false`) to the `settings` block
next to `cat_filter_completed` and `cat_update_all`.

- Gives: independent enablement per command as the spec requires; follows the established
  `settings` pattern exactly; touches only four surfaces (`modules/config.py`,
  `config/config.yml.sample`, `docs/Config-Setup.md`, `web-ui/js/config-schemas/settings.js`); no
  change to `normalize_cat_change`, to the `cat` map shape or to the category dropdown UI.
- Costs: the granularity stops at the command — a user cannot exempt one category or one
  `cat_change` mapping without disabling relocation for the whole command.

### Option B: One global `settings` key plus a per-mapping override

Add `cat_relocate` (bool, default `false`) to `settings`, plus an optional `relocate` key in the
`cat_change` extended form that overrides it per mapping.

- Gives: a single switch for the common case and per-mapping exceptions where they matter.
- Costs: `normalize_cat_change` gains a third key and validation branch, the `cat_change` web UI
  schema needs the field in two places (the `patternProperties` and the `additionalProperties`
  mirror), and `cat_update` still has no per-category granularity, so the model is asymmetric.

### Option C: A per-category flag inside `cat`

Turn each `cat` entry into an object (`{path, relocate}`) instead of a string.

- Gives: the finest granularity, attached to the entity that owns the path.
- Costs: breaks the flat map shape that `Qbt.get_category`, the `Uncategorized` list special case
  and the `cat` web UI schema all assume; requires a migration path for existing configs and every
  reader of `config.data["cat"]`. The `cat` section describes where categories live; policy about
  moving files does not belong in it.

### Option D: Per-mapping flag only in `cat_change`, plus a `settings` key for `cat_update`

Add `relocate` to the `cat_change` extended form and `cat_update_relocate` to `settings`.

- Gives: independent enablement plus per-mapping control for the command that has a natural
  per-entry structure.
- Costs: two different configuration shapes for one feature; both `cat_change` UI schemas change,
  as in Option B.

## Decision

Option A: two global `settings` keys, `cat_update_relocate` and `cat_change_relocate`, both
boolean and defaulting to `false`. Decided by the approver on 2026-10-18.

The spec requires independent enablement per command (RF-1, RF-2) and a key only has to reach four
documented surfaces (RF-5). Option A satisfies both with the least machinery: no change to
`normalize_cat_change`, no change to the flat `cat` map that `Qbt.get_category`, the
`Uncategorized` list special case and the `cat` web UI schema depend on, and one settings schema
entry per key. Options B and D pay for per-entry granularity the spec does not ask for, and Option
C breaks the shape of the section that describes where categories live.

## Consequences

- Two independent switches, one per command; a user cannot exempt a single category or a single
  `cat_change` mapping without disabling relocation for the whole command.
- The two keys join the `settings` block and are documented on the four surfaces AGENTS.md
  requires: `modules/config.py`, `config/config.yml.sample`, `docs/Config-Setup.md` and
  `web-ui/js/config-schemas/settings.js`.
- `normalize_cat_change` and the `cat_change` web UI schema stay untouched, so the extended
  `cat_change` form keeps exactly two keys.
- With both keys absent or `false`, no relocation code path is reachable (RNF-1).

## References

- `qbit-manage/spec.md` — RF-1, RF-2, RF-5.
- `modules/config.py:88-128`, `modules/config.py:394-449`, `modules/qbittorrent.py:448-475`.
- `web-ui/js/config-schemas/cat.js`, `web-ui/js/config-schemas/cat_change.js`.
- `AGENTS.md`, "Adding a Configuration Key" — the four surfaces a key must reach.
