---
type: plan
revision: 1
project: qbit-manage
derived_from:
  spec.md: 1
repositories:
  qbit-manage:
    provider: github
    repository: xelgand/qbit_manage
    web_url: https://github.com/xelgand/qbit_manage
    default_branch: develop
    workflow: pull-request
created: 2026-10-17
updated: 2026-10-18
---

# Plan: qBit Manage — relocate torrents to the category's configured path

## Approach

Extend the two existing category commands instead of adding a new one. A single relocation
routine, shared by `cat_update` and `cat_change`, resolves the configured `cat:` path for the
target category, applies the guards from the spec (cross-seed sharing, ambiguous paths,
already-in-place, incomplete torrents, Automatic Torrent Management), and issues qBittorrent's
`set_location` through the existing API error-handling wrapper. Both commands enable it
independently through new, individually documented configuration keys. For `cat_update` the
routine serves two entry points: the existing category assignment, and an alignment pass that
walks already-categorized torrents whose location does not match their category's configured path
— the part of a library today's category filter never reaches. The feature rides the existing
command wiring (argparse, scheduler, web API, webhooks) untouched, because it changes behavior
inside commands that already exist.

## Phases

1. **Configuration surface.** Register and validate the new keys in `modules/config.py`, the
   sample config, the setup docs and the web UI schema. Makes the opt-in expressible; alone it
   changes no behavior.
2. **Relocation core.** Implement the guarded relocation routine and its unit tests, including
   the cross-seed detection that must work during `cat_update` runs, where the full torrent file
   map is not built today. Makes relocation correct in isolation.
3. **Command integration.** Wire the routine into `cat_change` and both `cat_update` entry points
   (category assignment and the alignment pass) with per-command flags, dry-run support and
   per-torrent failure isolation. Delivers the observable behavior of the spec.

## Repositories

- `qbit-manage`: the only work repository; holds the code, the tests and these artifacts.

## Technology

- `qbittorrent-api`'s `TorrentDictionary.set_location`, following the repository's established
  pattern of calling client methods directly under the `@handle_qbit_api_errors` decorator (as
  `set_category` and `recheck` already do).
- The existing `check_for_attribute` configuration registration and `normalize_cat_change`
  parsing for the new keys.
- `pytest` with the existing bypass-constructor factories (`make_category`, `FakeTorrent`,
  `FakeConfig`, `FakeQbtManager`) for unit tests.

## Verification

- Unit tests per guard and per command path, run with `pytest tests/core/` and
  `pytest tests/test_config*`, using the existing factories; relocation requests asserted on the
  fake torrent's recorded calls.
- Acceptance tests per `AC-N`, expressed on those same fakes; no live qBittorrent instance is
  required.
- `make lint`, `make format` and `make pre-commit` before every pull request, per AGENTS.md.
- Closure: the full suite (`pytest tests/`) once on the final release candidate.

## Architecture decisions

- ADR: where does the opt-in live — a global `settings` key, a per-`cat_change`-mapping key in
  the extended form, or a combination — and what are the exact key names?
- ADR: on a guarded skip (for example a cross-seed sibling), is the category change still
  applied or is the torrent left untouched?
- ADR: how is cross-seed sharing detected during `cat_update`, where the full torrent file map
  is not built today — build the file map for these commands, or use a cheaper save-path-equality
  scan?
- ADR: does relocation guard against breaking external hardlinks, and at what cost in filesystem
  access?

## Risks

- **Data movement breakage.** `set_location` moves files on disk; cross-seed siblings and
  external hardlink users can break. Reduced by the RF-3 guards, conservative skip-by-default on
  any ambiguity, and dry-run support for rehearsal.
- **Path-space confusion.** Relocation targets must stay in qBittorrent path space; local checks
  need the `root_dir`/`remote_dir` mapping. Reduced by resolving targets exclusively from the
  `cat:` configuration and covering the mapping in unit tests.
- **Interaction with Automatic Torrent Management.** With ATM enabled, qBittorrent itself relocates
  a torrent to its own per-category save path when the category changes. Reduced by excluding
  ATM-managed torrents from relocation (AC-13), so no category change and location change is ever
  sequenced against the client's own move, and by documenting that the client's category path
  governs for them.
- **Widened blast radius from the alignment pass.** RF-6 makes `cat_update` touch torrents it never
  touched before, on a path where the category is trusted as correct. Reduced by keeping the pass
  behind the same opt-in key, by the shared guards, by dry-run support and by per-torrent failure
  isolation.

## Open questions

- None blocks the proposal; the spec's open questions are the ADRs listed above.
