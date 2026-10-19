"""Tests for Category.align_locations and its wiring in Category.__init__.

Only the module-level logger of ``modules.core.category`` is patched, per test, so combining this
file with the other Category tests never leaks a recorder into them.
"""

from __future__ import annotations

import pytest

from tests.factories import FakeConfig
from tests.factories import FakeQbtManager
from tests.factories import FakeTorrent
from tests.factories import make_category

# Literal outcome contract: importing Category at module scope would bind the
# module logger during collection, before the per-test fixture runs.
RELOCATION_SKIP_AUTO_TMM = "Automatic Torrent Management"
RELOCATION_SKIP_NO_CONFIGURED_PATH = "no unambiguous configured path"
RELOCATION_SKIP_INCOMPLETE = "incomplete"
RELOCATION_SKIP_ALREADY_IN_PLACE = "already in place"

CATEGORY = "Movies"
CONFIGURED_PATH = "/data/media/Movies"
TARGET = CONFIGURED_PATH + "/"
OTHER_PATH = "/data/downloads/Example.Torrent"
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
        "category": CATEGORY,
        "save_path": OTHER_PATH,
        "state": "uploading",
    }
    data.update(overrides)
    return FakeTorrent(**data)


def _build(*, torrents=None, settings=None, dry_run=False, category_paths=None, shared_files=False):
    cfg = FakeConfig()
    cfg.settings.update(settings or {})
    cfg.dry_run = dry_run
    qbt = FakeQbtManager(
        torrents=torrents or [],
        config=cfg,
        category_paths=category_paths if category_paths is not None else {CATEGORY: CONFIGURED_PATH},
        has_shared_files=shared_files,
    )
    return make_category(qbt), qbt, cfg


def _wire_client_move(qbt):
    """Mirror Qbt.relocate_torrent: issue the move and update the save path."""

    def relocate_torrent(torrent, target):
        torrent.set_location(location=target)
        torrent.save_path = target
        return qbt.__class__.relocate_torrent(qbt, torrent, target)

    qbt.relocate_torrent = relocate_torrent


def _call_names(torrent):
    return [name for name, _ in torrent.calls]


# ── relocation without a category write ──────────────────────────────────────


def test_align_locations_relocates_without_set_category(category_module):
    _, recorder = category_module
    torrent = _torrent()
    cat, qbt, _ = _build(torrents=[torrent], settings={"cat_update_relocate": True})
    _wire_client_move(qbt)

    cat.align_locations()

    assert _call_names(torrent) == ["set_location"]
    assert torrent.calls[0][1] == {"location": TARGET}
    assert qbt.relocate_torrent_calls == [(torrent, TARGET)]
    assert torrent.category == CATEGORY
    assert cat._relocation_counters()["relocated"] == 1
    assert [attr["title"] for attr in cat.notify_attr] == ["Relocating Torrents"]
    assert cat.torrents_updated == [torrent.name]
    assert any(
        message.startswith("Relocation summary: 1 relocated, 0 failed, 0 refused, 0 skipped")
        for message in recorder.messages
    )


def test_align_locations_honours_the_run_hashes(category_module):
    selected = _torrent(name="Selected", hash="a" * 40)
    other = _torrent(name="Other", hash="b" * 40)
    cat, qbt, _ = _build(torrents=[selected, other], settings={"cat_update_relocate": True})
    cat.hashes = [selected.hash]

    cat.align_locations()

    assert qbt.relocate_torrent_calls == [(selected, TARGET)]
    assert other.calls == []


def test_align_locations_ignores_uncategorized_torrents(category_module, monkeypatch):
    _, recorder = category_module
    torrent = _torrent(category="Uncategorized")
    cat, qbt, _ = _build(torrents=[torrent], settings={"cat_update_relocate": True})

    def never_evaluated(*args, **kwargs):
        raise AssertionError("an uncategorized torrent is not a relocation candidate")

    monkeypatch.setattr(type(cat), "relocation_plan", never_evaluated)

    cat.align_locations()

    assert torrent.calls == []
    assert qbt.relocate_torrent_calls == []
    assert cat._relocation_counters()["skipped"] == {}
    assert recorder.messages == ["Relocation summary: 0 relocated, 0 failed, 0 refused, 0 skipped."]


# ── every skip reason is counted and calls nothing ───────────────────────────


@pytest.mark.parametrize(
    ("reason", "torrent_kwargs", "category_paths", "settings"),
    [
        (RELOCATION_SKIP_NO_CONFIGURED_PATH, {}, {}, {}),
        (RELOCATION_SKIP_NO_CONFIGURED_PATH, {}, {"Movies": "/data/media/*"}, {}),
        (RELOCATION_SKIP_NO_CONFIGURED_PATH, {}, {"Movies": ["/data/a", "/data/b"]}, {}),
        (
            RELOCATION_SKIP_INCOMPLETE,
            {"state": "downloading", "progress": 0.5},
            {CATEGORY: CONFIGURED_PATH},
            {"cat_filter_completed": False},
        ),
        (RELOCATION_SKIP_AUTO_TMM, {"auto_tmm": True}, {CATEGORY: CONFIGURED_PATH}, {}),
        (RELOCATION_SKIP_ALREADY_IN_PLACE, {"save_path": CONFIGURED_PATH}, {CATEGORY: CONFIGURED_PATH}, {}),
    ],
)
def test_align_locations_counts_each_skip_reason(
    category_module, reason, torrent_kwargs, category_paths, settings
):
    _, recorder = category_module
    torrent = _torrent(**torrent_kwargs)
    cat, qbt, _ = _build(
        torrents=[torrent],
        settings={"cat_update_relocate": True, **settings},
        category_paths=category_paths,
    )

    cat.align_locations()

    assert torrent.calls == []
    assert qbt.relocate_torrent_calls == []
    counters = cat._relocation_counters()
    assert counters["skipped"] == {reason: 1}
    assert counters["skipped_names"] == [torrent.name]
    assert f"Skipping relocation for {torrent.name}: {reason}." in recorder.messages
    assert any(message.endswith(f"1 skipped ({reason}: 1).") for message in recorder.messages)


def test_align_locations_counts_a_cross_seed_refusal(category_module):
    _, recorder = category_module
    torrent = _torrent()
    cat, qbt, _ = _build(
        torrents=[torrent],
        settings={"cat_update_relocate": True},
        shared_files=True,
    )

    cat.align_locations()

    assert torrent.calls == []
    assert qbt.relocate_torrent_calls == []
    assert cat._relocation_counters()["refused"] == 1
    assert f"Refused to relocate {torrent.name}: cross-seed." in recorder.messages
    assert [attr["title"] for attr in cat.notify_attr] == ["Relocation Refused"]


# ── dry run ──────────────────────────────────────────────────────────────────


def test_align_locations_dry_run_logs_the_move_without_a_client_call(category_module):
    _, recorder = category_module
    torrent = _torrent()
    cat, qbt, _ = _build(
        torrents=[torrent],
        settings={"cat_update_relocate": True},
        dry_run=True,
    )

    cat.align_locations()

    assert torrent.calls == []
    assert qbt.relocate_torrent_calls == []
    # Rule 5 was reached, so the plan was fully evaluated.
    assert qbt.has_shared_files_calls == [(torrent.hash, torrent.save_path)]
    assert f"Would relocate {torrent.name} to {TARGET}." in recorder.messages
    assert cat._relocation_counters()["relocated"] == 0


def test_align_locations_dry_run_reports_a_refusal_without_a_client_call(category_module):
    _, recorder = category_module
    torrent = _torrent()
    cat, qbt, _ = _build(
        torrents=[torrent],
        settings={"cat_update_relocate": True},
        shared_files=True,
        dry_run=True,
    )

    cat.align_locations()

    assert torrent.calls == []
    assert qbt.relocate_torrent_calls == []
    assert f"Refused to relocate {torrent.name}: cross-seed." in recorder.messages


# ── call-site order through the real __init__ ────────────────────────────────


def test_cat_change_candidate_is_relocated_once_to_the_new_category_path(category_module):
    _, recorder = category_module
    torrent = _torrent(
        name="Changing.Torrent",
        category="OldCat",
        save_path="/data/downloads/Changing.Torrent",
    )
    _, qbt, cfg = _build(
        torrents=[torrent],
        settings={"cat_change_relocate": True, "cat_update_relocate": True},
        category_paths={"OldCat": "/data/media/OldCat", "NewCat": "/data/media/NewCat"},
    )
    cfg.cat_change = {"OldCat": {"new_cat": "NewCat", "delay_minutes": 0}}
    _wire_client_move(qbt)

    from modules.core.category import Category

    Category(qbt)

    locations = [kwargs for name, kwargs in torrent.calls if name == "set_location"]
    assert locations == [{"location": "/data/media/NewCat/"}]
    assert _call_names(torrent).count("set_category") == 1
    assert qbt.relocate_torrent_calls == [(torrent, "/data/media/NewCat/")]
    assert torrent.category == "NewCat"
    assert any("Relocated Changing.Torrent to /data/media/NewCat/." in message for message in recorder.messages)
    # One relocation in the category-change path; the pass then found it already in place.
    assert "Relocation summary: 1 relocated, 0 failed, 0 refused, 1 skipped (already in place: 1)." in recorder.messages


def test_cat_change_only_run_sends_one_skip_summary(category_module):
    _, recorder = category_module
    torrent = _torrent(
        name="Incomplete.Torrent",
        category="OldCat",
        save_path="/data/downloads/Incomplete.Torrent",
        state="downloading",
        progress=0.5,
    )
    cat, qbt, cfg = _build(
        torrents=[torrent],
        settings={"cat_change_relocate": True, "cat_filter_completed": False},
        category_paths={"NewCat": "/data/media/NewCat"},
    )
    cfg.cat_change = {"OldCat": {"new_cat": "NewCat", "delay_minutes": 0}}

    from modules.core.category import Category

    Category(qbt)

    assert len(cfg.notifications_sent) == 1
    summary = cfg.notifications_sent[0]
    assert summary["title"] == "Relocation Skipped"
    assert f"{RELOCATION_SKIP_INCOMPLETE}: 1" in summary["body"]
    assert summary["torrents"] == [torrent.name]
    assert qbt.relocate_torrent_calls == []
    # The alignment pass never ran, so no closing summary line was logged.
    assert not any(message.startswith("Relocation summary:") for message in recorder.messages)


def test_cat_change_only_run_sends_no_summary_without_skips(category_module):
    _, _ = category_module
    torrent = _torrent(category="OldCat")
    cfg = FakeConfig()
    cfg.settings["cat_change_relocate"] = True
    cfg.cat_change = {"OtherCat": {"new_cat": "NewCat", "delay_minutes": 0}}
    qbt = FakeQbtManager(torrents=[torrent], config=cfg, category_paths={})

    from modules.core.category import Category

    Category(qbt)

    assert cfg.notifications_sent == []


def test_disabled_alignment_pass_is_not_invoked_and_fetches_nothing_extra(category_module, monkeypatch):
    _, _ = category_module
    torrent = _torrent()
    cfg = FakeConfig()
    qbt = FakeQbtManager(torrents=[torrent], config=cfg)
    fetches = []
    original = qbt.get_torrents

    def recording_get_torrents(params):
        fetches.append(dict(params))
        return original(params)

    qbt.get_torrents = recording_get_torrents

    from modules.core.category import Category

    def never_called(self):
        raise AssertionError("align_locations must not run when cat_update_relocate is disabled")

    monkeypatch.setattr(Category, "align_locations", never_called)

    Category(qbt)

    # Only category() fetched a list; the disabled pass adds neither a call nor a fetch.
    assert len(fetches) == 1
    assert fetches[0]["category"] == ""
    assert cfg.notifications_sent == []


def test_pass_results_reach_the_notification_payload(category_module):
    _, _ = category_module
    torrent = _torrent()
    cfg = FakeConfig()
    cfg.settings["cat_update_relocate"] = True
    qbt = FakeQbtManager(
        torrents=[torrent],
        config=cfg,
        category_paths={CATEGORY: CONFIGURED_PATH},
    )

    from modules.core.category import Category

    Category(qbt)

    assert len(cfg.webhooks_factory.notify_calls) == 1
    torrents_updated, notify_attr, group_by = cfg.webhooks_factory.notify_calls[0]
    assert group_by == "category"
    assert torrents_updated == [torrent.name]
    assert [attr["title"] for attr in notify_attr] == ["Relocating Torrents"]
    assert notify_attr[0]["torrents"] == [torrent.name]
