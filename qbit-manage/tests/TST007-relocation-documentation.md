---
id: TST007
type: test
revision: 1
project: qbit-manage
kind: other
verifies:
  - T007
derived_from:
  tasks/T007-relocation-documentation.md: 1
execution:
  mode: manual
  environment: local
created: 2026-10-18
updated: 2026-10-18
---

# TST007: The documentation covers every guard and no excluded promise

## Purpose

Proves a user can learn, from the documentation alone, what the keys do, which torrents move and
which do not. Without it, the feature ships guards that look like bugs: a torrent that is not moved
and a category change that silently did not happen.

## Preconditions

- The documentation changes of T007.
- The architecture's guard table and the spec's Excluded scope at hand for the comparison.

## Procedure

1. `grep -c "cat_update_relocate\|cat_change_relocate" docs/Config-Setup.md` — both keys are
   documented.
2. Read the new passage and tick off one sentence per architecture guard: Automatic Torrent
   Management (the torrent's own setting and `force_auto_tmm`), ambiguous configured path (glob and
   `Uncategorized`), incomplete torrent, already in place, cross-seed refusal.
3. Confirm the text states that a refusal also withholds the category change, and why.
4. Confirm the text states the `dry_run` behavior and that a skipped torrent is retried next run.
5. Confirm the cross-filesystem hardlink limitation and the same-filesystem advice are present.
6. Read the passage against the spec's Excluded scope and confirm nothing excluded is described as
   supported.

## Expected result

Every check holds. A failure names the missing guard, the unsupported promise, or a contradiction
with the key descriptions T001 wrote in the sample configuration and the settings table.
