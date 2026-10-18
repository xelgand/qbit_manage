---
type: architecture
revision: 1
project: qbit-manage
derived_from:
  spec.md: 1
  plan.md: 1
  adr/ADR-001-relocation-opt-in-configuration.md: 1
  adr/ADR-002-guarded-skip-category-behaviour.md: 1
  adr/ADR-003-cross-seed-detection-mechanism.md: 1
  adr/ADR-004-hardlink-safety.md: 1
created: 2026-10-17
updated: 2026-10-18
---

# Architecture: qBit Manage — relocate torrents to the category's configured path

## Overview

The feature adds one relocation routine and two entry points to the existing category command, and
no new command, section or process.

- `modules/core/category.py` — `Category` gains the relocation routine, the guard evaluation and
  two entry points: the guard inside the existing `update_cat` (used by `cat_update` and
  `cat_change`) and a new alignment pass over already-categorized torrents.
- `modules/qbittorrent.py` — `Qbt` gains the API-level pieces the routine needs: resolving a
  category's configured path, finding directory peers, fetching and caching file lists, deciding
  cross-seed sharing, and issuing `set_location`.
- `modules/config.py` plus the three other configuration surfaces — two boolean settings keys, one
  per command (ADR-001).

Everything else stays as it is: the commands, their wiring through argparse/scheduler/web API/
webhooks, the run statistics, the notification pipeline.

## Domain design

### Vocabulary

- **Configured path** — the value `config.data["cat"][category]` for a category, in qBittorrent
  path space. It is a valid relocation target only when it is a single, literal path.
- **Candidate** — a torrent the routine would move: completed, Automatic Torrent Management
  disabled, carrying a category, whose normalized save path differs from the category's configured
  path.
- **Refusal** — the routine declines to act at all for a torrent, including the category change it
  was invoked for.
- **No-op** — relocation does not apply, but the caller's own work (the category change) proceeds
  unchanged.

### Guard evaluation

Evaluated in this order, cheapest and most authoritative first, only when the command's key is
enabled:

| # | Condition | Outcome |
|---|---|---|
| 1 | **Effective Automatic Torrent Management** — `torrent.auto_tmm` is true, or, in the category-change path, `settings["force_auto_tmm"]` is on and the torrent carries no tag from `settings["force_auto_tmm_ignore_tags"]` | No-op. Reason: Automatic Torrent Management governs the location (AC-13, AC-14). |
| 2 | Category absent from `cat:`, or its value is a list (`Uncategorized`) or contains glob metacharacters (`*`, `?`, `[`) | No-op. Reason: no unambiguous configured path. |
| 3 | Torrent not completed | No-op. Reason: incomplete. |
| 4 | Normalized save path equals the configured path | No-op. Reason: already in place (AC-6). |
| 5 | A directory peer shares one of the torrent's file paths | **Refusal** (AC-4). |
| 6 | Otherwise | Relocate. |

Rule 1 comes first because it is a local read and because AC-13 requires the Automatic Torrent
Management reason whenever that setting is on, even for a torrent that is also incomplete or whose
category has no literal path.

Rule 1's input differs by path, and the difference is the point: `update_cat` itself enables
Automatic Torrent Management for ATM-disabled torrents when `force_auto_tmm` is on
(`modules/core/category.py:122-128`), so the category-change path evaluates the state the change
produces; the alignment pass never touches Automatic Torrent Management and runs after every
category write, so it evaluates `torrent.auto_tmm` as it stands.

Only rule 5 refuses. Rules 1–4 cannot cause damage, so withholding the category change for them
would be a regression, not a guard. The distinction matters because `set_category` is the one call
in this path that can make qBittorrent move files itself, which is why a refusal must happen before
it (ADR-002).

### Path equality

Both sides are normalized to a trailing separator with `os.path.join(value, "")` — the same form
`Qbt.get_category` uses when matching save paths (`modules/qbittorrent.py:451-460`) — and compared
as strings. The configured path is used verbatim as the `set_location` target: it is already in
qBittorrent path space, and `root_dir`/`remote_dir` mapping must not be applied to it.

### Entry points

1. **Category-change path** — inside `update_cat`. The plan is evaluated and logged before the
   existing `if not self.config.dry_run:` block, so a dry run still reports every intended move and
   every refusal (AC-8); only `set_category` and the relocation call are gated by it. A refusal
   returns immediately (no category change, no relocation); a relocation is performed after
   `set_category` succeeds, so a failed category change never leaves a moved-but-miscategorized
   torrent.
2. **Alignment pass** — a new pass over already-categorized torrents, running only when
   `cat_update_relocate` is enabled and only for completed, non-ATM torrents whose category has a
   literal configured path. It changes no category, so a refusal withholds the relocation alone. It
   runs after `category()` and after `change_categories()`, and before the notification call at
   `modules/core/category.py:25` — see the Operations section for why that last boundary matters —
   so that: torrents that just received a category are evaluated against it, a `cat_change`
   candidate is not first moved to its old category's path and then to its new one, and any
   Automatic Torrent Management flip the run already made is visible to rule 1. A torrent an
   earlier step already moved is a no-op by rule 4.

### Counters and statistics

`self.stats` keeps its meaning — torrents whose category was updated — because it feeds the
run-end webhook field `torrents_categorized` (`modules/util.py:1847-1849`). Relocations and skips
are counted separately for the run summary and never increment `self.stats`, so a relocation-only
run reports no category updates.

## Applicable ADRs

| ADR | Decision it fixes here |
|---|---|
| `ADR-001` | Two boolean `settings` keys, `cat_update_relocate` and `cat_change_relocate`, default `false`; no per-category or per-mapping granularity. |
| `ADR-002` | The cross-seed guard is a refusal evaluated before `set_category`; every other guard is a no-op that leaves the category change alone. |
| `ADR-003` | Cross-seed sharing is decided by lazy per-candidate file-path intersection with a per-run cache, not by building the global file map. |
| `ADR-004` | No hardlink or filesystem check; the routine stays API-level and the cross-filesystem limitation is documented. |

## Interfaces

### `modules/config.py`

`settings["cat_update_relocate"]` and `settings["cat_change_relocate"]`, both
`check_for_attribute(..., parent="settings", var_type="bool", default=False)`, registered in the
block at `modules/config.py:394-449`. Mirrored in `config/config.yml.sample`,
`docs/Config-Setup.md` and `web-ui/js/config-schemas/settings.js`.

### `modules/qbittorrent.py` (`Qbt`)

| Member | Contract |
|---|---|
| `category_config_path(category)` | The normalized literal configured path for a category, or `None` when rule 2 applies. Pure read of `config.data["cat"]`; decorated with `cache(...)` like `get_category` (`modules/qbittorrent.py:129-131`). |
| `directory_peers(save_path, exclude_hash)` | The hashes of the torrents whose `save_path` is equal to, an ancestor of, or a descendant of `save_path` — every save path that can collide with it under `os.path.join` — from a lazily fetched and cached full client list. Returns `None` when that list cannot be read, which is a different answer from an empty list. |
| `torrent_file_paths(torrent_hash)` | The set of `os.path.join(save_path, file.name)` for a torrent, cached for the run; `None` when the file list cannot be read. Built the same way as `add_torrent_files` (`modules/qbittorrent.py:239-253`) so the two agree on what a shared path is. |
| `has_shared_files(torrent_hash, save_path)` | `True` when a peer shares a file path with the torrent; `True` as well when the peers or any file list cannot be read, because the guard fails closed (ADR-003). `False` only on a complete, empty intersection. |
| `relocate_torrent(torrent, target) -> bool` | Issues the move and reports whether it happened. The inner call returns `True` and is wrapped by `@handle_qbit_api_errors(context="set_location", retry_attempts=2)`; that decorator logs, notifies and returns `None` instead of raising for API errors (`modules/qbit_error_handler.py:155-243`), so the outer method returns `inner() is True` and a swallowed error reaches the caller as `False`. |

### `modules/core/category.py` (`Category`)

| Member | Contract |
|---|---|
| `relocation_enabled(cat_change)` | `self.config.settings["cat_change_relocate" if cat_change else "cat_update_relocate"]`. |
| `relocation_plan(torrent, category, cat_change)` | Applies rules 1–5 and returns the outcome — relocate with a target, no-op with a reason, or refuse with a reason. Performs no API call except the cross-seed check of rule 5, and only after rules 1–4 passed. The `cat_change` argument selects rule 1's effective-Automatic-Torrent-Management predicate. |
| `relocate(torrent, target)` | Calls `Qbt.relocate_torrent`, logs and notifies the outcome, and returns the boolean it received, so a swallowed API error is reported as a failure (AC-9) and is not counted as a relocation. |
| `align_locations()` | The alignment pass. Uses `self.hashes` when the run was invoked with hashes, so a targeted run stays targeted. |
| `update_cat(torrent, new_cat, cat_change)` | Gains the refusal short-circuit before the dry-run gate and the relocation after `set_category`. |

Returning an outcome value rather than logging inside the guard keeps the decision testable without
a notification pipeline, and keeps the wording of reasons in one place.

## Data

Nothing is persisted. All state is per-run and lives on the objects the run already creates:

- `Qbt` file-list cache: `dict[torrent_hash, set[str] | None]`, bounded by the candidates and their
  peers.
- `Qbt` peer cache: `dict[save_path, list[str]]`, one entry per directory touched.
- `Qbt` client-list cache: the single full torrent list used by `directory_peers`, fetched at most
  once per run.
- `Category` counters: relocations, refusals and no-op reasons for the summary line.

## Sequences

**Category change with relocation enabled.** `update_cat` → `relocation_plan` (rules 1–4 are local
reads) → rule 5 asks `has_shared_files`, which fetches peer file lists on first use → plan says
relocate → `set_category` → `relocate_torrent(target)` → `True`: log, notify, count the
relocation.

**Refusal.** Same start; rule 5 reports a shared file → log and notify the refusal with its reason
→ return without calling `set_category` or `set_location`.

**Alignment pass.** `Category.__init__` → `category()` → `change_categories()` →
`align_locations()` → for each completed, non-ATM torrent with a category: plan → relocate or skip
→ summary line with counts. No category is written.

**Failure.** `relocate_torrent` returns `False` after the decorator swallowed the API error and
notified it (`modules/qbit_error_handler.py:210-243`) → `relocate` logs and notifies the failure
with the torrent and target, does not count a relocation, and the run continues with the next
torrent (AC-9); the category change that preceded it stands, and the torrent remains where it was.

**Dry run.** The plan is evaluated and reported exactly as in a real run — what would move, what
was refused — while `set_category` and `relocate_torrent` are never called, so no client state
changes and no `set_location` is issued (AC-8).

## Operations

- Log lines via the existing `logger.print_line` with `self.config.loglevel`, one per relocation,
  refusal and skip; the per-run summary line reporting counts per reason closes the run and carries
  the same numbers as the summary notification.
- Notifications reuse the existing pipeline: attributes appended to `self.notify_attr` with
  `function: "cat_update"` and a title that distinguishes a relocation from a refusal — those two
  are the only classes that go through grouping. Each attribute carries `torrent_category`,
  `torrent_tag`, `torrent_tracker` and `notifiarr_indexer` because `group_notifications_by_key`
  indexes `attr["torrent_category"]` when a run exceeds the grouping limit
  (`modules/webhooks.py:195-249`); an attribute missing it would raise inside the notification path,
  not in the relocation path.
- Relocated and refused torrents are appended to `self.torrents_updated` alongside category
  updates, because that list is what decides grouping (`modules/webhooks.py:196`) — the run-end
  payload for a relocation-heavy alignment run would otherwise be one notification per torrent.
  `self.torrents_updated` feeds only that decision in this class (`modules/core/category.py:25`),
  so the list's meaning broadens from "torrents whose category changed" to "torrents this command
  acted on" while `self.stats` — and therefore the run-end `torrents_categorized` count — keeps the
  narrow meaning.
- Every other skip is never notified per torrent and never travels through the grouping path. The
  pass keeps counters per reason (ambiguous or absent configured path, incomplete, Automatic
  Torrent Management, already in place) and, at the end of the run, sends one attribute directly
  with `self.config.send_notifications(attr)` — the precedent is the grouped cleanup summary in
  `modules/core/share_limits.py:176-201` — instead of appending it to `self.notify_attr`. That
  matters because `Webhooks.notify` groups into per-`torrent_category` buckets as soon as
  `len(torrents_updated) > 10` (`modules/webhooks.py:12`, `:196`), keeps one attribute per bucket as
  the leader, rewrites its body unless the bucket holds exactly one torrent (`:218-225`) and indexes
  `torrents` unguarded (`:212`, `:226`): a category-independent summary inside that path would
  either lose its counts to the rewrite or raise `KeyError`. The sent attribute is fully pinned —
  `function: "cat_update"`, a title marking it a summary, a body listing the counts per reason,
  `torrents` holding the skipped torrent names, and `torrent_category`, `torrent_tag`,
  `torrent_tracker` and `notifiarr_indexer` all `None`, matching the cleanup summary's shape. It is
  what keeps a run whose every candidate was skipped visible in notifications without a storm
  (RNF-2, AC-11), and it is the only notification a torrent's own Automatic Torrent Management
  setting can produce (AC-13, AC-14).
- No new webhook field, no new stats key: the run-end payload keeps its current shape.

## Verification

| Layer | What it proves | Shape |
|---|---|---|
| Unit | Each guard in isolation, path normalization, dry-run, per-torrent failure isolation | `pytest tests/core/test_category*.py` on the existing factories; the fake torrent records `set_location`, the fake qbt manager supplies configured paths, peers and file lists |
| Unit | Configuration parsing and rejection of invalid values for both keys | `pytest tests/test_config*.py` |
| Acceptance | Every `AC-N` of the spec | Gherkin scenarios per criterion on the same fakes; no live qBittorrent |
| Manual | The four configuration surfaces agree, and a real run reports what it intended | `make lint`, `make format`, `make pre-commit`, plus a dry run against a real client |

The design's risky edges are exactly the ones the acceptance tests must pin: that a refusal
withholds `set_category` (AC-4), that a no-op does not (AC-5, AC-6, AC-7, AC-13), that
`force_auto_tmm` suspends relocation even though the torrent was ATM-disabled when the plan was
evaluated (AC-14), that the alignment pass writes no category (AC-12), that a swallowed API error
is reported as a failed relocation rather than a success (AC-9), and that disabling both keys
leaves the run's calls unchanged (AC-3).

## Open questions

- None. Every decision this design needed is closed by ADR-001 to ADR-004; a new one opens a new
  ADR.
