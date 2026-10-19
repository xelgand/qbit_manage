"""Tests for Category.relocation_enabled and Category.relocation_plan.

Uses the make_category() bypass constructor so __init__'s eager work does not
fire. Every plan is pure: no set_location must ever be recorded.
"""

from __future__ import annotations

import pytest

from tests.factories import FakeConfig
from tests.factories import FakeQbtManager
from tests.factories import FakeTorrent
from tests.factories import make_category

# Literal outcome contract. Importing these from modules.core.category at module
# scope would import Category during collection, before the autouse fake_logger
# fixture runs, leaving the module-level logger bound to the unset proxy and
# breaking the other Category test modules in a combined run.
RELOCATION_ACTION_RELOCATE = "relocate"
RELOCATION_ACTION_SKIP = "skip"
RELOCATION_ACTION_REFUSE = "refuse"
RELOCATION_SKIP_AUTO_TMM = "Automatic Torrent Management"
RELOCATION_SKIP_NO_CONFIGURED_PATH = "no unambiguous configured path"
RELOCATION_SKIP_INCOMPLETE = "incomplete"
RELOCATION_SKIP_ALREADY_IN_PLACE = "already in place"
RELOCATION_REFUSE_CROSS_SEED = "cross-seed"

CATEGORY = "Movies"
CONFIGURED_PATH = "/data/media/Movies"
OTHER_PATH = "/data/media/Other"


def _torrent(**overrides):
    """A completed, non-ATM torrent whose save path differs from the configured one."""
    data = {"category": CATEGORY, "save_path": OTHER_PATH, "state": "uploading"}
    data.update(overrides)
    return FakeTorrent(**data)


def _evaluate(torrent, *, cat_change=False, settings=None, paths=None, shared_files=False):
    cfg = FakeConfig()
    cfg.settings.update(settings or {})
    qbt = FakeQbtManager(
        torrents=[torrent],
        config=cfg,
        category_paths={"Movies": CONFIGURED_PATH} if paths is None else paths,
        has_shared_files=shared_files,
    )
    cat = make_category(qbt)
    return cat.relocation_plan(torrent, CATEGORY, cat_change), qbt, torrent


def _assert_skip(plan, reason):
    assert plan.action == RELOCATION_ACTION_SKIP
    assert plan.reason == reason
    assert plan.target is None
    assert plan.relocates is False


def _assert_refuse(plan, reason):
    assert plan.action == RELOCATION_ACTION_REFUSE
    assert plan.reason == reason
    assert plan.target is None
    assert plan.relocates is False


def _assert_relocate(plan, target):
    assert plan.action == RELOCATION_ACTION_RELOCATE
    assert plan.reason is None
    assert plan.target == target
    assert plan.relocates is True


def _assert_no_location_change(torrent):
    assert [call for call in torrent.calls if call[0] == "set_location"] == []


# ── relocation_enabled ────────────────────────────────────────────────────────


def test_relocation_enabled_selects_key_for_each_path():
    cfg = FakeConfig()
    cfg.settings["cat_update_relocate"] = False
    cfg.settings["cat_change_relocate"] = True
    cat = make_category(FakeQbtManager(config=cfg))

    assert cat.relocation_enabled(cat_change=False) is False
    assert cat.relocation_enabled(cat_change=True) is True


# ── rule 1: effective Automatic Torrent Management ────────────────────────────


def test_auto_tmm_torrent_is_skipped():
    plan, qbt, torrent = _evaluate(_torrent(auto_tmm=True))

    _assert_skip(plan, RELOCATION_SKIP_AUTO_TMM)
    assert qbt.has_shared_files_calls == []
    _assert_no_location_change(torrent)


def test_auto_tmm_torrent_is_skipped_on_alignment_path():
    plan, qbt, torrent = _evaluate(_torrent(auto_tmm=True), cat_change=False)

    _assert_skip(plan, RELOCATION_SKIP_AUTO_TMM)
    assert qbt.has_shared_files_calls == []
    _assert_no_location_change(torrent)


def test_force_auto_tmm_without_ignore_tag_skips_on_category_change():
    plan, qbt, torrent = _evaluate(
        _torrent(tags=""),
        cat_change=True,
        settings={"force_auto_tmm": True, "force_auto_tmm_ignore_tags": ["keep"]},
    )

    _assert_skip(plan, RELOCATION_SKIP_AUTO_TMM)
    assert qbt.has_shared_files_calls == []
    _assert_no_location_change(torrent)


def test_force_auto_tmm_with_matching_ignore_tag_proceeds():
    plan, qbt, torrent = _evaluate(
        _torrent(tags="keep,other"),
        cat_change=True,
        settings={"force_auto_tmm": True, "force_auto_tmm_ignore_tags": ["keep"]},
    )

    _assert_relocate(plan, CONFIGURED_PATH + "/")
    assert len(qbt.has_shared_files_calls) == 1
    _assert_no_location_change(torrent)


def test_force_auto_tmm_is_not_applied_on_alignment_path():
    plan, qbt, torrent = _evaluate(
        _torrent(tags=""),
        cat_change=False,
        settings={"force_auto_tmm": True, "force_auto_tmm_ignore_tags": ["keep"]},
    )

    _assert_relocate(plan, CONFIGURED_PATH + "/")
    assert len(qbt.has_shared_files_calls) == 1
    _assert_no_location_change(torrent)


# ── rule 2: no unambiguous configured path ────────────────────────────────────


def test_absent_category_is_skipped():
    plan, qbt, torrent = _evaluate(_torrent(), paths={})

    _assert_skip(plan, RELOCATION_SKIP_NO_CONFIGURED_PATH)
    assert qbt.has_shared_files_calls == []
    _assert_no_location_change(torrent)


def test_list_configured_path_is_skipped():
    plan, qbt, torrent = _evaluate(_torrent(), paths={"Movies": ["/data/media/A", "/data/media/B"]})

    _assert_skip(plan, RELOCATION_SKIP_NO_CONFIGURED_PATH)
    assert qbt.has_shared_files_calls == []
    _assert_no_location_change(torrent)


def test_glob_configured_path_is_skipped():
    plan, qbt, torrent = _evaluate(_torrent(), paths={"Movies": "/data/media/*"})

    _assert_skip(plan, RELOCATION_SKIP_NO_CONFIGURED_PATH)
    assert qbt.has_shared_files_calls == []
    _assert_no_location_change(torrent)


# ── rule 3: incomplete ────────────────────────────────────────────────────────


def test_incomplete_torrent_is_skipped():
    plan, qbt, torrent = _evaluate(_torrent(state="downloading", progress=0.5))

    _assert_skip(plan, RELOCATION_SKIP_INCOMPLETE)
    assert qbt.has_shared_files_calls == []
    _assert_no_location_change(torrent)


# ── rule 4: already in place ──────────────────────────────────────────────────


def test_path_equal_after_normalization_is_skipped():
    plan, qbt, torrent = _evaluate(_torrent(save_path=CONFIGURED_PATH))

    _assert_skip(plan, RELOCATION_SKIP_ALREADY_IN_PLACE)
    assert qbt.has_shared_files_calls == []
    _assert_no_location_change(torrent)


# ── rule 5: shared file refusal ───────────────────────────────────────────────


def test_shared_file_refuses_the_relocation():
    plan, qbt, torrent = _evaluate(_torrent(), shared_files=True)

    _assert_refuse(plan, RELOCATION_REFUSE_CROSS_SEED)
    assert qbt.has_shared_files_calls == [(torrent.hash, OTHER_PATH)]
    _assert_no_location_change(torrent)


def test_peers_without_shared_files_relocate():
    plan, qbt, torrent = _evaluate(_torrent(), shared_files=False)

    _assert_relocate(plan, CONFIGURED_PATH + "/")
    assert len(qbt.has_shared_files_calls) == 1
    _assert_no_location_change(torrent)


# ── ordering ──────────────────────────────────────────────────────────────────


def test_auto_tmm_wins_over_incomplete():
    plan, qbt, torrent = _evaluate(_torrent(auto_tmm=True, state="downloading"))

    _assert_skip(plan, RELOCATION_SKIP_AUTO_TMM)
    assert qbt.has_shared_files_calls == []
    _assert_no_location_change(torrent)


def test_auto_tmm_wins_over_absent_configured_path():
    plan, qbt, torrent = _evaluate(_torrent(auto_tmm=True), paths={})

    _assert_skip(plan, RELOCATION_SKIP_AUTO_TMM)
    assert qbt.has_shared_files_calls == []
    _assert_no_location_change(torrent)


def test_absent_configured_path_wins_over_shared_file():
    plan, qbt, torrent = _evaluate(_torrent(), paths={}, shared_files=True)

    _assert_skip(plan, RELOCATION_SKIP_NO_CONFIGURED_PATH)
    assert qbt.has_shared_files_calls == []
    _assert_no_location_change(torrent)


def test_incomplete_wins_over_shared_file():
    plan, qbt, torrent = _evaluate(_torrent(state="downloading"), shared_files=True)

    _assert_skip(plan, RELOCATION_SKIP_INCOMPLETE)
    assert qbt.has_shared_files_calls == []
    _assert_no_location_change(torrent)


def test_already_in_place_wins_over_shared_file():
    plan, qbt, torrent = _evaluate(_torrent(save_path=CONFIGURED_PATH), shared_files=True)

    _assert_skip(plan, RELOCATION_SKIP_ALREADY_IN_PLACE)
    assert qbt.has_shared_files_calls == []
    _assert_no_location_change(torrent)


@pytest.mark.parametrize(
    ("settings", "cat_change"),
    [
        ({"force_auto_tmm": False}, True),
        ({}, False),
    ],
)
def test_only_rule_five_performs_a_client_call(settings, cat_change):
    """A passing plan calls the peer check exactly once; a decided plan calls it zero times."""
    passing, passing_qbt, _ = _evaluate(_torrent(), cat_change=cat_change, settings=settings)
    assert passing.relocates is True
    assert len(passing_qbt.has_shared_files_calls) == 1

    decided, decided_qbt, _ = _evaluate(_torrent(auto_tmm=True), cat_change=cat_change, settings=settings)
    assert decided.action == RELOCATION_ACTION_SKIP
    assert decided_qbt.has_shared_files_calls == []
