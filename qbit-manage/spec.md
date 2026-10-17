---
type: spec
revision: 1
project: qbit-manage
created: 2026-10-17
updated: 2026-10-17
---

# Spec: qBit Manage — relocate torrents to the category's configured path

## Problem

qBit Manage assigns categories from save paths (`cat_update`) and moves torrents between
categories (`cat_change`), but it never relocates the torrent's data: no code path in the
repository calls qBittorrent's `set_location`. Users who want a torrent's files to live in the
category's directory must rely on qBittorrent's Automatic Torrent Management moving the files as
a side effect of `set_category` — behavior the documentation warns about ("the files could be
moved !!!", `docs/Config-Setup.md`) because it is implicit, depends on a client-level setting the
tool does not control, and targets qBittorrent's per-category save path, which can diverge from
the path configured in qBit Manage's `cat:` section (qBit Manage itself creates missing
categories with the torrent's current save path, not the configured one).

## Expected outcome

When the user opts in, `cat_update` and `cat_change` relocate a torrent's data to the default
path configured for its category in the `cat:` section, deterministically and with explicit
safety guards, instead of relying on qBittorrent's Automatic Torrent Management side effects.
Without the opt-in, behavior is byte-for-byte identical to today.

## Functional requirements

- RF-1: `cat_update` can optionally relocate a torrent to its assigned category's configured
  `cat:` path when that path differs from the torrent's current save path.
- RF-2: `cat_change` can optionally relocate a torrent to the new category's configured `cat:`
  path after the category switch.
- RF-3: Relocation is guarded: it never moves a torrent whose files are shared with cross-seed
  siblings, never resolves an ambiguous configured path (wildcard entries, `Uncategorized`
  multi-path lists), does nothing when the torrent already sits at the configured path, and only
  applies to completed torrents.
- RF-4: Relocation honors `dry_run` (logs the intended move, performs none) and a relocation
  failure on one torrent is logged and notified without aborting the rest of the run.
- RF-5: The new configuration keys are registered through the existing `check_for_attribute`
  pattern and propagate to every configuration surface: `config/config.yml.sample`,
  `docs/Config-Setup.md` and the matching `web-ui/js/config-schemas/` schema.

## Non-functional requirements

- RNF-1: Backwards compatibility: with the new keys absent or disabled, no relocation call is
  ever made and existing category behavior is unchanged.
- RNF-2: Observability: every relocation and every guarded skip produces a log line with the
  reason, consistent with the existing category logging and notification attributes.

## Included scope

- Opt-in relocation for the `cat_update` and `cat_change` commands, sharing one relocation
  implementation.
- Configuration parsing and validation for the new keys, on all four configuration surfaces.
- Unit tests for the relocation logic, its guards and the configuration parsing.
- Documentation of the behavior, its guards and its interaction with Automatic Torrent
  Management.

## Excluded scope

- Synchronizing qBittorrent's per-category save path with the `cat:` configuration, or editing
  existing qBittorrent categories.
- Changing how Automatic Torrent Management itself is enabled or disabled (`force_auto_tmm`
  stays as it is).
- Cross-drive or cross-filesystem move orchestration beyond what qBittorrent's `set_location`
  performs (the standalone `scripts/mover.py` use case).
- Relocation triggered by any command other than `cat_update` and `cat_change`.
- A new CLI command: the feature extends the two existing commands through configuration only.

## Acceptance criteria

- AC-1 (`RF-1`): Given relocation is enabled and a torrent is assigned a category whose
  configured `cat:` path differs from its save path, when `cat_update` applies the category,
  then the torrent's location is set to the configured path.
- AC-2 (`RF-2`): Given relocation is enabled and `cat_change` switches a completed torrent to a
  category with a different configured path, when the switch is applied, then the torrent's
  location is set to the new category's configured path.
- AC-3 (`RF-1`, `RF-2`, `RNF-1`): Given the relocation keys are absent or disabled, when
  `cat_update` or `cat_change` run, then no location change is requested for any torrent and the
  logged behavior matches the pre-feature behavior.
- AC-4 (`RF-3`): Given a torrent whose files are shared with a cross-seed sibling, when
  relocation would apply, then the relocation is skipped and the skip is logged with the
  cross-seed reason.
- AC-5 (`RF-3`): Given a category whose configured path is ambiguous (wildcard pattern or an
  `Uncategorized` list of paths), when relocation would target it, then the relocation is
  skipped and the ambiguity is logged.
- AC-6 (`RF-3`): Given a torrent already located at its category's configured path, when
  relocation is evaluated, then no relocation request is issued for it.
- AC-7 (`RF-3`): Given a torrent that has not completed downloading, when relocation is
  evaluated, then it is not relocated.
- AC-8 (`RF-4`): Given `dry_run` is active and relocation is enabled, when a relocation would
  apply, then the intended move is logged and no location change is requested.
- AC-9 (`RF-4`): Given the relocation request fails for one torrent, when the run continues,
  then the failure is logged and notified and the remaining torrents are still processed.
- AC-10 (`RF-5`): Given an invalid value for a new relocation key, when the configuration is
  loaded, then it is rejected with the same error behavior as other invalid configuration keys;
  and the keys are documented in the sample config, the setup docs and the web UI schema.
- AC-11 (`RNF-2`): Given relocation is enabled, when a run relocates or skips torrents, then the
  run's log and notification payload identify each relocated or skipped torrent with its reason.

## Constraints

- Paths in the `cat:` configuration, torrent save paths and `set_location` targets all live in
  qBittorrent's path space (`root_dir`); local filesystem checks require the existing
  `root_dir`/`remote_dir` mapping and must not leak into relocation targets.
- The relocation guard for cross-seeds must work during `cat_update` runs, where the full
  torrent file map (`torrentfiles`) is not built today.
- Python 3.10+, Ruff lint/format, and the repository's test-factory patterns apply (AGENTS.md).
- All changes land through pull requests targeting `develop` (AGENTS.md branch model).

## Open questions

- On a guarded skip (for example a cross-seed sibling), should the category change itself still
  be applied, or should the torrent be left entirely untouched? To be resolved by an ADR.
- Should the opt-in be a single global setting, a per-`cat_change`-mapping flag, or both? To be
  resolved by an ADR; the spec only requires that both commands can be enabled independently.
- None of these blocks this proposal.
