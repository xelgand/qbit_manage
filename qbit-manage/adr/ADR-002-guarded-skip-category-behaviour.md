---
id: ADR-002
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

# ADR-002: What happens to the category when relocation is skipped by a guard

## Context

`cat_update` assigns a category and `cat_change` switches one; today both do that with a single
`torrent.set_category(...)` call (`modules/core/category.py:122`) and, when `force_auto_tmm` is on,
`torrent.set_auto_management(True)` (`category.py:126`). The relocation feature adds guards that
can refuse a move: cross-seed sharing (RF-3), an ambiguous configured path (RF-3), a torrent
already in place (RF-3) and incomplete torrents (RF-3).

The guards are evaluated inside a command whose primary job is the category change, so a refusal to
move leaves a question: is the category change still applied? The answer matters beyond this
feature: qBittorrent itself moves files when the category changes and Automatic Torrent Management
is on — the exact side effect this feature exists to replace — so applying the category change can
relay the move to the client even though qBit Manage declined to perform it.

## Question

When a relocation guard refuses the move, is the category change still applied?

## Options

### Option A: Apply the category change, skip only the relocation

- Gives: command semantics stay as they are — categorization never depends on filesystem
  conditions; the log and notification report the skip and its reason.
- Costs: with Automatic Torrent Management on, `set_category` can make qBittorrent move the files
  to the client's per-category save path anyway, which defeats the cross-seed guard exactly when it
  is needed. It also leaves the torrent in a category whose configured path is not where the data
  is, a divergence this feature otherwise removes.

### Option B: Skip the whole torrent — no category change, no relocation

- Gives: a guard that actually prevents file movement, because nothing reaches the client that
  could trigger its own move. The state stays coherent: no torrent is put in a category whose
  configured path it does not occupy. The next run retries, so the work resumes once the condition
  clears.
- Costs: a torrent can keep an outdated category while a cross-seed sibling exists; users see a
  skipped category change, not just a skipped move, and need the log to understand why.

### Option C: Apply the category change and tag the torrent for manual review

- Gives: the category advances while the unresolved conflict is visible in qBittorrent.
- Costs: inherits Option A's Automatic Torrent Management exposure, and introduces a new tag with
  its own lifecycle (when is it removed?) that the spec does not define.

## Decision

Option B: when a relocation guard refuses the move, the torrent is left untouched — no category
change, no relocation, and the skip is logged and notified with its reason. Decided by the
approver on 2026-10-18.

The decisive argument is the Automatic Torrent Management relay. `set_category` is the only call
this command family makes that can make qBittorrent itself move files, and with ATM on it moves
them to the client's per-category save path. A guard that skips only the relocation therefore
leaves the very move it refused to qBittorrent, which defeats it. Option B is the only option
where a refusal reaching the client is impossible.

The decision is scoped to the category-change path. The alignment pass introduced by RF-6 changes
no category: there, a refusal withholds the relocation alone, because there is nothing else to
withhold. Ambiguous configured paths and torrents already in place are not refusals either — they
mean no relocation applies, so the category change proceeds as it does today.

## Consequences

- A torrent whose move is refused keeps its previous category until the condition clears; the next
  run retries, so no state is lost, but a run's category workload can be incomplete with the
  reason visible only in the log and notification payload.
- Users see a skipped category change, not just a skipped move, and the log line has to name the
  reason (AC-4, AC-11) or the behavior looks like a bug.
- The guard must be evaluated before `set_category` is called, not after, so refusal costs nothing
  on the client.
- qBit Manage never leaves a torrent in a category whose configured path it does not occupy
  because of a guard; the divergence that remains is the client's, under ATM, which the spec
  excludes.

## References

- `qbit-manage/spec.md` — RF-3, AC-4, AC-5, AC-6, AC-7.
- `modules/core/category.py:112-174` — `update_cat`, the single `set_category` call site.
- `docs/Config-Setup.md` — the Automatic Torrent Management warning for `cat_change`.
