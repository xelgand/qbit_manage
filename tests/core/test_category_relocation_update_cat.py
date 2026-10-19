"""Tests for the relocation integration inside Category.update_cat.

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
TRACKER = "http://tracker1.example/announce"


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
    """Mimic qbittorrentapi: ``set_category`` sends the request but keeps the old category."""

    def set_category(self, category):
        self._record("set_category", category=category)


@pytest.fixture
def category_module(monkeypatch):
    """Patch the category module logger for the duration of one test only."""
    from modules.core import category as module

    recorder = RecordingLogger()
    monkeypatch.setattr(module, "logger", recorder)
    return module, recorder


def _build(*, settings=None, dry_run=False, category_paths=None, has_shared_files=False, torrent=None, **torrent_kwargs):
    torrent = torrent or FakeTorrent(
        name="Example.Torrent",
        category="Downloads",
        save_path="/data/downloads/Example.Torrent",
        **torrent_kwargs,
    )
    cfg = FakeConfig()
    cfg.settings.update(settings or {})
    cfg.dry_run = dry_run
    qbt = FakeQbtManager(
        torrents=[torrent],
        config=cfg,
        category_paths=category_paths or {},
        has_shared_files=has_shared_files,
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


# ── relocation after the category change ─────────────────────────────────────


def test_update_cat_relocates_after_the_category_change(category_module):
    _, recorder = category_module
    cat, qbt, _, torrent = _build(
        settings={"cat_update_relocate": True},
        category_paths={"Movies": "/data/media/Movies"},
    )
    _wire_client_move(qbt)

    cat.update_cat(torrent, "Movies", False)

    assert _call_names(torrent) == ["set_category", "set_location"]
    assert torrent.calls[1][1] == {"location": TARGET}
    assert qbt.relocate_torrent_calls == [(torrent, TARGET)]
    assert cat.stats == 1
    assert cat.torrents_updated == [torrent.name, torrent.name]

    # The relocation attribute is built by relocate() before update_cat appends the category one.
    titles = [attr["title"] for attr in cat.notify_attr]
    assert titles == ["Relocating Torrents", "Updating Categories"]
    assert any(f"Relocated {torrent.name} to {TARGET}" in message for message in recorder.messages)


def test_update_cat_reads_the_cat_change_key_on_that_path(category_module):
    _, recorder = category_module
    cat, qbt, _, torrent = _build(
        settings={"cat_change_relocate": True},
        category_paths={"Movies": "/data/media/Movies"},
    )
    _wire_client_move(qbt)

    cat.update_cat(torrent, "Movies", True)

    assert _call_names(torrent) == ["set_category", "set_location"]
    assert qbt.relocate_torrent_calls == [(torrent, TARGET)]
    assert [attr["title"] for attr in cat.notify_attr] == ["Relocating Torrents", "Moving Categories"]
    assert any(f"Relocated {torrent.name} to {TARGET}" in message for message in recorder.messages)


def test_update_cat_does_not_relocate_when_the_category_change_fails(category_module):
    from qbittorrentapi import InvalidRequest400Error

    _, recorder = category_module
    cat, qbt, _, torrent = _build(
        settings={"cat_update_relocate": True},
        category_paths={"Movies": "/data/media/Movies"},
    )
    _wire_client_move(qbt)

    def failing_set_category(category):
        raise InvalidRequest400Error("category rejected by client")

    torrent.set_category = failing_set_category

    cat.update_cat(torrent, "Movies", False)

    # The handler swallowed the API error, so the category is unchanged: no move may follow.
    assert torrent.calls == []
    assert qbt.relocate_torrent_calls == []
    assert torrent.category == "Downloads"
    assert cat._relocation_counters()["relocated"] == 0
    assert [attr["title"] for attr in cat.notify_attr] == ["Updating Categories"]


# ── refusal withholds the whole torrent ──────────────────────────────────────


def test_update_cat_refusal_withholds_category_and_relocation(category_module):
    _, recorder = category_module
    cat, qbt, _, torrent = _build(
        settings={"cat_update_relocate": True},
        category_paths={"Movies": "/data/media/Movies"},
        has_shared_files=True,
    )

    cat.update_cat(torrent, "Movies", False)

    assert torrent.calls == []
    assert qbt.relocate_torrent_calls == []
    assert cat.stats == 0
    assert cat.torrents_updated == [torrent.name]
    assert cat._relocation_counters()["refused"] == 1

    # Only the refusal is reported: the category-change lines never run.
    assert len(recorder.messages) == 1
    assert f"Refused to relocate {torrent.name}: cross-seed." == recorder.messages[0]
    assert len(cat.notify_attr) == 1
    attr = cat.notify_attr[0]
    assert attr["title"] == "Relocation Refused"
    assert "cross-seed" in attr["body"]
    assert attr["torrents"] == [torrent.name]


# ── skip leaves the category change alone ────────────────────────────────────


def test_update_cat_skip_reports_once_and_keeps_the_category_change(category_module):
    from modules.core.category import RELOCATION_SKIP_INCOMPLETE

    _, recorder = category_module
    cat, qbt, cfg, torrent = _build(
        settings={"cat_update_relocate": True},
        category_paths={"Movies": "/data/media/Movies"},
        state="downloading",
    )
    _wire_client_move(qbt)

    cat.update_cat(torrent, "Movies", False)

    assert _call_names(torrent) == ["set_category"]
    assert qbt.relocate_torrent_calls == []
    assert cat.stats == 1

    counters = cat._relocation_counters()
    assert counters["skipped"] == {RELOCATION_SKIP_INCOMPLETE: 1}
    assert counters["skipped_names"] == [torrent.name]

    skip_lines = [message for message in recorder.messages if message.startswith("Skipping relocation")]
    assert skip_lines == [f"Skipping relocation for {torrent.name}: {RELOCATION_SKIP_INCOMPLETE}."]

    # The only notification is the category one; the run-level skip summary stays unwired here.
    assert cfg.notifications_sent == []
    assert [attr["title"] for attr in cat.notify_attr] == ["Updating Categories"]


def test_update_cat_cat_change_path_lets_force_auto_tmm_skip_the_move(category_module):
    from modules.core.category import RELOCATION_SKIP_AUTO_TMM

    _, recorder = category_module
    cat, qbt, _, torrent = _build(
        settings={"cat_change_relocate": True, "force_auto_tmm": True},
        category_paths={"Movies": "/data/media/Movies"},
    )
    _wire_client_move(qbt)

    cat.update_cat(torrent, "Movies", True)

    assert _call_names(torrent) == ["set_category", "set_auto_management"]
    assert qbt.relocate_torrent_calls == []
    assert qbt.has_shared_files_calls == []
    assert cat._relocation_counters()["skipped"] == {RELOCATION_SKIP_AUTO_TMM: 1}
    assert len(recorder.messages) == 4 + 1  # one skip line, then the unchanged category block


def test_update_cat_cat_update_path_lets_force_auto_tmm_skip_the_move(category_module):
    from modules.core.category import RELOCATION_SKIP_AUTO_TMM

    _, recorder = category_module
    cat, qbt, _, torrent = _build(
        settings={"cat_update_relocate": True, "force_auto_tmm": True},
        category_paths={"Movies": "/data/media/Movies"},
    )
    _wire_client_move(qbt)

    # cat_update is a category change too: its set_category enables ATM for this torrent.
    cat.update_cat(torrent, "Movies", False)

    assert _call_names(torrent) == ["set_category", "set_auto_management"]
    assert qbt.relocate_torrent_calls == []
    assert qbt.has_shared_files_calls == []
    assert cat._relocation_counters()["skipped"] == {RELOCATION_SKIP_AUTO_TMM: 1}
    assert f"Skipping relocation for {torrent.name}: {RELOCATION_SKIP_AUTO_TMM}." in recorder.messages


def test_update_cat_cat_update_path_relocates_when_an_ignore_tag_protects_the_torrent(category_module):
    _, recorder = category_module
    cat, qbt, _, torrent = _build(
        settings={"cat_update_relocate": True, "force_auto_tmm": True, "force_auto_tmm_ignore_tags": ["Keep"]},
        category_paths={"Movies": "/data/media/Movies"},
        tags="Keep",
    )
    _wire_client_move(qbt)

    cat.update_cat(torrent, "Movies", False)

    assert _call_names(torrent) == ["set_category", "set_location"]
    assert qbt.relocate_torrent_calls == [(torrent, TARGET)]
    assert cat._relocation_counters()["skipped"] == {}
    assert any(f"Relocated {torrent.name} to {TARGET}" in message for message in recorder.messages)


def test_update_cat_relocation_reports_the_post_change_category(category_module):
    _, _ = category_module
    cat, qbt, _, torrent = _build(
        settings={"cat_update_relocate": True},
        category_paths={"Movies": "/data/media/Movies"},
        torrent=StaleCategoryTorrent(
            name="Stale.Torrent",
            category="Downloads",
            save_path="/data/downloads/Stale.Torrent",
        ),
    )
    _wire_client_move(qbt)

    cat.update_cat(torrent, "Movies", False)

    # The client never mutates the local object, so the category on the torrent stays stale.
    assert torrent.category == "Downloads"
    assert _call_names(torrent) == ["set_category", "set_location"]
    relocation_attr = cat.notify_attr[0]
    assert relocation_attr["title"] == "Relocating Torrents"
    assert relocation_attr["torrent_category"] == "Movies"
    assert cat.notify_attr[1]["torrent_category"] == "Movies"


# ── dry run ──────────────────────────────────────────────────────────────────


def test_update_cat_dry_run_logs_the_intended_move_without_client_calls(category_module):
    _, recorder = category_module
    cat, qbt, _, torrent = _build(
        settings={"cat_update_relocate": True},
        category_paths={"Movies": "/data/media/Movies"},
        dry_run=True,
    )

    cat.update_cat(torrent, "Movies", False)

    assert torrent.calls == []
    assert qbt.relocate_torrent_calls == []
    # The plan was evaluated: rule 5 is reached only when rules 1-4 let the move through.
    assert qbt.has_shared_files_calls == [(torrent.hash, torrent.save_path)]
    assert f"Would relocate {torrent.name} to {TARGET}." in recorder.messages
    assert [attr["title"] for attr in cat.notify_attr] == ["Updating Categories"]


def test_update_cat_dry_run_reports_a_refusal_without_client_calls(category_module):
    _, recorder = category_module
    cat, qbt, _, torrent = _build(
        settings={"cat_update_relocate": True},
        category_paths={"Movies": "/data/media/Movies"},
        has_shared_files=True,
        dry_run=True,
    )

    cat.update_cat(torrent, "Movies", False)

    assert torrent.calls == []
    assert qbt.relocate_torrent_calls == []
    assert recorder.messages == [f"Refused to relocate {torrent.name}: cross-seed."]
    assert [attr["title"] for attr in cat.notify_attr] == ["Relocation Refused"]


# ── disabled: unchanged pre-feature behaviour ────────────────────────────────


@pytest.mark.parametrize(
    ("cat_change", "title", "expected_messages"),
    [
        (
            False,
            "Updating Categories",
            [
                "   Torrent Name: Example.Torrent",
                "   New Category: Movies",
                f"        Tracker: {TRACKER}",
            ],
        ),
        (
            True,
            "Moving Categories",
            [
                "   Torrent Name: Example.Torrent",
                "   Old Category: Downloads",
                "   New Category: Movies",
                f"        Tracker: {TRACKER}",
            ],
        ),
    ],
)
def test_update_cat_without_relocation_is_the_pre_feature_path(
    category_module, monkeypatch, cat_change, title, expected_messages
):
    _, recorder = category_module
    cat, qbt, _, torrent = _build()

    def never_called(*args, **kwargs):
        raise AssertionError("relocation_plan must not be evaluated when relocation is disabled")

    monkeypatch.setattr(type(cat), "relocation_plan", never_called)

    cat.update_cat(torrent, "Movies", cat_change)

    assert torrent.calls == [("set_category", {"category": "Movies"})]
    assert qbt.relocate_torrent_calls == []
    assert qbt.has_shared_files_calls == []
    assert cat.stats == 1
    assert cat.torrents_updated == [torrent.name]
    assert recorder.messages == expected_messages
    assert cat.notify_attr == [
        {
            "function": "cat_update",
            "title": title,
            "body": "\n".join(expected_messages),
            "torrents": [torrent.name],
            "torrent_category": "Movies",
            "torrent_tag": "",
            "torrent_tracker": TRACKER,
            "notifiarr_indexer": None,
        }
    ]
