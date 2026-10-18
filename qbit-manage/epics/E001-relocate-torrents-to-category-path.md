---
id: E001
type: epic
revision: 1
project: qbit-manage
repository: qbit-manage
derived_from:
  architecture.md: 1
covers:
  - AC-1
  - AC-2
  - AC-3
  - AC-4
  - AC-5
  - AC-6
  - AC-7
  - AC-8
  - AC-9
  - AC-10
  - AC-11
  - AC-12
  - AC-13
  - AC-14
created: 2026-10-18
updated: 2026-10-18
---

# E001: Relocate torrents to their category's configured path

## Shared outcome

With the new opt-in enabled, `cat_update` and `cat_change` move a torrent's data to the path its
category declares in the `cat:` section, behind the guards the spec and the design define, and the
run reports what it moved, refused and skipped.

## Scope

- The two configuration keys and their four surfaces.
- The API-level relocation primitives on `Qbt`, including cross-seed detection and the failure
  signal.
- The guard evaluation and the relocation execution on `Category`, with its logging, notification
  attributes and per-run skip summary.
- Integration into the category-change path and into the new alignment pass for already-categorized
  torrents.
- The unit tests of each piece and the acceptance tests of every criterion.
- The user-facing documentation of the behavior, its guards and its limitations.

## Exclusions

- Any command other than `cat_update` and `cat_change`, and any new CLI flag or command: the feature
  is configuration-only.
- Synchronizing qBittorrent's per-category save path with `cat:`, or editing existing categories.
- Filesystem-level checks (hardlink, filesystem identity), which ADR-004 excludes.
- Cross-drive move orchestration: `scripts/mover.py` stays as it is.
- Rework of the share-limits, no-hardlinks, orphaned or unregistered paths, which only supply the
  cross-seed notion this epic reuses.

## Sequence

The tasks form a chain inside this epic, so one epic branch and one review cover the whole feature:

- `T001` and `T002` are independent and open the work.
- `T003` → `T004` → `T005` → `T006` are sequential because every one of them edits
  `modules/core/category.py`.
- `T007` follows `T001` because both edit `docs/Config-Setup.md`.
- `T008`, `T009` and `T010` follow `T006` and are independent of each other: each writes its own
  test file and touches none shared.
