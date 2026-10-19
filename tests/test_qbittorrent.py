"""Unit tests for modules/qbittorrent.py — Qbt class.

Coverage:
- get_tracker_urls() — URL extraction, protocol filtering, sentinels ([DHT], [PeX], [LSD])
- is_torrent_private() — boolean checks using private attr and tracker messages
- get_tags() — config-based tracker URL mapping
- get_torrent_info() — torrentinfo cache population, state mapping
- Cross-seed detection (is_cross_seed, has_cross_seed, torrentfiles tracking)
- Relocation primitives (category_config_path, directory_peers, torrent_file_paths,
  has_shared_files, relocate_torrent)
"""

from __future__ import annotations

from functools import cache
from types import SimpleNamespace
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
from qbittorrentapi import NotFound404Error

from modules.qbittorrent import Qbt
from tests.factories import FakeTorrent
from tests.factories import _Tracker


def make_qbt_config():
    return SimpleNamespace(
        commands={
            "skip_qb_version_check": False,
            "share_limits": False,
            "recheck": False,
            "rem_unregistered": False,
            "tag_tracker_error": False,
            "tag_nohardlinks": False,
        },
        settings={"disable_qbt_default_share_limits": False},
        notify=MagicMock(),
    )


def make_qbt_client():
    client = MagicMock()
    client.app.version = "v5.5.0"
    client.app.web_api_version = "2.11.0"
    client.app.preferences.max_ratio_act = 0
    client.app.preferences.max_ratio_enabled = False
    client.app.preferences.max_ratio = 0
    client.app.preferences.max_seeding_time_enabled = False
    client.app.preferences.max_seeding_time = 0
    return client


class TestAuthentication:
    """Test Qbt authentication configuration."""

    @patch("modules.qbittorrent.Version.is_app_version_supported", return_value=True)
    @patch("modules.qbittorrent.Qbt.get_torrents", return_value=[])
    @patch("modules.qbittorrent.Client")
    @patch("modules.qbittorrent.logger.secret", create=True)
    def test_passes_api_key_to_client(self, _mock_secret, mock_client, _mock_get_torrents, _mock_version_supported):
        client = make_qbt_client()
        mock_client.return_value = client

        Qbt(
            make_qbt_config(),
            {"host": "localhost:8080", "username": None, "password": None, "api_key": "qbt_test_key"},
        )

        mock_client.assert_called_once_with(
            host="localhost:8080",
            username=None,
            password=None,
            api_key="qbt_test_key",
            VERIFY_WEBUI_CERTIFICATE=False,
            REQUESTS_ARGS={"timeout": (45, 60)},
        )
        client.auth_log_in.assert_called_once()

    @patch("modules.qbittorrent.Version.is_app_version_supported", return_value=True)
    @patch("modules.qbittorrent.Qbt.get_torrents", return_value=[])
    @patch("modules.qbittorrent.logger.warning")
    @patch("modules.qbittorrent.Client")
    @patch("modules.qbittorrent.logger.secret", create=True)
    def test_warns_when_api_key_and_password_credentials_are_set(
        self, _mock_secret, mock_client, mock_warning, _mock_get_torrents, _mock_version_supported
    ):
        mock_client.return_value = make_qbt_client()

        Qbt(
            make_qbt_config(),
            {"host": "localhost:8080", "username": "admin", "password": "password", "api_key": "qbt_test_key"},
        )

        mock_warning.assert_called_once_with("qBittorrent API key is set; it takes precedence over username and password.")


# ---- get_tracker_urls tests --------------------------------------------------


class TestGetTrackerUrls:
    """Test Qbt.get_tracker_urls() tracker URL extraction."""

    def test_extracts_http_https_udp_ws_urls(self):
        """Filter out DHT/PeX/LSD sentinels; keep http, https, udp, ws."""
        trackers = [
            _Tracker(url="http://tracker1.example/announce"),
            _Tracker(url="https://tracker2.example/announce"),
            _Tracker(url="udp://tracker3.example:6969/announce"),
            _Tracker(url="ws://tracker4.example/announce"),
            _Tracker(url="** [DHT] **"),
            _Tracker(url="** [PeX] **"),
            _Tracker(url="** [LSD] **"),
        ]
        qbt = MagicMock(spec=Qbt)
        urls = Qbt.get_tracker_urls(qbt, trackers)
        assert len(urls) == 4
        assert "http://tracker1.example/announce" in urls
        assert "** [DHT] **" not in urls
        assert "** [PeX] **" not in urls

    def test_returns_tuple(self):
        """get_tracker_urls returns a tuple."""
        trackers = [_Tracker(url="http://tracker1.example/announce")]
        qbt = MagicMock(spec=Qbt)
        urls = Qbt.get_tracker_urls(qbt, trackers)
        assert isinstance(urls, tuple)

    def test_empty_trackers_returns_empty_tuple(self):
        """Empty tracker list returns empty tuple."""
        qbt = MagicMock(spec=Qbt)
        urls = Qbt.get_tracker_urls(qbt, [])
        assert urls == ()

    def test_filters_non_protocol_urls(self):
        """Filter out URLs without http/https/udp/ws prefix."""
        trackers = [
            _Tracker(url="http://valid.example/announce"),
            _Tracker(url="/announce"),
            _Tracker(url="file:///announce"),
        ]
        qbt = MagicMock(spec=Qbt)
        urls = Qbt.get_tracker_urls(qbt, trackers)
        assert len(urls) == 1
        assert "http://valid.example/announce" in urls


# ---- is_torrent_private tests ------------------------------------------------


class TestIsTorrentPrivate:
    """Test Qbt.is_torrent_private() boolean detection."""

    def test_private_attr_true_returns_true(self):
        """If torrent.private == True, return True immediately."""
        torrent = FakeTorrent(private=True)
        qbt = MagicMock(spec=Qbt)
        result = Qbt.is_torrent_private(qbt, torrent)
        assert result is True

    def test_private_attr_false_returns_false(self):
        """If torrent.private == False, return False immediately."""
        torrent = FakeTorrent(private=False)
        qbt = MagicMock(spec=Qbt)
        result = Qbt.is_torrent_private(qbt, torrent)
        assert result is False

    def test_no_private_attr_checks_trackers(self):
        """If torrent has no private attr, check tracker messages/URLs."""
        torrent = FakeTorrent(name="test", hash="abc123")
        # Remove the private attribute to simulate old API response
        delattr(torrent, "private")

        qbt = MagicMock(spec=Qbt)
        qbt.client = MagicMock()
        qbt.client.torrents_trackers = MagicMock(
            return_value=[
                {"url": "http://tracker1.example/announce", "msg": ""},
                {"url": "http://private.tracker.example/announce", "msg": "private"},
            ]
        )

        result = Qbt.is_torrent_private(qbt, torrent)
        assert result is True

    def test_tracker_url_contains_private(self):
        """Detect private=True if tracker URL contains 'private'."""
        torrent = FakeTorrent(name="test", hash="abc123")
        delattr(torrent, "private")

        qbt = MagicMock(spec=Qbt)
        qbt.client = MagicMock()
        qbt.client.torrents_trackers = MagicMock(return_value=[{"url": "http://private.example/announce", "msg": ""}])

        result = Qbt.is_torrent_private(qbt, torrent)
        assert result is True

    def test_accepts_hash_string_as_torrent_param(self):
        """is_torrent_private accepts torrent hash string (not just object)."""
        qbt = MagicMock(spec=Qbt)
        qbt.client = MagicMock()
        qbt.client.torrents_trackers = MagicMock(return_value=[{"url": "http://tracker1.example/announce", "msg": ""}])

        result = Qbt.is_torrent_private(qbt, "abc123xyz")
        assert result is False
        qbt.client.torrents_trackers.assert_called_once_with("abc123xyz")


# ---- get_tags tests ----------------------------------------------------------


class TestGetTags:
    """Test Qbt.get_tags() tracker URL → tag mapping."""

    @patch("modules.qbittorrent.logger")
    def test_returns_dict_shape(self, mock_logger):
        """get_tags returns dict with tag/cat/notifiarr/url keys."""
        qbt = MagicMock(spec=Qbt)
        qbt.config = MagicMock()
        qbt.config.data = {"tracker": {}}
        qbt.config.util = MagicMock()
        qbt.config.util.check_for_attribute = MagicMock(return_value=None)

        result = Qbt.get_tags(qbt, ["http://tracker1.example/announce"])
        assert isinstance(result, dict)
        assert "tag" in result
        assert "cat" in result
        assert "notifiarr" in result
        assert "url" in result

    @patch("modules.qbittorrent.logger")
    def test_no_urls_returns_default_other_tag(self, mock_logger):
        """Empty URL list defaults to 'other' tag."""
        qbt = MagicMock(spec=Qbt)
        qbt.config = MagicMock()
        qbt.config.data = {"tracker": {}}
        qbt.config.util = MagicMock()
        qbt.config.util.check_for_attribute = MagicMock(return_value=["other"])

        result = Qbt.get_tags(qbt, [])
        assert result["url"] == "No http URL found"
        assert result["tag"] == ["other"]

    def test_matches_tracker_config_url(self):
        """If tracker URL matches config key, return that tag/cat."""
        qbt = MagicMock(spec=Qbt)
        qbt.config = MagicMock()
        qbt.config.data = {"tracker": {"tracker1.example": {"tag": ["t1tag"], "cat": "T1Cat"}}}
        qbt.config.util = MagicMock()
        # Discriminate by the 2nd positional arg (the attribute key name).
        qbt.config.util.check_for_attribute = MagicMock(
            side_effect=lambda *args, **kwargs: ["t1tag"] if args[1] == "tag" else "T1Cat"
        )

        result = Qbt.get_tags(qbt, ["http://tracker1.example/announce"])
        # URL matched config key → specific tag/cat returned
        assert result["tag"] == ["t1tag"]
        assert result["cat"] == "T1Cat"

    def test_converts_string_tag_to_list(self):
        """If tag is a string, convert to list."""
        qbt = MagicMock(spec=Qbt)
        qbt.config = MagicMock()
        qbt.config.data = {"tracker": {"tracker1.example": {"tag": "singletag"}}}
        qbt.config.util = MagicMock()
        qbt.config.util.check_for_attribute = MagicMock(return_value="singletag")

        result = Qbt.get_tags(qbt, ["http://tracker1.example/announce"])
        # String tag input must be converted to a one-element list
        assert result["tag"] == ["singletag"]


# ---- get_torrent_info tests --------------------------------------------------


class TestGetTorrentInfo:
    """Test Qbt.get_torrent_info() torrentinfo cache population."""

    @patch("modules.qbittorrent.logger")
    def test_populates_torrentinfo_dict(self, mock_logger):
        """get_torrent_info populates self.torrentinfo with torrent name keys."""
        torrent = FakeTorrent(
            name="TestTorrent",
            hash="hash123",
            category="TV",
            save_path="/data/torrents/TV",
        )

        qbt = MagicMock(spec=Qbt)
        qbt.config = MagicMock()
        qbt.config.settings = {
            "force_auto_tmm": False,
            "force_auto_tmm_ignore_tags": [],
        }
        qbt.config.dry_run = False
        qbt.config.notify = MagicMock()
        qbt.torrent_list = [torrent]
        qbt.torrentfiles = {}
        qbt.add_torrent_files = MagicMock()

        # Call the actual method
        Qbt.get_torrent_info(qbt)

        assert qbt.torrentinfo is not None
        assert isinstance(qbt.torrentinfo, dict)

    @patch("modules.qbittorrent.logger")
    def test_populates_torrentvalid_list(self, mock_logger):
        """Torrents with working trackers go to torrentvalid list."""
        torrent = FakeTorrent(
            name="ValidTorrent",
            hash="hash456",
            trackers=[_Tracker(url="http://tracker1.example/announce", status=2)],
        )

        qbt = MagicMock(spec=Qbt)
        qbt.config = MagicMock()
        qbt.config.settings = {
            "force_auto_tmm": False,
            "force_auto_tmm_ignore_tags": [],
        }
        qbt.config.dry_run = False
        qbt.config.notify = MagicMock()
        qbt.torrent_list = [torrent]
        qbt.torrentfiles = {}
        qbt.add_torrent_files = MagicMock()

        Qbt.get_torrent_info(qbt)

        # Check that torrentvalid list was populated
        assert hasattr(qbt, "torrentvalid")

    @patch("modules.qbittorrent.logger")
    def test_none_tracker_msg_does_not_crash(self, mock_logger):
        """A tracker with msg=None must not crash torrentinfo population (#1358)."""
        torrent = FakeTorrent(
            name="NoneMsgTorrent",
            hash="hashnone",
            trackers=[_Tracker(url="http://tracker1.example/announce", status=4, msg=None)],
        )

        qbt = MagicMock(spec=Qbt)
        qbt.config = MagicMock()
        qbt.config.settings = {
            "force_auto_tmm": False,
            "force_auto_tmm_ignore_tags": [],
        }
        qbt.config.dry_run = False
        qbt.config.notify = MagicMock()
        qbt.torrent_list = [torrent]
        qbt.torrentfiles = {}
        qbt.add_torrent_files = MagicMock()

        Qbt.get_torrent_info(qbt)

        assert isinstance(qbt.torrentinfo, dict)

    @patch("modules.qbittorrent.logger")
    def test_populates_torrentissue_list(self, mock_logger):
        """Torrents with broken trackers go to torrentissue list."""
        qbt = MagicMock(spec=Qbt)
        qbt.config = MagicMock()
        qbt.config.settings = {
            "force_auto_tmm": False,
            "force_auto_tmm_ignore_tags": [],
        }
        qbt.config.dry_run = False
        qbt.config.notify = MagicMock()
        qbt.torrent_list = []
        qbt.torrentfiles = {}
        qbt.add_torrent_files = MagicMock()

        Qbt.get_torrent_info(qbt)

        # Check that torrentissue list was created
        assert hasattr(qbt, "torrentissue")
        assert isinstance(qbt.torrentissue, list)


# ---- Cross-seed detection tests ----------------------------------------------


class TestCrossSeedDetection:
    """Test is_cross_seed, has_cross_seed, add_torrent_files tracking."""

    @patch("modules.qbittorrent.logger")
    def test_is_cross_seed_returns_false_when_downloaded_nonzero(self, mock_logger):
        """is_cross_seed returns False if torrent.downloaded != 0."""
        torrent = FakeTorrent(downloaded=1024)
        qbt = MagicMock(spec=Qbt)
        qbt.torrentfiles = {}

        result = Qbt.is_cross_seed(qbt, torrent)
        assert result is False

    def test_add_torrent_files_tracks_original_and_crossseeds(self):
        """add_torrent_files populates cross_seed map correctly."""
        qbt = MagicMock(spec=Qbt)
        qbt.torrentfiles = {}

        class FakeFile:
            def __init__(self, name):
                self.name = name

        files = [FakeFile("file1.txt")]
        Qbt.add_torrent_files(qbt, "hash1", files, "/data/torrents/")

        assert "/data/torrents/file1.txt" in qbt.torrentfiles
        assert qbt.torrentfiles["/data/torrents/file1.txt"]["original"] == "hash1"
        assert qbt.torrentfiles["/data/torrents/file1.txt"]["cross_seed"] == []

    def test_add_torrent_files_appends_crossseed_hash(self):
        """Duplicate files append hash to cross_seed list."""
        qbt = MagicMock(spec=Qbt)
        qbt.torrentfiles = {}

        class FakeFile:
            def __init__(self, name):
                self.name = name

        files1 = [FakeFile("file1.txt")]
        files2 = [FakeFile("file1.txt")]

        Qbt.add_torrent_files(qbt, "hash1", files1, "/data/torrents/")
        Qbt.add_torrent_files(qbt, "hash2", files2, "/data/torrents/")

        assert qbt.torrentfiles["/data/torrents/file1.txt"]["original"] == "hash1"
        assert "hash2" in qbt.torrentfiles["/data/torrents/file1.txt"]["cross_seed"]

    @patch("modules.qbittorrent.logger")
    def test_has_cross_seed_returns_true_if_files_have_crossseeds(self, mock_logger):
        """has_cross_seed returns True if any file has cross_seed entries."""

        class FakeFile:
            def __init__(self, name):
                self.name = name

        torrent = FakeTorrent(name="Test", hash="hash1", save_path="/data/", files=[FakeFile("file1.txt")])
        qbt = MagicMock(spec=Qbt)
        qbt.torrentfiles = {"/data/file1.txt": {"original": "hash1", "cross_seed": ["hash2"]}}

        result = Qbt.has_cross_seed(qbt, torrent)
        assert result is True

    @patch("modules.qbittorrent.logger")
    def test_remove_torrent_files_updates_original_on_delete(self, mock_logger):
        """remove_torrent_files promotes cross_seed[0] to original on delete."""
        torrent = FakeTorrent(hash="hash1")

        class FakeFile:
            def __init__(self, name):
                self.name = name

        torrent.files = [FakeFile("file1.txt")]
        torrent.save_path = "/data/"

        qbt = MagicMock(spec=Qbt)
        qbt.torrentfiles = {"/data/file1.txt": {"original": "hash1", "cross_seed": ["hash2", "hash3"]}}

        Qbt.remove_torrent_files(qbt, torrent)

        assert qbt.torrentfiles["/data/file1.txt"]["original"] == "hash2"
        assert qbt.torrentfiles["/data/file1.txt"]["cross_seed"] == ["hash3"]


# ---- Relocation primitives tests ---------------------------------------------


class FakeFile:
    """Minimal stand-in for a qbittorrent-api torrent file entry."""

    def __init__(self, name):
        self.name = name


class BrokenFiles:
    """File list whose iteration fails, simulating an unreadable file list."""

    def __iter__(self):
        raise RuntimeError("file list unavailable")


def make_relocation_qbt(torrents, cat=None):
    """Build a Qbt stand-in with the relocation members wired as in __init__."""
    qbt = MagicMock(spec=Qbt)
    qbt.config = SimpleNamespace(data={"cat": cat if cat is not None else {}})
    qbt.torrentfiles = {}
    qbt.get_all_torrents = MagicMock(return_value=torrents)
    qbt._directory_peer_hashes = cache(Qbt._directory_peer_hashes.__get__(qbt))
    qbt.directory_peers = Qbt.directory_peers.__get__(qbt)
    qbt.torrent_file_paths = cache(Qbt.torrent_file_paths.__get__(qbt))
    qbt.has_shared_files = Qbt.has_shared_files.__get__(qbt)
    return qbt


class TestCategoryConfigPath:
    """Test Qbt.category_config_path() literal path resolution."""

    def test_returns_trailing_separator_form(self):
        qbt = make_relocation_qbt([], cat={"TV": "/data/tv"})
        assert Qbt.category_config_path(qbt, "TV") == "/data/tv/"

    def test_absent_category_returns_none(self):
        qbt = make_relocation_qbt([], cat={"TV": "/data/tv"})
        assert Qbt.category_config_path(qbt, "Movies") is None

    def test_absent_cat_section_returns_none(self):
        qbt = make_relocation_qbt([])
        qbt.config.data = {}
        assert Qbt.category_config_path(qbt, "TV") is None

    def test_list_value_returns_none(self):
        qbt = make_relocation_qbt([], cat={"Uncategorized": ["/data/a", "/data/b"]})
        assert Qbt.category_config_path(qbt, "Uncategorized") is None

    @pytest.mark.parametrize("save_path", ["/data/*", "/data/tv?", "/data/[abc]"])
    def test_glob_metacharacter_returns_none(self, save_path):
        qbt = make_relocation_qbt([], cat={"TV": save_path})
        assert Qbt.category_config_path(qbt, "TV") is None


class TestDirectoryPeers:
    """Test Qbt.directory_peers() colliding save-path selection."""

    def _torrents(self):
        return [
            FakeTorrent(hash="candidate", save_path="/data/tv"),
            FakeTorrent(hash="same", save_path="/data/tv"),
            FakeTorrent(hash="descendant", save_path="/data/tv/Show"),
            FakeTorrent(hash="ancestor", save_path="/data"),
            FakeTorrent(hash="unrelated", save_path="/data/other"),
            FakeTorrent(hash="sibling", save_path="/data/tv2"),
        ]

    def test_selects_same_ancestor_and_descendant_peers(self):
        qbt = make_relocation_qbt(self._torrents())
        peers = Qbt.directory_peers(qbt, "/data/tv", "candidate")
        assert set(peers) == {"same", "descendant", "ancestor"}

    def test_excludes_candidate_and_unrelated_paths(self):
        qbt = make_relocation_qbt(self._torrents())
        peers = Qbt.directory_peers(qbt, "/data/tv", "candidate")
        assert "candidate" not in peers
        assert "unrelated" not in peers
        assert "sibling" not in peers

    def test_root_save_path_is_a_peer_of_a_nested_candidate(self):
        torrents = [
            FakeTorrent(hash="candidate", save_path="/data/tv"),
            FakeTorrent(hash="root", save_path="/"),
            FakeTorrent(hash="unrelated", save_path="/other"),
        ]
        qbt = make_relocation_qbt(torrents)

        peers = Qbt.directory_peers(qbt, "/data/tv", "candidate")

        assert set(peers) == {"root"}

    def test_nested_torrents_are_peers_of_a_root_candidate(self):
        torrents = [
            FakeTorrent(hash="candidate", save_path="/"),
            FakeTorrent(hash="nested", save_path="/data/tv"),
            FakeTorrent(hash="other", save_path="/data/other"),
        ]
        qbt = make_relocation_qbt(torrents)

        peers = Qbt.directory_peers(qbt, "/", "candidate")

        assert set(peers) == {"nested", "other"}

    def test_fetches_the_client_list_once(self):
        qbt = make_relocation_qbt(self._torrents())
        Qbt.directory_peers(qbt, "/data/tv", "candidate")
        Qbt.directory_peers(qbt, "/data/tv", "same")
        assert qbt.get_all_torrents.call_count == 1

    def test_read_error_returns_none(self):
        qbt = make_relocation_qbt([])
        qbt.get_all_torrents.side_effect = RuntimeError("client unavailable")
        assert Qbt.directory_peers(qbt, "/data/tv", "candidate") is None

    def test_empty_client_list_returns_empty_list(self):
        qbt = make_relocation_qbt([])
        peers = Qbt.directory_peers(qbt, "/data/tv", "candidate")
        assert peers == []
        assert peers is not None


class TestTorrentFilePaths:
    """Test Qbt.torrent_file_paths() joined-path construction and caching."""

    def test_builds_the_same_paths_as_add_torrent_files(self):
        files = [FakeFile("file1.mkv"), FakeFile("subs/file2.srt")]
        torrent = FakeTorrent(hash="hash1", save_path="/data/tv", files=files)
        qbt = make_relocation_qbt([torrent])

        paths = qbt.torrent_file_paths("hash1")
        Qbt.add_torrent_files(qbt, "hash1", files, "/data/tv")

        assert paths == set(qbt.torrentfiles)
        assert paths == {"/data/tv/file1.mkv", "/data/tv/subs/file2.srt"}

    def test_fetches_once_per_hash(self):
        torrent = FakeTorrent(hash="hash1", save_path="/data/tv", files=[FakeFile("file1.mkv")])
        qbt = make_relocation_qbt([torrent])

        qbt.torrent_file_paths("hash1")
        qbt.torrent_file_paths("hash1")

        assert qbt.get_all_torrents.call_count == 1

    def test_unreadable_file_list_returns_none(self):
        torrent = FakeTorrent(hash="hash1", save_path="/data/tv")
        torrent.files = BrokenFiles()
        qbt = make_relocation_qbt([torrent])

        assert qbt.torrent_file_paths("hash1") is None

    def test_unknown_hash_returns_none(self):
        qbt = make_relocation_qbt([FakeTorrent(hash="hash1")])
        assert qbt.torrent_file_paths("missing") is None


class TestHasSharedFiles:
    """Test Qbt.has_shared_files() intersection and fail-closed behavior."""

    def _candidate_and_peer(self, peer_files):
        candidate = FakeTorrent(hash="candidate", save_path="/data/tv", files=[FakeFile("file1.mkv")])
        peer = FakeTorrent(hash="peer", save_path="/data/tv", files=peer_files)
        return make_relocation_qbt([candidate, peer])

    def test_shared_file_returns_true(self):
        qbt = self._candidate_and_peer([FakeFile("file1.mkv")])
        assert qbt.has_shared_files("candidate", "/data/tv") is True

    def test_disjoint_files_return_false(self):
        qbt = self._candidate_and_peer([FakeFile("other.mkv")])
        assert qbt.has_shared_files("candidate", "/data/tv") is False

    def test_unreadable_peer_file_list_returns_true(self):
        qbt = self._candidate_and_peer(BrokenFiles())
        assert qbt.has_shared_files("candidate", "/data/tv") is True

    def test_unreadable_candidate_file_list_returns_true(self):
        qbt = self._candidate_and_peer([FakeFile("file1.mkv")])
        qbt.get_all_torrents.return_value[0].files = BrokenFiles()
        assert qbt.has_shared_files("candidate", "/data/tv") is True

    def test_unreadable_peer_list_returns_true(self):
        qbt = make_relocation_qbt([])
        qbt.get_all_torrents.side_effect = RuntimeError("client unavailable")
        assert qbt.has_shared_files("candidate", "/data/tv") is True


class TestRelocateTorrent:
    """Test Qbt.relocate_torrent() boolean outcome reporting."""

    def test_calls_set_location_and_returns_true(self):
        torrent = MagicMock()
        qbt = MagicMock(spec=Qbt)

        assert Qbt.relocate_torrent(qbt, torrent, "/data/new") is True
        torrent.set_location.assert_called_once_with(location="/data/new")

    def test_swallowed_api_error_returns_false(self):
        torrent = MagicMock()
        torrent.set_location.side_effect = NotFound404Error("torrent not found")
        qbt = MagicMock(spec=Qbt)

        assert Qbt.relocate_torrent(qbt, torrent, "/data/new") is False
        torrent.set_location.assert_called_once_with(location="/data/new")


class TestRelocationPrimitiveCaches:
    """Test that Qbt.__init__ wires the relocation caches for a run."""

    @patch("modules.qbittorrent.Version.is_app_version_supported", return_value=True)
    @patch("modules.qbittorrent.Qbt.get_torrents", return_value=[])
    @patch("modules.qbittorrent.Client")
    @patch("modules.qbittorrent.logger.secret", create=True)
    def test_constructor_wires_caches(self, _mock_secret, mock_client, _mock_get_torrents, _mock_version_supported):
        mock_client.return_value = make_qbt_client()
        qbt = Qbt(make_qbt_config(), {"host": "localhost:8080", "username": None, "password": None})

        for name in ("category_config_path", "get_all_torrents", "torrent_file_paths"):
            assert hasattr(getattr(qbt, name), "cache_info"), name
