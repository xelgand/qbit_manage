---
id: ADR-003
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

# ADR-003: How cross-seed sharing is detected during cat_update and cat_change

## Context

Cross-seed safety in this repository is built on one structure: `Qbt.torrentfiles`, a map from
`os.path.join(save_path, file.name)` to `{"original": hash, "cross_seed": [hashes]}`, filled by
`add_torrent_files` (`modules/qbittorrent.py:239-253`) and consumed by `has_cross_seed`
(`qbittorrent.py:277-294`) and `is_cross_seed` (`qbittorrent.py:255-275`). That structure is built
only when at least one command in `TORRENT_DICT_COMMANDS` is enabled (`qbittorrent.py:32`, gated at
`qbittorrent.py:122`): `recheck`, `rem_unregistered`, `tag_tracker_error`, `tag_nohardlinks`,
`share_limits`. Building it costs one file-list fetch per torrent in the client
(`get_torrent_info`, `qbittorrent.py:133-237`).

`cat_update` and `cat_change` are not in that list, so during a category-only run `torrentfiles` is
`None`. The relocation guard from RF-3 must decide whether another torrent owns the same files
before calling `set_location`, which moves them on disk.

## Question

How does the relocation guard detect that a torrent's files are shared with a cross-seed sibling,
given that the existing cross-seed structure is not built during category runs?

## Options

### Option A: Add the category commands to `TORRENT_DICT_COMMANDS`

Build the full `torrentfiles` map for `cat_update`/`cat_change` runs and reuse `has_cross_seed`
unchanged.

- Gives: no new detection logic; the guard uses the same, already-tested structure as
  `share_limits` and `rem_unregistered`, so its notion of a sibling is exactly theirs.
- Costs: one file-list API call per torrent in the whole client on every category run, whether or
  not relocation is enabled and whether or not any torrent is a relocation candidate. It also
  changes what a category-only run does today, which the backwards-compatibility requirement
  (RNF-1) asks us to avoid.

### Option B: Cheap save-path scan over the torrent list

Group the already-fetched torrent list by `save_path` and refuse relocation when another torrent
shares the directory.

- Gives: no extra API calls at all; the data is already in hand.
- Costs: it does not detect sharing, only cohabitation. Two independent torrents legitimately
  living in one directory — a common layout — are treated as siblings, so relocation silently
  stops working precisely on the categories users are most likely to configure. A guard that fires
  on the common case is worse than no guard, because it hides the feature.

### Option C: Lazy per-candidate detection

When relocation is enabled and a torrent is a candidate, fetch file lists for that torrent and for
the torrents sharing its `save_path`, and intersect the file paths to decide sibling status.

- Gives: accurate results with a bounded cost — API calls proportional to the number of relocation
  candidates and their neighbours, zero when relocation is off or nothing needs to move, so RNF-1
  holds. It reuses the same path-intersection idea as `add_torrent_files`.
- Costs: new detection code to write and test, and a per-candidate cost that grows with the size of
  the shared directory; requires caching within a run so that two candidates in one directory do
  not fetch the same peer's file list twice.

## Decision

Option C: lazy per-candidate detection. When relocation is enabled and a torrent is a candidate,
fetch the file lists of that torrent and of the torrents sharing its `save_path`, cache them for
the run, and treat a non-empty intersection of file paths as cross-seed sharing. Decided by the
approver on 2026-10-18.

Option A changes what a category-only run does for every user (RNF-1 forbids it) and pays one
file-list call per torrent in the client on every run, whether or not relocation is on. Option B
does not detect sharing at all — it detects cohabitation — and would silently disable relocation
for the layouts where several torrents legitimately share a directory. Option C pays only when
there is a candidate, keeps the cross-seed notion identical to `add_torrent_files` (same path
construction, same intersection), and needs no change to `TORRENT_DICT_COMMANDS`.

## Consequences

- Detection cost is proportional to relocation candidates and their directory peers, not to the
  library; a run with relocation enabled and nothing to move costs no extra API calls.
- A per-run cache is required, or two candidates in one directory refetch the same peers' file
  lists.
- The guard's notion of a sibling matches `share_limits` and `rem_unregistered`, so the three
  features cannot disagree about what a cross-seed is.
- The guard remains blind to files that are *not* shared by path — hardlinked duplicates of the
  same content under different paths — which is ADR-004's decision.
- If a peer's file list cannot be fetched, the guard must fail closed for that candidate: an
  unknown sibling is treated as a sibling, so a guard that cannot run refuses the move.

## References

- `qbit-manage/spec.md` — RF-3, AC-4, RNF-1; constraint on the missing file map.
- `modules/qbittorrent.py:32`, `:122`, `:239-294` — the gated map and the existing guards.
- `modules/core/remove_unregistered.py:338-347`, `modules/core/share_limits.py:133-151` — current
  consumers of `has_cross_seed`.
