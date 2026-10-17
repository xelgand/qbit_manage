---
id: qbit-manage
type: project
status: active
language: en
created: 2026-10-17
updated: 2026-10-17
approvers:
  - xelgand
tracking:
  mode: none
control_repository:
  provider: github
  repository: xelgand/qbit_manage
  web_url: https://github.com/xelgand/qbit_manage
  default_branch: develop
  workflow: pull-request
adoption:
  id: adoption-2026-10
  complete: false
  source:
    kind: repository
    reference: https://github.com/xelgand/qbit_manage/tree/3984bbb8640e97fd943f997dcc83fc0c4a9d973b
---

# qBit Manage

## Purpose

qBit Manage is a Python automation tool for qBittorrent: tagging by tracker, category assignment
by save path, category changes, share-limit enforcement, hardlink-aware no-hardlink tagging,
orphan and unregistered removal, plus a web UI and a REST API. This Specbound project adopts the
existing repository and governs new work on it, starting with relocating a torrent's download
path to the default path configured for its category.

## Documents

- Spec: [[spec]]
- Plan: [[plan]]

## Adoption inventory

Statements about the pre-Specbound state, each labeled by how it is known.

### Observed

- Repository: `git@github.com:xelgand/qbit_manage.git`, provider GitHub, default branch `develop`
  (`origin/HEAD` -> `origin/develop`).
- Baseline commit `3984bbb8640e97fd943f997dcc83fc0c4a9d973b` ("chore: bump VERSION to
  4.13.1-develop27"), tip of local `develop` at adoption time. It is readable locally.
- At the baseline commit the repository contains no `tasks/`, `epics/`, `adr/`, `spec.md`,
  `plan.md`, `architecture.md` or `project.md`, so no Specbound tasks are inherited as finished.
- Branch model in `AGENTS.md`: all pull requests target `develop`; `master` takes stable releases
  only. Only `develop` exists locally and on `origin`.
- Project documentation at the baseline: `README.md`, `AGENTS.md`, `CLAUDE.md`, `DEVELOPER.md`,
  `CHANGELOG`, `docs/` (wiki source, synced bidirectionally with the GitHub Wiki).
- Test suite: `pytest tests/` (~168 tests per `AGENTS.md`), factories in `tests/factories.py`.
- The repository is a fork; the upstream project is `StuffAnThings/qbit_manage` (referenced in
  `AGENTS.md` and `docs/`).

### Decided by a person

- Adoption route: full brownfield adoption under Specbound (xelgand, 2026-10-17).
- First governed feature: relocate a torrent's download path to the category's configured default
  path, applied by both `cat_update` and `cat_change` behind opt-in flags (xelgand, 2026-10-17).
- Approvers: `xelgand`; tracking mode: `none`; workflow: `pull-request`; language: `en`
  (xelgand, 2026-10-17).
- Project id `qbit-manage` lives in the `qbit-manage/` subdirectory because the repository
  directory name `qbit_manage` is not kebab-case and fails `specbound validate`
  (`slug-not-kebab-case`).

### Not checkable

- Whether work in progress exists outside this clone (forks, un-pushed branches, the upstream
  repository). No source available here proves or disproves it; assumed none for this repository.
- Whether any of the pre-existing documented behavior was ever formally verified beyond the
  existing pytest suite and CI workflows.
