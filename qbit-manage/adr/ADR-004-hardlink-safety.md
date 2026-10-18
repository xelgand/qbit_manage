---
id: ADR-004
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

# ADR-004: Whether relocation is guarded against breaking external hardlinks

## Context

qBittorrent's `set_location` moves a torrent's files on disk. Within one filesystem the move is a
rename and hardlinks elsewhere keep pointing at the same inode, so nothing breaks. Across
filesystems the data is copied and the original path is removed, which leaves any hardlink outside
the torrent directory — the "hardlinked media library" layout this project supports through
`nohardlinks` (`modules/core/tag_nohardlinks.py`) — pointing at a now-orphaned inode while the
torrent's copy is a separate file. Subsequent seeding then writes to a different inode than the
media library and the two silently diverge.

The repository already contains the cost model for the opposite direction: the `nohardlinks`
feature stats files under `root_dir` mapped to `remote_dir` (`modules/util.py:1539-1578`) to detect
them. When relocation is enabled, the same class of user is the one most likely to move torrents
between category paths.

The spec's guards (RF-3) cover cross-seed siblings and ambiguous paths; hardlinks are named in the
plan's risks but no criterion requires a check. This decision fixes how far the feature goes.

## Question

Does relocation check for hardlinks before moving files, and if so, at what cost?

## Options

### Option A: No hardlink check; document the limitation

- Gives: no filesystem work in the relocation path; the feature stays an API-level operation, and
  users who hardlink are told to keep category paths on one filesystem (within which moves are
  renames and harmless).
- Costs: a cross-filesystem relocation silently breaks the media-library link, with no warning at
  the moment it happens; the damage is discovered later, when the library and the torrent have
  diverged.

### Option B: Inode check on relocation candidates

For each relocation candidate, stat its files under the `remote_dir` mapping and refuse the move
when any file has a link count greater than one.

- Gives: the broken-link case is caught before it happens, with the same `root_dir`/`remote_dir`
  discipline the rest of the project already uses; the skip can be logged with the file that
  triggered it.
- Costs: one `stat` per file of every candidate, on the machine running qBit Manage, which requires
  the remote filesystem to be mounted and reachable — a new runtime dependency the current
  category commands do not have. Path mapping bugs would make it report false negatives, and the
  guard is meaningless when the target path is on the same filesystem (where the move is safe).

### Option C: Filesystem-boundary test only

Refuse relocation when the source and target paths resolve to different filesystem device numbers
under the `remote_dir` mapping, without inspecting file link counts.

- Gives: catches the dangerous case (a cross-filesystem move) rather than the symptom, needs one
  `stat` per candidate directory instead of one per file, and cannot produce false positives for
  same-filesystem moves.
- Costs: it does not warn about a same-filesystem move into a directory that later gets archived
  or copied elsewhere; it still needs the remote filesystem mounted to compare device numbers.

## Decision

Option A: no hardlink check. Relocation stays an API-level operation that never touches the local
filesystem, and the limitation is documented where the feature is documented. Decided by the
approver on 2026-10-18.

The dangerous case is a move across filesystems, where the data is copied and any hardlink outside
the torrent directory is left pointing at an orphaned inode. Both guard options require the remote
filesystem to be mounted and readable from the machine running qBit Manage — a dependency the
category commands do not have today — and either of them turns a configuration mistake (a wrong
`remote_dir`) into a silent refusal to relocate. The specification's excluded scope already keeps
cross-filesystem orchestration out of this feature; documenting the constraint keeps the feature
small and its failure modes honest.

## Consequences

- Moves within one filesystem are renames: hardlinked media libraries are unaffected, which covers
  the normal layout where every category path lives on the same array.
- A user whose category paths span filesystems can silently orphan the library-side hardlink of a
  moved torrent; the documentation must state the constraint next to the new keys, and the
  operator is responsible for keeping category paths on one filesystem.
- The runtime requirement of the category commands does not grow: no mount, no `stat`, no new
  failure mode in the relocation path.
- If a future revision wants the check, it is additive: a device-number comparison under
  `remote_dir` can be added as a guard without changing the configuration keys, which the
  specification would have to require first.

## References

- `qbit-manage/spec.md` — RF-3, Included/Excluded scope; `qbit-manage/plan.md` — Risks.
- `modules/core/tag_nohardlinks.py`, `modules/util.py:1539-1578` — existing hardlink detection and
  the `root_dir`/`remote_dir` mapping.
- `docs/Config-Setup.md`, "nohardlinks" — the supported hardlink layout.
