---
id: T004
type: task
revision: 1
project: qbit-manage
execution_mode: builder
repository: qbit-manage
epic: E001
derived_from:
  architecture.md: 1
covers:
  - AC-9
  - AC-11
depends_on:
  - T003
execution_budget:
  target_minutes: 45
allowed_paths:
  - modules/core/category.py
  - tests/core/test_category_relocation_execution.py
  - tests/factories.py
risk: irreversible
created: 2026-10-18
updated: 2026-10-18
---

# T004: Execute, report and count relocations on `Category`

## Outcome

A relocation decided by `relocation_plan` is performed through `Qbt.relocate_torrent`, reported per
torrent when it succeeds or fails or is refused, counted per reason when it is skipped, and the run
ends with one summary entry carrying those counts.

## Scope

- `relocate(torrent, target) -> bool`: call `Qbt.relocate_torrent`, and
  - on `True`: log the move, append an attribute to `self.notify_attr` with the shape built at
    `modules/core/category.py:158-172` (`function: "cat_update"`, a title marking a relocation,
    `body`, a non-empty `torrents` list with the torrent name, `torrent_category`, `torrent_tag`,
    `torrent_tracker`, `notifiarr_indexer`), append the name to `self.torrents_updated` and increase
    the relocation counter;
  - on `False`: log and notify the failure with the torrent and the target, without counting a
    relocation, and let the run continue (never raise).
- A refusal is logged and notified with the same attribute shape and a title marking it a refusal.
- `report_skip(torrent, plan)`: the single entry point every skip goes through, from either path —
  one log line naming the torrent and the reason, and exactly one reason counter. It performs no
  client call and sends nothing.
- `relocation_skip_summary()`: sends the run's skip summary — one attribute with
  `self.config.send_notifications(attr)`, carrying `torrent_category`, `torrent_tag`,
  `torrent_tracker` and `notifiarr_indexer` as `None`, a `torrents` list with the skipped names, a
  summary title and a body listing the counts per reason — and sends nothing when no skip was
  counted. It is a method of its own, so the run can emit it whenever either key is enabled, not
  only when the alignment pass ran; T006 wires the call.
- Leave `self.stats` untouched by relocations and skips: it keeps counting category updates only.
- Unit tests in `tests/core/test_category_relocation_execution.py`, with the fake torrent recording
  `set_location` calls.

## Exclusions

- The guard rules themselves: T003 owns them; this task consumes the plan.
- The call sites in `update_cat` and the alignment pass: T005 and T006 decide when to call
  `relocate`.
- Any change to the run-end webhook payload, `stats` keys or `modules/webhooks.py`.
- `self.stats` semantics beyond leaving them unchanged for relocations.

## Completion criteria

- A successful relocation produces one log line, one notification attribute with a non-empty
  `torrents` list, one entry in `self.torrents_updated` and one unit in the relocation counter.
- A failed relocation (the primitive returning `False`) produces a logged and notified failure, no
  relocation count, no entry in `self.torrents_updated`, and does not interrupt the caller.
- A refusal produces a logged and notified refusal with its reason and does not count as a
  relocation.
- `report_skip` produces exactly one log line naming the torrent and the reason and increments
  exactly one reason counter, for each skip reason, and never a per-torrent notification.
- `relocation_skip_summary()` sends exactly one attribute through `config.send_notifications` with
  `None` for the category-derived fields and the counts per reason, sends nothing when no skip was
  counted, and can be called in a run where the alignment pass never ran.
- `relocate` itself performs the client call unconditionally: the dry-run gate lives at the call
  sites (T005 for the category-change path, T006 for the alignment pass), so this task's tests
  assert the call and T005/T006 assert its absence under `dry_run`.
- `self.stats` is unchanged by any of these paths.

## Verification

- `uv run pytest tests/core/test_category_relocation_execution.py` passes.
- The tests assert on the recorded `set_location` calls, on the attributes appended to
  `notify_attr`, on the direct `send_notifications` call for the summary, and on the counters.
- Failure looks like: a failed relocation counted as a move, a per-torrent notification for a skip,
  or the summary travelling through `notify_attr` (which the grouping path would rewrite).

Covered by `TST004`.

## Evidence

- Pull request: https://github.com/xelgand/qbit_manage/pull/9
- Commit: `abb7849` (feat(T004): perform relocations with reporting and counters)
- Merge: `e85924bf3d4146ee4160fac1975ad6454c2f6e5a` into `specbound/E001-relocate-torrents-to-category-path`
