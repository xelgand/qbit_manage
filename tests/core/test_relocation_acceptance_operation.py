"""Acceptance tests for the operational behavior of the relocation feature (TST010).

Covers, over the existing fakes and the real ``Category`` entry points:

- AC-3  the feature is off by default: no location change and the pre-feature log lines.
- AC-8  a dry run reports the intended moves and issues no location change, on both entry
        points (the category change and the alignment pass).
- AC-9  one failed relocation is logged and notified without stopping the run.
- AC-10 the two keys are validated at configuration load and documented on every surface.
- AC-11 the run reports what it moved, refused and skipped: one attribute per relocation and
        per refusal, one per-run skip summary sent through ``config.send_notifications``.

The module-level logger of ``modules.core.category`` is patched through ``monkeypatch`` inside a
per-test fixture only, so a combined run with the other Category test modules never leaks a
recorder into them. ``Category`` is imported inside the tests, never at module scope, so no
logger binds during collection.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from modules.config import Config
from modules.util import Failed
from modules.util import YAML
from modules.util import check
from tests.factories import FakeConfig
from tests.factories import FakeQbtManager
from tests.factories import FakeTorrent

REPO_ROOT = Path(__file__).resolve().parents[2]

# Literal outcome contract. Importing these from modules.core.category at module scope would bind
# the module logger during collection, before the per-test fixture runs.
RELOCATION_ACTION_RELOCATE = "relocate"
RELOCATION_ACTION_SKIP = "skip"
RELOCATION_ACTION_REFUSE = "refuse"
RELOCATION_ACTION_TITLES = {
    "Relocating Torrents",
    "Relocation Refused",
    "Relocation Failed",
}
RELOCATION_SKIP_SUMMARY_TITLE = "Relocation Skipped"

CATEGORY = "Movies"
CONFIGURED_PATH = "/data/media/Movies"
OTHER_PATH = "/data/downloads/Example.Torrent"

# Every message the feature can produce; a disabled run must contain none of them.
RELOCATION_MARKERS = (
    "Relocated ",
    "Failed to relocate ",
    "Would relocate ",
    "Skipping relocation for ",
    "Refused to relocate ",
    "Relocation summary:",
    "Relocation skipped for ",
)


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

    def info(self, *args, **kwargs):
        return None

    def warning(self, *args, **kwargs):
        return None

    def error(self, *args, **kwargs):
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


def _run_category(qbt):
    """Run the real ``Category`` entry point, eager work included."""
    from modules.core.category import Category

    return Category(qbt)


def _notify_attr(cfg):
    """Return the notification attributes handed to the webhooks factory in the run."""
    assert len(cfg.webhooks_factory.notify_calls) == 1
    _, notify_attr, group_by = cfg.webhooks_factory.notify_calls[0]
    assert group_by == "category"
    return notify_attr


def _location_calls(torrent):
    return [call for call in torrent.calls if call[0] == "set_location"]


def _relocation_lines(recorder):
    return [message for message in recorder.messages if any(marker in message for marker in RELOCATION_MARKERS)]


# ── AC-3: without the keys nothing is relocated and the run behaves as before ─


# The pre-feature log lines for this input: with cat_update_all disabled the pass only considers
# uncategorized torrents, so a categorized one is untouched and the run ends with the same closing
# line it printed before the feature existed.
PRE_FEATURE_MESSAGES = [
    "No new torrents to categorize.",
]


def _disabled_settings(variant):
    cfg = FakeConfig()
    if variant == "explicit_false":
        cfg.settings["cat_update_relocate"] = False
        cfg.settings["cat_change_relocate"] = False
    return cfg


@pytest.mark.parametrize("variant", ["default_false", "explicit_false"])
def test_disabled_keys_request_no_location_change_and_log_the_pre_feature_lines(category_module, variant):
    """AC-3: keys absent (default) or disabled -> no move, unchanged log lines."""
    _, recorder = category_module
    torrent = _torrent(name="Example.Torrent", category=CATEGORY, save_path=OTHER_PATH)
    cfg = _disabled_settings(variant)
    qbt = FakeQbtManager(torrents=[torrent], config=cfg, category_paths={CATEGORY: CONFIGURED_PATH})

    _run_category(qbt)

    assert _location_calls(torrent) == []
    assert qbt.relocate_torrent_calls == []
    assert _relocation_lines(recorder) == []
    assert recorder.messages == PRE_FEATURE_MESSAGES
    assert cfg.notifications_sent == []


def test_disabled_run_output_is_identical_whether_keys_are_default_or_explicit(category_module):
    """AC-3: the run is independent of whether the keys are defaulted or written as false."""
    _, recorder = category_module
    torrent = _torrent(name="Example.Torrent", category=CATEGORY, save_path=OTHER_PATH)

    cfg_default = _disabled_settings("default_false")
    qbt_default = FakeQbtManager(torrents=[torrent], config=cfg_default, category_paths={})
    _run_category(qbt_default)
    default_messages = list(recorder.messages)

    recorder.messages.clear()
    torrent2 = _torrent(name="Example.Torrent", category=CATEGORY, save_path=OTHER_PATH)
    cfg_explicit = _disabled_settings("explicit_false")
    qbt_explicit = FakeQbtManager(torrents=[torrent2], config=cfg_explicit, category_paths={})
    _run_category(qbt_explicit)

    assert recorder.messages == default_messages
    assert recorder.messages == PRE_FEATURE_MESSAGES


# ── AC-8: a dry run reports the intended moves and refuses to make them ───────


def test_dry_run_category_change_logs_the_move_without_a_location_change(category_module):
    """AC-8: the category-change entry point reports the intended move, moves nothing."""
    _, recorder = category_module
    torrent = _torrent(name="Changing.Torrent", category="OldCat", save_path="/data/downloads/Changing.Torrent")
    cfg = FakeConfig()
    cfg.settings["cat_change_relocate"] = True
    cfg.dry_run = True
    cfg.cat_change = {"OldCat": {"new_cat": "NewCat", "delay_minutes": 0}}
    qbt = FakeQbtManager(
        torrents=[torrent],
        config=cfg,
        category_paths={"OldCat": "/data/media/OldCat", "NewCat": "/data/media/NewCat"},
    )

    _run_category(qbt)

    assert "Would relocate Changing.Torrent to /data/media/NewCat/." in recorder.messages
    assert _location_calls(torrent) == []
    assert qbt.relocate_torrent_calls == []
    # Even the category write is withheld under dry run.
    assert [call for call in torrent.calls if call[0] == "set_category"] == []


def test_dry_run_alignment_pass_logs_the_move_without_a_location_change(category_module):
    """AC-8: the alignment-pass entry point reports the intended move, moves nothing."""
    _, recorder = category_module
    torrent = _torrent()
    cfg = FakeConfig()
    cfg.settings["cat_update_relocate"] = True
    cfg.dry_run = True
    qbt = FakeQbtManager(torrents=[torrent], config=cfg, category_paths={CATEGORY: CONFIGURED_PATH})

    _run_category(qbt)

    assert "Would relocate Example.Torrent to /data/media/Movies/." in recorder.messages
    assert _location_calls(torrent) == []
    assert qbt.relocate_torrent_calls == []


# ── AC-9: one failed relocation does not stop the run ─────────────────────────


def test_one_failed_relocation_is_reported_and_the_run_continues(category_module):
    """AC-9: a failing move is logged and notified; the remaining torrents are processed."""
    _, recorder = category_module
    failing = _torrent(name="Bad.Torrent", hash="1" * 40, save_path="/data/downloads/Bad.Torrent")
    succeeding = _torrent(name="Good.Torrent", hash="2" * 40, save_path="/data/downloads/Good.Torrent")
    cfg = FakeConfig()
    cfg.settings["cat_update_relocate"] = True
    qbt = FakeQbtManager(torrents=[failing, succeeding], config=cfg, category_paths={CATEGORY: CONFIGURED_PATH})

    def relocate_torrent(torrent, target):
        qbt.relocate_torrent_calls.append((torrent, target))
        return torrent.name != "Bad.Torrent"

    qbt.relocate_torrent = relocate_torrent

    _run_category(qbt)

    assert "Failed to relocate Bad.Torrent to /data/media/Movies/." in recorder.messages
    assert "Relocated Good.Torrent to /data/media/Movies/." in recorder.messages
    # The second request went out: the failure did not abort the loop.
    assert [(torrent.name, target) for torrent, target in qbt.relocate_torrent_calls] == [
        ("Bad.Torrent", "/data/media/Movies/"),
        ("Good.Torrent", "/data/media/Movies/"),
    ]

    notify_attr = _notify_attr(cfg)
    by_title = {}
    for attr in notify_attr:
        by_title.setdefault(attr["title"], []).append(attr)
    assert "Relocation Failed" in by_title
    assert "Bad.Torrent" in by_title["Relocation Failed"][0]["body"]
    assert "Relocating Torrents" in by_title
    assert "Good.Torrent" in by_title["Relocating Torrents"][0]["body"]


# ── AC-10: the keys are validated and documented on every surface ─────────────


CONFIG_KEYS = ("cat_update_relocate", "cat_change_relocate")


def _write_config(tmp_path, body):
    path = tmp_path / "config.yml"
    path.write_text(body, encoding="utf-8")
    return path


def _loaded_config(config_path):
    """A Config whose settings parse through the real registration path."""
    cfg = object.__new__(Config)
    cfg.config_path = str(config_path)
    cfg.data = YAML(str(config_path)).data
    cfg.util = check(cfg)
    return cfg


@pytest.mark.parametrize("key", CONFIG_KEYS)
def test_invalid_relocation_key_is_rejected_like_other_boolean_keys(tmp_path, key):
    """AC-10: an invalid relocation value is rejected exactly as an existing boolean key is."""
    invalid = f"settings:\n  {key}: not-a-bool\n"
    cfg = _loaded_config(_write_config(tmp_path, invalid))

    with pytest.raises(Failed, match=f"{key} must be either true or false"):
        cfg.process_config_settings()

    # The same load path rejects an existing boolean key the same way.
    baseline = _loaded_config(_write_config(tmp_path, "settings:\n  force_auto_tmm: not-a-bool\n"))
    with pytest.raises(Failed, match="force_auto_tmm must be either true or false"):
        baseline.process_config_settings()


@pytest.mark.parametrize("key", CONFIG_KEYS)
def test_absent_relocation_key_defaults_to_false_through_config_load(tmp_path, key):
    """AC-10/AC-3: an absent key loads as the disabled default through the real Config path."""
    cfg = _loaded_config(_write_config(tmp_path, "settings: {}\n"))

    cfg.process_config_settings()

    assert cfg.settings[key] is False


@pytest.mark.parametrize("key", CONFIG_KEYS)
def test_relocation_keys_are_documented_on_every_surface(key):
    """AC-10: both keys appear in the sample config, the setup docs and the web UI schema."""
    surfaces = {
        "modules/config.py": (REPO_ROOT / "modules" / "config.py").read_text(encoding="utf-8"),
        "config/config.yml.sample": (REPO_ROOT / "config" / "config.yml.sample").read_text(encoding="utf-8"),
        "docs/Config-Setup.md": (REPO_ROOT / "docs" / "Config-Setup.md").read_text(encoding="utf-8"),
        "web-ui/js/config-schemas/settings.js": (REPO_ROOT / "web-ui" / "js" / "config-schemas" / "settings.js").read_text(
            encoding="utf-8"
        ),
    }
    for surface, text in surfaces.items():
        assert key in text, f"{key} missing from {surface}"


# ── AC-11: the run reports what it moved, refused and skipped ─────────────────


def test_run_reports_relocations_refusals_and_a_single_skip_summary(category_module):
    """AC-11: per-torrent reporting plus one per-run skip summary through send_notifications."""
    _, recorder = category_module
    relocated = _torrent(name="Moved.Torrent", hash="1" * 40, save_path="/data/downloads/Moved.Torrent")
    refused = _torrent(name="Cross.Torrent", hash="2" * 40, save_path="/data/downloads/Cross.Torrent")
    incomplete = _torrent(
        name="Incomplete.Torrent", hash="3" * 40, save_path="/data/downloads/Incomplete.Torrent", state="downloading"
    )
    no_path = _torrent(name="NoPath.Torrent", hash="4" * 40, category="Missing", save_path="/data/downloads/NoPath.Torrent")
    cfg = FakeConfig()
    cfg.settings["cat_update_relocate"] = True
    cfg.settings["cat_filter_completed"] = False
    qbt = FakeQbtManager(
        torrents=[relocated, refused, incomplete, no_path],
        config=cfg,
        category_paths={CATEGORY: CONFIGURED_PATH},
    )

    def has_shared_files(torrent_hash, save_path):
        return torrent_hash == refused.hash

    qbt.has_shared_files = has_shared_files

    _run_category(qbt)

    # Per-torrent log lines identify each affected torrent with its reason.
    assert "Relocated Moved.Torrent to /data/media/Movies/." in recorder.messages
    assert "Refused to relocate Cross.Torrent: cross-seed." in recorder.messages
    assert "Skipping relocation for Incomplete.Torrent: incomplete." in recorder.messages
    assert "Skipping relocation for NoPath.Torrent: no unambiguous configured path." in recorder.messages

    # Relocations and refusals each appear individually in the notification payload.
    notify_attr = _notify_attr(cfg)
    titles = [attr["title"] for attr in notify_attr]
    assert titles.count("Relocating Torrents") == 1
    assert titles.count("Relocation Refused") == 1
    relating = [attr for attr in notify_attr if attr["title"] in RELOCATION_ACTION_TITLES]
    assert len(relating) == 2
    bodies = "\n".join(attr["body"] for attr in relating)
    assert "Moved.Torrent" in bodies
    assert "Cross.Torrent" in bodies
    # Skips are never notified per torrent.
    assert "Incomplete.Torrent" not in bodies
    assert "NoPath.Torrent" not in bodies

    # Exactly one per-run summary carries the counts per reason, sent directly.
    assert len(cfg.notifications_sent) == 1
    summary = cfg.notifications_sent[0]
    assert summary["title"] == RELOCATION_SKIP_SUMMARY_TITLE
    assert summary["torrents"] == ["Incomplete.Torrent", "NoPath.Torrent"]
    assert "Relocation skipped for 2 torrent(s):" in summary["body"]
    assert "incomplete: 1" in summary["body"]
    assert "no unambiguous configured path: 1" in summary["body"]


def test_cat_change_only_run_reports_its_skips_without_the_alignment_pass(category_module):
    """AC-11: enabling only cat_change still sends one skip summary; the alignment pass did not run."""
    _, recorder = category_module
    torrent = _torrent(
        name="Changing.Torrent",
        hash="5" * 40,
        category="OldCat",
        save_path="/data/downloads/Changing.Torrent",
        state="downloading",
    )
    cfg = FakeConfig()
    cfg.settings["cat_change_relocate"] = True
    cfg.settings["cat_update_relocate"] = False
    cfg.settings["cat_filter_completed"] = False
    cfg.cat_change = {"OldCat": {"new_cat": "NewCat", "delay_minutes": 0}}
    qbt = FakeQbtManager(torrents=[torrent], config=cfg, category_paths={"NewCat": "/data/media/NewCat"})

    _run_category(qbt)

    assert "Skipping relocation for Changing.Torrent: incomplete." in recorder.messages
    assert len(cfg.notifications_sent) == 1
    summary = cfg.notifications_sent[0]
    assert summary["title"] == RELOCATION_SKIP_SUMMARY_TITLE
    assert summary["torrents"] == [torrent.name]
    assert "incomplete: 1" in summary["body"]

    # The alignment pass ran no relocation and logged no closing summary line.
    assert qbt.relocate_torrent_calls == []
    assert not any(message.startswith("Relocation summary:") for message in recorder.messages)
    assert not any(message.startswith("Would relocate ") for message in recorder.messages)
