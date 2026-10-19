"""Executable acceptance scenarios for relocating torrents to a category's configured path.

Each test proves one acceptance criterion of ``spec.md`` through the observable outcome: the
location requested from the client (the recorded ``set_location`` target) and the torrent's
category. All of them run on the shared fakes; no live qBittorrent instance is involved.

The module-level logger of ``modules.core.category`` is patched through ``monkeypatch`` inside a
fixture only, so combining this file with the other Category tests never leaks a recorder.
"""

from __future__ import annotations

import pytest

from tests.factories import FakeConfig
from tests.factories import FakeQbtManager
from tests.factories import FakeTorrent
from tests.factories import make_category

CATEGORY = "Movies"
CONFIGURED_PATH = "/data/media/Movies"
TARGET = "/data/media/Movies/"
SAVE_PATH = "/data/downloads/Example.Torrent"


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


def _torrent(**overrides):
    data = {
        "name": "Example.Torrent",
        "category": "",
        "save_path": SAVE_PATH,
        "state": "uploading",
        "auto_tmm": False,
    }
    data.update(overrides)
    return FakeTorrent(**data)


def _build(torrent, *, settings=None):
    cfg = FakeConfig()
    cfg.settings.update(settings or {})
    qbt = FakeQbtManager(
        torrents=[torrent],
        config=cfg,
        category_paths={CATEGORY: CONFIGURED_PATH},
    )
    return make_category(qbt), qbt, cfg


def _wire_client_move(qbt):
    """Make the fake manager move the fake torrent the way Qbt.relocate_torrent does."""
    record = qbt.relocate_torrent

    def relocate_torrent(torrent, target):
        torrent.set_location(location=target)
        return record(torrent, target)

    qbt.relocate_torrent = relocate_torrent


def _set_location_targets(torrent):
    return [kwargs["location"] for name, kwargs in torrent.calls if name == "set_location"]


# ── AC-1: relocation follows a category assigned by cat_update ────────────────


def test_ac1_cat_update_relocates_a_torrent_to_its_new_category_path(category_module):
    """AC-1: cat_update applies a category and moves the torrent to its configured path.

    Given relocation is enabled for cat_update and Automatic Torrent Management is disabled for
    the torrent, and the torrent is assigned a category whose configured path differs from its
    save path, when cat_update applies the category, then the torrent's location is set to that
    configured path and it carries the assigned category.
    """
    _, _ = category_module
    torrent = _torrent()
    cat, qbt, _ = _build(torrent, settings={"cat_update_relocate": True})
    _wire_client_move(qbt)

    cat.update_cat(torrent, CATEGORY, False)

    assert _set_location_targets(torrent) == [TARGET]
    assert qbt.relocate_torrent_calls == [(torrent, TARGET)]
    assert torrent.category == CATEGORY
    assert cat._relocation_counters()["relocated"] == 1


# ── AC-2: relocation follows a category change ───────────────────────────────


def test_ac2_cat_change_relocates_a_completed_torrent_to_the_new_category_path(category_module):
    """AC-2: cat_change switches a completed torrent and moves it to the new category's path.

    Given relocation is enabled for cat_change and Automatic Torrent Management is disabled, and
    a completed torrent is switched to a category with a different configured path, when
    cat_change applies the switch, then the torrent's location is set to the new category's
    configured path and it carries the new category.
    """
    _, _ = category_module
    torrent = _torrent(category="Downloads", state="uploading", auto_tmm=False)
    cat, qbt, _ = _build(torrent, settings={"cat_change_relocate": True})
    _wire_client_move(qbt)

    cat.update_cat(torrent, CATEGORY, True)

    assert _set_location_targets(torrent) == [TARGET]
    assert qbt.relocate_torrent_calls == [(torrent, TARGET)]
    assert torrent.category == CATEGORY
    assert cat._relocation_counters()["relocated"] == 1


# ── AC-12: an already-categorized torrent is aligned without a category write ─


def test_ac12_cat_update_aligns_an_already_categorized_torrent_and_leaves_its_category(category_module):
    """AC-12: the alignment pass moves a categorized torrent and does not rewrite its category.

    Given relocation is enabled for cat_update and Automatic Torrent Management is disabled, and
    a completed torrent carries a category whose configured path differs from its save path, when
    cat_update runs, then the torrent's location is set to that configured path and its category
    is left unchanged.
    """
    _, _ = category_module
    torrent = _torrent(category=CATEGORY, state="uploading", auto_tmm=False)
    cfg = FakeConfig()
    cfg.settings["cat_update_relocate"] = True
    qbt = FakeQbtManager(
        torrents=[torrent],
        config=cfg,
        category_paths={CATEGORY: CONFIGURED_PATH},
    )
    _wire_client_move(qbt)

    from modules.core.category import Category

    Category(qbt)

    assert _set_location_targets(torrent) == [TARGET]
    assert qbt.relocate_torrent_calls == [(torrent, TARGET)]
    # The alignment pass trusts the category it finds: no set_category call and no rewrite.
    assert [name for name, _ in torrent.calls] == ["set_location"]
    assert torrent.category == CATEGORY
