---
id: TST004
type: test
revision: 1
project: qbit-manage
kind: unit
verifies:
  - T004
derived_from:
  tasks/T004-category-relocation-execution.md: 1
execution:
  mode: automated
  environment: local
  command: uv run pytest tests/core/test_category_relocation_execution.py
created: 2026-10-18
updated: 2026-10-18
---

# TST004: Relocations, failures, refusals and skips are reported and counted exactly once

## Purpose

Proves the run's reporting contract: what a user is told, through which channel, and with which
counters. It is the contract the acceptance criteria describe and the one that must not turn a large
library into thousands of notifications.

## Preconditions

- The `Category` built through `tests/factories.py`, with the fake torrent recording `set_location`.
- The primitives of T002 and the plan of T003.

## Procedure

1. Successful relocation: assert one log line, one attribute in `notify_attr` with a non-empty
   `torrents` list and the category-derived fields, one entry in `torrents_updated`, one relocation
   counted, and `stats` unchanged.
2. Failed relocation: make the primitive return `False`; assert the failure is logged and notified,
   no relocation counted, no entry in `torrents_updated`, `stats` unchanged, and no exception
   propagated.
3. Refusal: assert the refusal is logged and notified with its reason, and no relocation counted.
4. Skips: for each skip reason assert one log line naming the torrent and reason, exactly one reason
   counter incremented, no per-torrent attribute, and one summary attribute per run sent through
   `config.send_notifications` with `torrents` holding the skipped names and the four
   category-derived fields `None`.

## Expected result

All cases pass. Failures report which channel or counter is wrong: a skip producing a per-torrent
notification, or the summary travelling through `notify_attr`, where the grouping path would rewrite
its body and lose the counts.
