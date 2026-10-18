---
id: T003
type: task
revision: 1
project: qbit-manage
execution_mode: builder
repository: qbit-manage
epic: E001
derived_from:
  architecture.md: 1
covers:
  - AC-5
  - AC-6
  - AC-7
  - AC-13
  - AC-14
depends_on:
  - T002
execution_budget:
  target_minutes: 45
allowed_paths:
  - modules/core/category.py
  - tests/core/test_category_relocation_plan.py
  - tests/factories.py
created: 2026-10-18
updated: 2026-10-18
---

# T003: Evaluate the relocation guards on `Category`

## Outcome

`Category` can decide, for one torrent and one category, whether relocation applies: it returns the
target path, or a no-op with the reason that stopped it, or a refusal, without changing anything.

## Scope

- `relocation_enabled(cat_change)`: read `cat_change_relocate` or `cat_update_relocate`.
- `relocation_plan(torrent, category, cat_change)`: return an outcome — relocate with a target, a
  no-op with a reason, or a refusal with a reason — applying the architecture's rules in order:
  1. effective Automatic Torrent Management (`torrent.auto_tmm`, or, when `cat_change` selects the
     category-change path, `settings["force_auto_tmm"]` and no tag from
     `settings["force_auto_tmm_ignore_tags"]` present);
  2. no unambiguous configured path (`Qbt.category_config_path` returning `None`);
  3. torrent not completed;
  4. save path already equal to the configured path (`os.path.join(..., "")` on both sides);
  5. a shared file with a directory peer (`Qbt.has_shared_files`), which is the only refusal.
- Extend `tests/factories.py` so a fake torrent exposes the fields and state the rules read, and a
  fake qbt manager supplies a configured path, peers and an intersection answer.
- Unit tests in `tests/core/test_category_relocation_plan.py`, one case per rule, plus the ordering
  cases (an ATM torrent that is also incomplete reports the Automatic Torrent Management reason).

## Exclusions

- Calling `set_location`, logging or notifying: that is T004.
- Reading the keys from a real configuration object: T001 registers them; these tests supply them
  through the fake configuration.
- The call sites in `update_cat` and the alignment pass: T005 and T006.

## Completion criteria

- Rule 1 returns the Automatic Torrent Management no-op for an ATM-on torrent, and for an ATM-off
  torrent whose plan is evaluated for the category-change path while `force_auto_tmm` is on and no
  configured ignore tag matches; it does not apply that second condition when the alignment path is
  selected or when an ignore tag matches.
- Rule 2 returns a no-op for an absent category, a list value and a glob value.
- Rule 3 returns a no-op for an incomplete torrent.
- Rule 4 returns a no-op when the normalized paths are equal.
- Rule 5 returns a refusal when `has_shared_files` is true, and no other rule refuses.
- `relocation_plan` performs no client call except the rule-5 check, and makes none at all when an
  earlier rule already decided.
- Ordering holds: rule 1 wins over rules 2–5; rule 5 is reached only when rules 1–4 pass.
- `relocation_enabled` returns the value of the key matching the selected path.

## Verification

- `uv run pytest tests/core/test_category_relocation_plan.py` passes with one case per rule, one per
  ordering pair that matters (rules 1, 2 and 3 against rule 5), and one per `force_auto_tmm`
  variation.
- The tests assert the returned outcome and reason, and that no `set_location` call was recorded.
- Failure looks like: an incomplete ATM torrent reporting the incomplete reason instead of the
  Automatic Torrent Management one, or a cohabitation case (peers present, no shared file) being
  refused.

Covered by `TST003`.
