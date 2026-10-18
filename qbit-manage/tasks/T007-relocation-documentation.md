---
id: T007
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
depends_on:
  - T001
execution_budget:
  target_minutes: 30
allowed_paths:
  - docs/Config-Setup.md
  - README.md
created: 2026-10-18
updated: 2026-10-18
---

# T007: Document the relocation behavior, its guards and its limitations

## Outcome

A user who reads the setup documentation learns what the two keys do, which torrents are moved,
which are refused or skipped and why, what happens with Automatic Torrent Management, and which
limitation the feature accepts.

## Scope

- Extend the `cat` and `cat_change` sections and the `settings` table of `docs/Config-Setup.md`
  with: what enabling relocation does in each command, the alignment pass for already-categorized
  torrents, the guard list with the reason each produces, that a cross-seed refusal withholds the
  category change too and why, that Automatic Torrent Management torrents are never relocated (both
  the torrent's own setting and `force_auto_tmm`), that a blocked or delayed torrent is retried on
  the next run, and the cross-filesystem hardlink limitation from ADR-004 with the advice to keep
  category paths on one filesystem.
- Add the two keys to the relevant feature list in `README.md` if the file enumerates category
  behavior.

## Exclusions

- Any code change.
- The inline comments in `config/config.yml.sample` and the key rows in the settings table: T001
  owns those, and this task must not contradict them.
- Restating the ADRs: the documentation explains behavior for a user, and links the decisions
  instead of copying their rationale.

## Completion criteria

- Every guard in the architecture's evaluation table is described with the outcome a user observes
  (moved, refused, or skipped) and with its Automatic Torrent Management case included.
- The documentation states that a refusal also withholds the category change, and that this is what
  keeps qBittorrent from performing the move instead.
- The documentation states the cross-filesystem limitation and the same-filesystem advice.
- The `dry_run` behavior of the feature is stated.
- No sentence contradicts the descriptions of the two keys that T001 wrote.

## Verification

- Structural check: `grep -c "cat_update_relocate\|cat_change_relocate" docs/Config-Setup.md`
  reports the keys, and every guard name from the architecture (`Automatic Torrent Management`,
  cross-seed, wildcard, `Uncategorized`, incomplete, already in place) appears in the new text.
- Manual procedure: read the new section against the architecture's guard table and confirm one
  sentence per row, and against the spec's Excluded scope to confirm nothing promised there is
  described as supported.
- Failure looks like: a guard missing, the `force_auto_tmm` case unmentioned, or a claim that
  relocation works for ATM-managed torrents.

Covered by `TST007`.
