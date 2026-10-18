---
type: spec
revision: 1
project: qbit-manage
created: 2026-10-17
updated: 2026-10-18
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
  multi-path lists), does nothing when the torrent already sits at the configured path, applies
  only to completed torrents, and never targets a torrent whose location qBittorrent governs — or
  will govern once this run has made its category change — through Automatic Torrent Management,
  whether that comes from the torrent's own setting or from the `force_auto_tmm` setting the
  category change applies.
- RF-4: Relocation honors `dry_run` (logs the intended move, performs none) and a relocation
  failure on one torrent is logged and notified without aborting the rest of the run.
- RF-5: The new configuration keys are registered through the existing `check_for_attribute`
  pattern and propagate to every configuration surface: `config/config.yml.sample`,
  `docs/Config-Setup.md` and the matching `web-ui/js/config-schemas/` schema.
- RF-6: With relocation enabled, `cat_update` also aligns torrents that already carry a category
  but sit outside that category's configured path, moving them to it without changing their
  category. This covers the larger part of a typical library, which today is skipped by the
  existing "has a category, Automatic Torrent Management disabled" filter.

## Non-functional requirements

- RNF-1: Backwards compatibility: with the new keys absent or disabled, no relocation call is
  ever made and existing category behavior is unchanged.
- RNF-2: Observability: every relocation, every refusal and every skip produces a log line naming
  the torrent and the reason. Relocations and refusals also reach the notification payload per
  torrent; every other skip — an ambiguous or absent configured path, an incomplete torrent, an
  Automatic Torrent Management torrent, whether the setting is the torrent's own or the one
  `force_auto_tmm` applies, and a torrent already in place — is reported in one per-run summary
  entry with counts per reason. No library size can therefore produce a notification storm, and a
  run where every candidate was skipped still says so.

## Included scope

- Opt-in relocation for the `cat_update` and `cat_change` commands, sharing one relocation
  implementation.
- Alignment of already-categorized torrents with their category's configured path, when
  `cat_update` relocation is enabled and Automatic Torrent Management is disabled for the torrent
  (RF-6).
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
- Relocation of torrents whose location qBittorrent manages through Automatic Torrent Management:
  for those, the client's per-category save path governs, and the mismatch between that path and
  the `cat:` configuration is the excluded synchronization above.
- A new CLI command: the feature extends the two existing commands through configuration only.

## Acceptance criteria

- AC-1 (`RF-1`): Given relocation is enabled, Automatic Torrent Management is disabled for the
  torrent, and the torrent is assigned a category whose configured `cat:` path differs from its
  save path, when `cat_update` applies the category, then the torrent's location is set to the
  configured path.
- AC-2 (`RF-2`): Given relocation is enabled and Automatic Torrent Management is disabled,
  when `cat_change` switches a completed torrent to a category with a different configured path,
  then the torrent's location is set to the new category's configured path.
- AC-3 (`RF-1`, `RF-2`, `RNF-1`): Given the relocation keys are absent or disabled, when
  `cat_update` or `cat_change` run, then no location change is requested for any torrent and the
  logged behavior matches the pre-feature behavior.
- AC-4 (`RF-3`): Given a torrent whose files are shared with a cross-seed sibling, when
  relocation would apply in the category-change path, then neither the category change nor the
  relocation is requested for it, and the skip is logged and notified with the cross-seed reason.
  In the alignment path (RF-6) there is no category change to withhold, so the guard withholds the
  relocation alone.
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
- AC-11 (`RNF-2`): Given relocation is enabled, when a run relocates torrents, refuses a
  relocation or skips one for any reason, then the log identifies each affected torrent with its
  reason, the notification payload identifies each relocated and refused torrent individually, and
  every other skip appears in a single per-run summary entry carrying the count per reason.
- AC-12 (`RF-6`): Given relocation is enabled for `cat_update`, Automatic Torrent Management is
  disabled, and a completed torrent carries a category whose configured path differs from its
  save path, when `cat_update` runs, then the torrent's location is set to that configured path
  and its category is left unchanged.
- AC-13 (`RF-3`): Given Automatic Torrent Management is enabled for a torrent, when relocation is
  evaluated, then no location change is requested for it, the skip is logged with the Automatic
  Torrent Management reason, and it is counted in the per-run skip summary.
- AC-14 (`RF-3`): Given `force_auto_tmm` is enabled and the torrent carries no ignore tag from
  `force_auto_tmm_ignore_tags`, when the category-change path evaluates relocation, then no
  location change is requested for that torrent — the category change hands its location to
  qBittorrent — the skip is logged with that reason and counted in the per-run skip summary. In the
  alignment path, which never enables Automatic Torrent Management itself, the torrent's own
  current setting governs.

## Constraints

- Paths in the `cat:` configuration, torrent save paths and `set_location` targets all live in
  qBittorrent's path space (`root_dir`); local filesystem checks require the existing
  `root_dir`/`remote_dir` mapping and must not leak into relocation targets.
- The relocation guard for cross-seeds must work during `cat_update` runs, where the full
  torrent file map (`torrentfiles`) is not built today.
- Automatic Torrent Management is a client-side location authority. Relocation never contends with
  it, and the contention is reachable from this project's own code: `update_cat`
  (`modules/core/category.py:122-128`) enables Automatic Torrent Management for ATM-disabled
  torrents whenever `force_auto_tmm` is on and the torrent carries no ignore tag. The guard
  therefore evaluates the state the category change *produces*, not only the state it finds
  (AC-13, AC-14): the category-change path treats a torrent as ATM-governed when its own setting is
  on **or** this run's category change will turn it on; the alignment pass, which never touches
  Automatic Torrent Management, uses the torrent's current setting alone and runs after
  `category()`, so it sees any flip that already happened.
- Python 3.10+, Ruff lint/format, and the repository's test-factory patterns apply (AGENTS.md).
- All changes land through pull requests targeting `develop` (AGENTS.md branch model).

## Open questions

- None blocks this proposal. The two questions that were open here — what a guarded skip does to
  the category change, and where the opt-in lives — are resolved by ADR-002 and ADR-001.
