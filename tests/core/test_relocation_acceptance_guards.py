"""Acceptance tests for every guard that stops a relocation (TST009).

Each test names the criterion it verifies, asserts both the effect (which client calls happened)
and the reported reason, so the guard ordering in ``Category.relocation_plan`` is pinned. A refusal
must withhold the whole category-change path; a skip must leave the category change untouched.

Only the module-level logger of ``modules.core.category`` is patched, per test through
``monkeypatch``, so combining this file with the other Category tests never leaks a recorder.
"""

from __future__ import annotations

import pytest

from tests.factories import FakeConfig
from tests.factories import FakeQbtManager
from tests.factories import FakeTorrent
from tests.factories import make_category

# Literal outcome contract. Importing modules.core.category at module scope would bind its logger
# during collection, before the per-test fixture runs, and break combined runs.
RELOCATION_SKIP_AUTO_TMM = "Automatic Torrent Management"
RELOCATION_SKIP_NO_CONFIGURED_PATH = "no unambiguous configured path"
RELOCATION_SKIP_INCOMPLETE = "incomplete"
RELOCATION_SKIP_ALREADY_IN_PLACE = "already in place"
RELOCATION_REFUSE_CROSS_SEED = "cross-seed"

CATEGORY = "Movies"
OLD_CATEGORY = "Downloads"
CONFIGURED_PATH = "/data/media/Movies"
TARGET = CONFIGURED_PATH + "/"
TORRENT_PATH = "/data/downloads/Example.Torrent"


class RecordingLogger:
    """Capture the messages Category prints, keeping the MyLogger return shapes."""

    def __init__(self):
        self.messages = []

    def print_line(self, msg, loglevel="INFO", *args, **kwargs):
        self.messages.append(str(msg))
        return [str(msg)]

    def insert_space(self, msg, space_length=0):
        return f"{' ' * space_length}{msg}"

    def separator(self, *args, **kwargs):
        return None

    def debug(self, *args, **kwargs):
        return None

    def trace(self, *args, **kwargs):
        return None

    def warning(self, *args, **kwargs):
        return None


@pytest.fixture
def category_module(monkeypatch):
    """Patch the category module logger for the duration of one test only."""
    from modules.core import category as module

    recorder = RecordingLogger()
    monkeypatch.setattr(module, "logger", recorder)
    return module, recorder


def _build(*, settings=None, category_paths=None, shared_files=False, torrent_kwargs=None):
    torrent_data = {
        "name": "Example.Torrent",
        "category": OLD_CATEGORY,
        "save_path": TORRENT_PATH,
    }
    torrent_data.update(torrent_kwargs or {})
    torrent = FakeTorrent(**torrent_data)
    cfg = FakeConfig()
    cfg.settings.update(settings or {})
    qbt = FakeQbtManager(
        torrents=[torrent],
        config=cfg,
        category_paths={CATEGORY: CONFIGURED_PATH} if category_paths is None else category_paths,
        has_shared_files=shared_files,
    )
    return make_category(qbt), qbt, cfg, torrent


def _wire_client_move(qbt):
    """Make the fake manager move the fake torrent the way Qbt.relocate_torrent does."""
    record = qbt.relocate_torrent

    def relocate_torrent(torrent, target):
        torrent.set_location(location=target)
        return record(torrent, target)

    qbt.relocate_torrent = relocate_torrent


def _call_names(torrent):
    return [name for name, _ in torrent.calls]


def _skip_lines(recorder):
    return [message for message in recorder.messages if message.startswith("Skipping relocation")]


# ── AC-4: a cross-seed sibling ───────────────────────────────────────────────


def test_ac_4_cross_seed_refusal_withholds_category_change_and_relocation(category_module):
    """AC-4, category-change path: neither the category change nor the move is requested."""
    _, recorder = category_module
    cat, qbt, _, torrent = _build(settings={"cat_change_relocate": True}, shared_files=True)

    cat.update_cat(torrent, CATEGORY, True)

    # Both withheld: no set_category, no set_auto_management, no set_location.
    assert torrent.calls == []
    assert "set_category" not in _call_names(torrent)
    assert _call_names(torrent).count("set_location") == 0
    assert qbt.relocate_torrent_calls == []
    assert qbt.has_shared_files_calls == [(torrent.hash, torrent.save_path)]
    assert cat.stats == 0

    # The refusal is logged and notified with the cross-seed reason, and nothing else runs.
    assert recorder.messages == [f"Refused to relocate {torrent.name}: {RELOCATION_REFUSE_CROSS_SEED}."]
    assert cat._relocation_counters()["refused"] == 1
    assert [attr["title"] for attr in cat.notify_attr] == ["Relocation Refused"]
    assert f"Reason: {RELOCATION_REFUSE_CROSS_SEED}" in cat.notify_attr[0]["body"]


def test_ac_4_cross_seed_refusal_withholds_only_the_move_in_the_alignment_path(category_module):
    """AC-4, alignment path: no category is written, the move is refused with the cross-seed reason."""
    _, recorder = category_module
    cat, qbt, _, torrent = _build(
        settings={"cat_update_relocate": True},
        shared_files=True,
        torrent_kwargs={"category": CATEGORY},
    )

    cat.align_locations()

    assert torrent.calls == []
    assert "set_category" not in _call_names(torrent)
    assert qbt.relocate_torrent_calls == []
    assert cat._relocation_counters()["refused"] == 1
    assert cat._relocation_counters()["skipped"] == {}
    assert recorder.messages[0] == f"Refused to relocate {torrent.name}: {RELOCATION_REFUSE_CROSS_SEED}."
    assert [attr["title"] for attr in cat.notify_attr] == ["Relocation Refused"]


# ── AC-5: an ambiguous configured path ───────────────────────────────────────


@pytest.mark.parametrize(
    "configured_path",
    [
        pytest.param("/data/media/*", id="glob-pattern"),
        pytest.param(["/data/media/A", "/data/media/B"], id="uncategorized-list"),
    ],
)
def test_ac_5_ambiguous_configured_path_is_skipped_and_the_category_change_applies(category_module, configured_path):
    """AC-5: the ambiguity is logged, the move is skipped, the category change still happens."""
    _, recorder = category_module
    cat, qbt, _, torrent = _build(
        settings={"cat_change_relocate": True},
        category_paths={CATEGORY: configured_path},
    )
    _wire_client_move(qbt)

    cat.update_cat(torrent, CATEGORY, True)

    assert _call_names(torrent) == ["set_category"]
    assert torrent.calls[0][1] == {"category": CATEGORY}
    assert torrent.category == CATEGORY
    assert qbt.relocate_torrent_calls == []
    assert qbt.has_shared_files_calls == []  # the ambiguity guard decides before the peer check

    assert _skip_lines(recorder) == [f"Skipping relocation for {torrent.name}: {RELOCATION_SKIP_NO_CONFIGURED_PATH}."]
    assert cat._relocation_counters()["skipped"] == {RELOCATION_SKIP_NO_CONFIGURED_PATH: 1}
    assert cat.stats == 1
    assert [attr["title"] for attr in cat.notify_attr] == ["Moving Categories"]


# ── AC-6: already in place ───────────────────────────────────────────────────


def test_ac_6_torrent_already_in_place_is_not_moved_and_still_categorized(category_module):
    """AC-6: no relocation request, the already-in-place reason, and the category change applies."""
    _, recorder = category_module
    cat, qbt, _, torrent = _build(
        settings={"cat_change_relocate": True},
        torrent_kwargs={"save_path": CONFIGURED_PATH},
    )
    _wire_client_move(qbt)

    cat.update_cat(torrent, CATEGORY, True)

    assert _call_names(torrent) == ["set_category"]
    assert torrent.category == CATEGORY
    assert qbt.relocate_torrent_calls == []
    assert _skip_lines(recorder) == [f"Skipping relocation for {torrent.name}: {RELOCATION_SKIP_ALREADY_IN_PLACE}."]
    assert cat._relocation_counters()["skipped"] == {RELOCATION_SKIP_ALREADY_IN_PLACE: 1}
    assert cat.stats == 1


# ── AC-7: an incomplete torrent ──────────────────────────────────────────────


def test_ac_7_incomplete_torrent_is_not_relocated_and_still_categorized(category_module):
    """AC-7: an incomplete torrent is skipped as incomplete while the category change applies."""
    _, recorder = category_module
    cat, qbt, _, torrent = _build(
        settings={"cat_change_relocate": True},
        torrent_kwargs={"state": "downloading", "progress": 0.5},
    )
    _wire_client_move(qbt)

    cat.update_cat(torrent, CATEGORY, True)

    assert _call_names(torrent) == ["set_category"]
    assert torrent.category == CATEGORY
    assert qbt.relocate_torrent_calls == []
    assert _skip_lines(recorder) == [f"Skipping relocation for {torrent.name}: {RELOCATION_SKIP_INCOMPLETE}."]
    assert cat._relocation_counters()["skipped"] == {RELOCATION_SKIP_INCOMPLETE: 1}
    assert cat.stats == 1


# ── AC-13: Automatic Torrent Management is on ────────────────────────────────


def test_ac_13_auto_tmm_torrent_is_skipped_and_counted_in_the_run_summary(category_module):
    """AC-13: ATM wins over incomplete, no location change, and the run's skip summary counts it."""
    _, recorder = category_module
    cfg = FakeConfig()
    cfg.settings["cat_update_relocate"] = True
    cfg.settings["cat_filter_completed"] = False
    torrent = FakeTorrent(
        name="Example.Torrent",
        category=CATEGORY,
        save_path=TORRENT_PATH,
        state="downloading",
        progress=0.5,
        auto_tmm=True,
    )
    qbt = FakeQbtManager(torrents=[torrent], config=cfg, category_paths={CATEGORY: CONFIGURED_PATH})

    from modules.core.category import Category

    cat = Category(qbt)

    # No location change is requested and the torrent is not handed to another location owner.
    assert torrent.calls == []
    assert qbt.relocate_torrent_calls == []

    # The ATM reason is reported even though the torrent is also incomplete: rule 1 decides.
    assert f"Skipping relocation for {torrent.name}: {RELOCATION_SKIP_AUTO_TMM}." in recorder.messages
    assert f"Skipping relocation for {torrent.name}: {RELOCATION_SKIP_INCOMPLETE}." not in recorder.messages
    assert cat._relocation_counters()["skipped"] == {RELOCATION_SKIP_AUTO_TMM: 1}

    # The run's skip summary carries the reason and the skipped torrent.
    assert len(cfg.notifications_sent) == 1
    summary = cfg.notifications_sent[0]
    assert summary["title"] == "Relocation Skipped"
    assert f"{RELOCATION_SKIP_AUTO_TMM}: 1" in summary["body"]
    assert summary["torrents"] == [torrent.name]


# ── AC-14: force_auto_tmm hands the location to qBittorrent ──────────────────


def test_ac_14_force_auto_tmm_without_ignore_tag_is_not_relocated(category_module):
    """AC-14: the category change hands the location over, so no move is requested or summarized wrong."""
    _, recorder = category_module
    cat, qbt, cfg, torrent = _build(
        settings={"cat_change_relocate": True, "force_auto_tmm": True},
    )
    _wire_client_move(qbt)

    cat.update_cat(torrent, CATEGORY, True)

    # The category change runs and enables Automatic Torrent Management; no move follows.
    assert _call_names(torrent) == ["set_category", "set_auto_management"]
    assert torrent.calls[0][1] == {"category": CATEGORY}
    assert torrent.calls[1][1] == {"enable": True}
    assert torrent.auto_tmm is True
    assert qbt.relocate_torrent_calls == []
    assert qbt.has_shared_files_calls == []
    assert _skip_lines(recorder) == [f"Skipping relocation for {torrent.name}: {RELOCATION_SKIP_AUTO_TMM}."]
    assert cat._relocation_counters()["skipped"] == {RELOCATION_SKIP_AUTO_TMM: 1}

    cat.relocation_skip_summary()

    assert len(cfg.notifications_sent) == 1
    summary = cfg.notifications_sent[0]
    assert summary["title"] == "Relocation Skipped"
    assert f"{RELOCATION_SKIP_AUTO_TMM}: 1" in summary["body"]
    assert summary["torrents"] == [torrent.name]


def test_ac_14_force_auto_tmm_with_ignore_tag_is_relocated(category_module):
    """AC-14 counterpart: an ignore tag leaves the move to the relocation pass."""
    _, recorder = category_module
    cat, qbt, _, torrent = _build(
        settings={
            "cat_change_relocate": True,
            "force_auto_tmm": True,
            "force_auto_tmm_ignore_tags": ["keep-location"],
        },
        torrent_kwargs={"tags": "keep-location"},
    )
    _wire_client_move(qbt)

    cat.update_cat(torrent, CATEGORY, True)

    assert _call_names(torrent) == ["set_category", "set_location"]
    assert torrent.calls[1][1] == {"location": TARGET}
    assert qbt.relocate_torrent_calls == [(torrent, TARGET)]
    assert cat._relocation_counters()["skipped"] == {}
    assert _skip_lines(recorder) == []
    assert f"Relocated {torrent.name} to {TARGET}." in recorder.messages
