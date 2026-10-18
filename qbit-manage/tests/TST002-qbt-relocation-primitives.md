---
id: TST002
type: test
revision: 1
project: qbit-manage
kind: unit
verifies:
  - T002
derived_from:
  tasks/T002-qbt-relocation-primitives.md: 1
execution:
  mode: automated
  environment: local
  command: uv run pytest tests/test_qbittorrent.py
created: 2026-10-18
updated: 2026-10-18
---

# TST002: Relocation primitives resolve targets, peers and failures correctly

## Purpose

Proves the four decisions the relocation guards depend on: which configured paths are usable, which
torrents can collide with a candidate, when sharing is declared, and whether a relocation actually
happened. A wrong answer here moves data that should not move, or reports a move that failed.

## Preconditions

- A `Qbt` instance built on the existing fakes, with a configuration carrying a `cat` section.
- The new members of T002 in `modules/qbittorrent.py`.

## Procedure

1. `category_config_path`: assert the trailing-separator form for a literal path; assert `None` for
   an absent category, a list value and each of the three glob metacharacters.
2. `directory_peers`: with torrents at `/data/tv`, `/data/tv/Show`, `/data/other` and the candidate
   at `/data/tv`, assert the peers are the same-path and descendant torrents, that the candidate is
   excluded, and that `/data/other` is not a peer.
3. `directory_peers` on a client list read error: assert the result is `None`, and that an empty
   torrent list returns `[]`.
4. `torrent_file_paths`: assert the joined paths match what `add_torrent_files` builds for the same
   torrent, and that a second call for the same hash does not fetch again.
5. `has_shared_files`: `True` for an overlapping file, `False` for peers with disjoint files, and
   `True` when a peer file list or the peer list is unavailable.
6. `relocate_torrent`: assert `set_location` received the target and the return is `True`; then make
   the call raise a handled API error type and assert the return is `False`.

## Expected result

All cases pass. A failure names the wrong answer: the dangerous ones are `has_shared_files`
returning `False` when it could not read a file list, and `relocate_torrent` returning `True` after
a swallowed error, which would count a failed move as done.
