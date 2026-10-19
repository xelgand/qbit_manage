---
id: T002
type: task
revision: 1
project: qbit-manage
execution_mode: builder
repository: qbit-manage
epic: E001
derived_from:
  architecture.md: 1
covers:
  - AC-4
  - AC-9
execution_budget:
  target_minutes: 45
allowed_paths:
  - modules/qbittorrent.py
  - tests/test_qbittorrent.py
risk: irreversible
created: 2026-10-18
updated: 2026-10-18
---

# T002: Add the relocation primitives to `Qbt`

## Outcome

`Qbt` can resolve a category's configured relocation path, find the torrents whose save paths could
collide with a torrent's files, decide whether any of them shares a file, and issue a relocation
that reports whether it happened.

## Scope

- `category_config_path(category)`: return the normalized literal configured path from
  `config.data["cat"]` (`os.path.join(value, "")`), or `None` when the category is absent, when its
  value is a list (`Uncategorized`), or when the value contains a glob metacharacter (`*`, `?`,
  `[`). Decorate with `cache(...)` like `get_category`.
- `directory_peers(save_path, exclude_hash)`: from a lazily fetched, cached full client list,
  return the hashes of the torrents whose save path is equal to, an ancestor of, or a descendant of
  `save_path` (compare normalized paths segment-wise); return `None` when that list cannot be read,
  distinctly from an empty list.
- `torrent_file_paths(torrent_hash)`: the set of `os.path.join(save_path, file.name)` for a torrent,
  cached for the run, `None` when the file list cannot be read. Build paths exactly as
  `add_torrent_files` does.
- `has_shared_files(torrent_hash, save_path)`: `True` when a peer shares a file path, and `True`
  when the peers or any needed file list cannot be read (fail closed).
- `relocate_torrent(torrent, target) -> bool`: call `torrent.set_location(location=target)` inside
  an inner function that returns `True`, wrapped by
  `@handle_qbit_api_errors(context="set_location", retry_attempts=2)`, and return
  `inner() is True` so a swallowed API error reaches the caller as `False`.
- Unit tests for every member above in `tests/test_qbittorrent.py`.

## Exclusions

- Any change to `modules/core/category.py`: the guard evaluation and the call sites are T003–T006.
- Extending `TORRENT_DICT_COMMANDS` or building `torrentfiles` for category runs: ADR-003 decides
  against it.
- Any filesystem access: ADR-004 decides against it.

## Completion criteria

- `category_config_path` returns the trailing-separator form of a literal path, and `None` for an
  absent category, a list value and each of `*`, `?`, `[`.
- `directory_peers` returns the same-save-path peers plus ancestor and descendant save-path peers,
  excludes the candidate itself, and returns `None` (not `[]`) when the client list read fails.
- `has_shared_files` returns `True` for a shared path, `False` for a complete empty intersection,
  and `True` when a file list or the peer list is unavailable.
- `torrent_file_paths` is fetched once per hash per run and builds the same joined path as
  `add_torrent_files`.
- `relocate_torrent` calls `set_location` with the given target and returns `True`; when the
  decorated call swallows an API error and yields `None`, it returns `False`.

## Verification

- `uv run pytest tests/test_qbittorrent.py` passes, including the new cases.
- The failure signal is proved by a case that makes the inner call raise a handled API error type
  and asserts `relocate_torrent(...) is False`.
- Failure looks like: `directory_peers` returning `[]` on a read error, or `relocate_torrent`
  returning `True`/`None` after a swallowed error.

Covered by `TST002`.

## Evidence

- Pull request: https://github.com/xelgand/qbit_manage/pull/6
- Commits: `9357bdb` (feat(T002): add relocation primitives to Qbt), `58380eb` (fix(T002): treat root save path as an ancestor in peer selection)
- Merge: `2eb160f1a80ed29bc1d212f2575d943cf23e9cde` into `specbound/E001-relocate-torrents-to-category-path`
