"""Tests for Category.relocate, report_refusal, report_skip and relocation_skip_summary.

The module-level logger of ``modules.core.category`` is patched through ``monkeypatch`` only, so a
run that combines this file with the other Category tests never leaks a recorder into them.
"""

from __future__ import annotations

import pytest

from tests.factories import FakeConfig
from tests.factories import FakeQbtManager
from tests.factories import FakeTorrent
from tests.factories import make_category

TARGET = "/data/media/Movies/"
SKIP_REASONS = [
    "Automatic Torrent Management",
    "no unambiguous configured path",
    "incomplete",
    "already in place",
]


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


class StaleCategoryTorrent(FakeTorrent):
    """Mimic qbittorrentapi: ``set_category`` sends the request but keeps the old category.

    ``TorrentDictionary.set_category`` never mutates the local object, so reading
    ``torrent.category`` after a category change returns the previous one; this stand-in keeps
    that behaviour visible to the relocation tests.
    """

    def set_category(self, category):
        self._record("set_category", category=category)


@pytest.fixture
def category_module(monkeypatch):
    """Patch the category module logger for the duration of one test only."""
    from modules.core import category as module

    recorder = RecordingLogger()
    monkeypatch.setattr(module, "logger", recorder)
    return module, recorder


def _build(*, relocate_result=True, settings=None, torrent=None):
    torrent = torrent or FakeTorrent(
        name="Example.Torrent",
        category="Movies",
        save_path="/data/downloads/Example.Torrent",
    )
    cfg = FakeConfig()
    cfg.settings.update(settings or {})
    qbt = FakeQbtManager(torrents=[torrent], config=cfg, relocate_result=relocate_result)
    return make_category(qbt), qbt, cfg, torrent


# ── successful relocation ─────────────────────────────────────────────────────


def test_relocate_issues_the_move_and_records_the_success(category_module):
    _, recorder = category_module
    cat, qbt, cfg, torrent = _build()

    assert cat.relocate(torrent, TARGET) is True

    assert qbt.relocate_torrent_calls == [(torrent, TARGET)]
    assert cfg.notifications_sent == []
    assert cat.torrents_updated == [torrent.name]
    assert cat.stats == 0
    counters = cat._relocation_counters()
    assert counters["relocated"] == 1
    assert counters["failed"] == 0
    assert counters["skipped"] == {}

    assert len(recorder.messages) == 1
    assert torrent.name in recorder.messages[0]
    assert TARGET in recorder.messages[0]

    assert len(cat.notify_attr) == 1
    attr = cat.notify_attr[0]
    assert attr["function"] == "cat_update"
    assert attr["title"] == "Relocating Torrents"
    assert torrent.name in attr["body"]
    assert TARGET in attr["body"]
    assert attr["torrents"] == [torrent.name]
    assert attr["torrent_category"] == "Movies"
    assert attr["torrent_tag"] == ""
    assert attr["torrent_tracker"] == "http://tracker1.example/announce"
    assert attr["notifiarr_indexer"] is None


# ── failed relocation ─────────────────────────────────────────────────────────


def test_relocation_attribute_reports_the_post_change_category(category_module):
    cat, qbt, cfg, torrent = _build(
        torrent=StaleCategoryTorrent(name="Stale.Torrent", category="", save_path="/data/downloads/Stale.Torrent")
    )
    torrent.set_category(category="Movies")
    assert torrent.category == ""

    assert cat.relocate(torrent, TARGET, category="Movies") is True

    assert qbt.relocate_torrent_calls == [(torrent, TARGET)]
    assert cfg.notifications_sent == []
    assert cat.notify_attr[0]["torrent_category"] == "Movies"


def test_relocation_failure_attribute_reports_the_post_change_category(category_module):
    cat, _, _, torrent = _build(
        relocate_result=False,
        torrent=StaleCategoryTorrent(name="Stale.Torrent", category="", save_path="/data/downloads/Stale.Torrent"),
    )
    torrent.set_category(category="Movies")

    assert cat.relocate(torrent, TARGET, category="Movies") is False

    assert cat.notify_attr[0]["torrent_category"] == "Movies"


def test_relocate_reports_a_failure_without_counting_or_raising(category_module):
    _, recorder = category_module
    cat, qbt, cfg, torrent = _build(relocate_result=False)

    assert cat.relocate(torrent, TARGET) is False

    assert qbt.relocate_torrent_calls == [(torrent, TARGET)]
    assert cfg.notifications_sent == []
    assert cat.torrents_updated == []
    assert cat.stats == 0
    counters = cat._relocation_counters()
    assert counters["relocated"] == 0
    assert counters["failed"] == 1

    assert len(recorder.messages) == 1
    assert torrent.name in recorder.messages[0]
    assert TARGET in recorder.messages[0]

    assert len(cat.notify_attr) == 1
    attr = cat.notify_attr[0]
    assert attr["function"] == "cat_update"
    assert attr["title"] == "Relocation Failed"
    assert torrent.name in attr["body"]
    assert TARGET in attr["body"]
    assert attr["torrents"] == [torrent.name]
    assert attr["torrent_category"] == "Movies"


# ── refusal ───────────────────────────────────────────────────────────────────


def test_report_refusal_logs_and_notifies_its_reason(category_module):
    _, recorder = category_module
    cat, qbt, cfg, torrent = _build()

    cat.report_refusal(torrent, "cross-seed")

    assert qbt.relocate_torrent_calls == []
    assert cfg.notifications_sent == []
    assert cat.stats == 0
    counters = cat._relocation_counters()
    assert counters["refused"] == 1
    assert counters["relocated"] == 0

    assert len(recorder.messages) == 1
    assert torrent.name in recorder.messages[0]
    assert "cross-seed" in recorder.messages[0]

    assert len(cat.notify_attr) == 1
    attr = cat.notify_attr[0]
    assert attr["function"] == "cat_update"
    assert attr["title"] == "Relocation Refused"
    assert "cross-seed" in attr["body"]
    assert attr["torrents"] == [torrent.name]
    assert attr["torrent_category"] == "Movies"
    assert attr["torrent_tag"] == ""
    assert attr["torrent_tracker"] == "http://tracker1.example/announce"
    assert attr["notifiarr_indexer"] is None


# ── skips ─────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("reason", SKIP_REASONS)
def test_report_skip_counts_exactly_one_reason_without_notifying(category_module, reason):
    module, recorder = category_module
    cat, qbt, cfg, torrent = _build()
    plan = module.RelocationPlan(action=module.RELOCATION_ACTION_SKIP, reason=reason)

    cat.report_skip(torrent, plan)

    assert qbt.relocate_torrent_calls == []
    assert cat.notify_attr == []
    assert cfg.notifications_sent == []
    assert cat.torrents_updated == []
    assert cat.stats == 0

    counters = cat._relocation_counters()
    assert counters["skipped"] == {reason: 1}
    assert counters["skipped_names"] == [torrent.name]

    assert len(recorder.messages) == 1
    assert torrent.name in recorder.messages[0]
    assert reason in recorder.messages[0]


def test_report_skip_accumulates_each_reason(category_module):
    module, _ = category_module
    cat, _, _, torrent = _build()
    other = FakeTorrent(name="Other.Torrent", category="Movies")

    cat.report_skip(torrent, module.RelocationPlan(action="skip", reason="incomplete"))
    cat.report_skip(other, module.RelocationPlan(action="skip", reason="incomplete"))
    cat.report_skip(other, module.RelocationPlan(action="skip", reason="already in place"))

    counters = cat._relocation_counters()
    assert counters["skipped"] == {"incomplete": 2, "already in place": 1}
    assert counters["skipped_names"] == [torrent.name, other.name, other.name]


# ── skip summary ──────────────────────────────────────────────────────────────


def test_relocation_skip_summary_is_sent_once_through_send_notifications(category_module):
    module, _ = category_module
    cat, qbt, cfg, torrent = _build()
    other = FakeTorrent(name="Other.Torrent", category="Movies")

    cat.report_skip(torrent, module.RelocationPlan(action="skip", reason="incomplete"))
    cat.report_skip(other, module.RelocationPlan(action="skip", reason="already in place"))
    cat.relocation_skip_summary()

    assert len(cfg.notifications_sent) == 1
    attr = cfg.notifications_sent[0]
    assert attr["function"] == "cat_update"
    assert attr["title"] == "Relocation Skipped"
    assert "incomplete: 1" in attr["body"]
    assert "already in place: 1" in attr["body"]
    assert attr["torrents"] == [torrent.name, other.name]
    assert attr["torrent_category"] is None
    assert attr["torrent_tag"] is None
    assert attr["torrent_tracker"] is None
    assert attr["notifiarr_indexer"] is None

    # The summary never travels through the grouping path.
    assert cat.notify_attr == []
    assert cfg.notify_calls == []
    assert qbt.relocate_torrent_calls == []
    assert cat.stats == 0


def test_relocation_skip_summary_sends_nothing_without_skips(category_module):
    cat, _, cfg, _ = _build()

    cat.relocation_skip_summary()

    assert cfg.notifications_sent == []
    assert cat.notify_attr == []
