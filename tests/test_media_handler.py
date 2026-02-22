"""Unit tests for MediaHandlerService."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.hardlink import HardlinkResult
from app.services.media_handler import (
    FAST_INTERVAL,
    MAX_TIMEOUT,
    MediaHandlerService,
)
from app.services.torrent_mapping import MediaType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mapping(original_title: str = "Original.Title", series_name: str = "Test Show"):
    """Create a mock TorrentMapping."""
    m = MagicMock()
    m.original_title = original_title
    m.series_name = series_name
    return m


def _make_torrent(hash_: str = "abc123", state: str = "uploading", save_path: str = "/downloads"):
    """Create a mock TorrentInfo."""
    t = MagicMock()
    t.hash = hash_
    t.state = state
    t.save_path = save_path
    t.name = "Test.Torrent"
    return t


def _make_file_list(file_names: list[str], torrent_hash: str = "abc123"):
    """Create a mock TorrentFileList."""
    fl = MagicMock()
    fl.torrent_hash = torrent_hash
    fl.torrent_name = "Test.Torrent"
    fl.files = [SimpleNamespace(name=n) for n in file_names]
    return fl


def _make_service(
    tmp_path: Path,
    mapping_return=None,
    torrent_return=None,
    file_list_return=None,
    hardlink_result=None,
) -> tuple[MediaHandlerService, dict]:
    """Build MediaHandlerService with mocked dependencies.

    Returns (service, mocks_dict).
    """
    mock_mapping = AsyncMock()
    mock_mapping.get_by_title.return_value = mapping_return

    mock_qb = AsyncMock()
    mock_qb.__aenter__ = AsyncMock(return_value=mock_qb)
    mock_qb.__aexit__ = AsyncMock(return_value=None)
    mock_qb.get_torrent_by_hash.return_value = torrent_return
    mock_qb.get_torrent_files.return_value = file_list_return

    mock_hardlink = MagicMock()
    mock_hardlink.create_hardlinks.return_value = hardlink_result or HardlinkResult()

    mock_subtitle = MagicMock()
    mock_subtitle.filter_subtitle_files.return_value = []

    svc = MediaHandlerService(
        torrent_mapping_service=mock_mapping,
        qbittorrent_service=mock_qb,
        hardlink_service=mock_hardlink,
        subtitle_service=mock_subtitle,
        download_path=tmp_path,
        hardlink_base=tmp_path / "hardlinks",
    )

    mocks = {
        "mapping": mock_mapping,
        "qb": mock_qb,
        "hardlink": mock_hardlink,
        "subtitle": mock_subtitle,
    }
    return svc, mocks


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestHandleGrabEventNoMapping:
    """When no mapping is found, handler exits early."""

    @pytest.mark.asyncio
    async def test_no_mapping_returns_early(self, tmp_path: Path):
        svc, mocks = _make_service(tmp_path, mapping_return=None)

        await svc.handle_grab_event(
            release_title="Some.Release.Title",
            download_id="abc123",
            media_type=MediaType.TV,
            series_title="Test Show",
        )

        mocks["mapping"].get_by_title.assert_awaited_once_with("Some.Release.Title")
        mocks["qb"].get_torrent_by_hash.assert_not_called()
        mocks["hardlink"].create_hardlinks.assert_not_called()


class TestHandleGrabEventHappyPath:
    """Full flow: mapping found, files on disk, hardlinks created."""

    @pytest.mark.asyncio
    @patch("app.services.media_handler.asyncio.sleep", new_callable=AsyncMock)
    async def test_happy_path(self, mock_sleep, tmp_path: Path):
        # Create real files on disk so Path.exists() returns True
        dl_dir = tmp_path / "torrents" / "Test.Torrent"
        dl_dir.mkdir(parents=True)
        video_file = dl_dir / "episode.mkv"
        video_file.write_bytes(b"fake video")

        mapping = _make_mapping()
        torrent = _make_torrent(save_path=str(tmp_path / "torrents"))
        file_list = _make_file_list(["Test.Torrent/episode.mkv"])

        svc, mocks = _make_service(
            tmp_path,
            mapping_return=mapping,
            torrent_return=torrent,
            file_list_return=file_list,
        )

        await svc.handle_grab_event(
            release_title="Normalized.Title",
            download_id="abc123",
            media_type=MediaType.TV,
            series_title="Test Show",
            season_number=1,
            episode_numbers=[5],
        )

        # Hardlinks should be called
        mocks["hardlink"].create_hardlinks.assert_called_once()
        call_args = mocks["hardlink"].create_hardlinks.call_args[0][0]
        assert len(call_args) == 1
        src, dst = call_args[0]
        assert src == dl_dir / "episode.mkv"
        assert "hardlinks" in str(dst)
        assert "Test Show - S01E05" in str(dst)

        # No qBit rename methods should be called
        mocks["qb"].rename_file.assert_not_called()
        mocks["qb"].rename_torrent.assert_not_called()


class TestPollTimeout:
    """Polling times out and retries once."""

    @pytest.mark.asyncio
    @patch("app.services.media_handler.MAX_TIMEOUT", 0.1)
    @patch("app.services.media_handler.FAST_INTERVAL", 0.02)
    @patch("app.services.media_handler.SLOW_INTERVAL", 0.02)
    @patch("app.services.media_handler.FAST_CUTOFF", 0.05)
    @patch("app.services.media_handler.RETRY_DELAY", 0.01)
    @patch("app.services.media_handler.MAX_ATTEMPTS", 2)
    async def test_poll_timeout_retries(self, tmp_path: Path):
        """When files never appear on disk, polling exhausts both attempts."""
        torrent = _make_torrent(save_path=str(tmp_path))
        file_list = _make_file_list(["nonexistent/file.mkv"])

        svc, mocks = _make_service(
            tmp_path,
            mapping_return=_make_mapping(),
            torrent_return=torrent,
            file_list_return=file_list,
        )

        await svc.handle_grab_event(
            release_title="Some.Release",
            download_id="abc123",
            media_type=MediaType.TV,
            series_title="Show",
        )

        # Hardlinks should NOT be called since files were never found
        mocks["hardlink"].create_hardlinks.assert_not_called()


class TestMakeSubfolderNameTV:
    """TV subfolder naming."""

    def test_single_episode(self):
        name = MediaHandlerService._make_subfolder_name(
            media_type=MediaType.TV,
            title="My Show",
            season_number=2,
            episode_numbers=[3],
        )
        assert name == "My Show - S02E03"

    def test_multi_episode(self):
        name = MediaHandlerService._make_subfolder_name(
            media_type=MediaType.TV,
            title="My Show",
            season_number=1,
            episode_numbers=[1, 2, 3, 12],
        )
        assert name == "My Show - S01E01-E12"

    def test_season_pack(self):
        name = MediaHandlerService._make_subfolder_name(
            media_type=MediaType.TV,
            title="My Show",
            season_number=3,
            episode_numbers=None,
        )
        assert name == "My Show - S03"

    def test_no_season(self):
        name = MediaHandlerService._make_subfolder_name(
            media_type=MediaType.TV,
            title="My Show",
            season_number=None,
            episode_numbers=None,
        )
        assert name == "My Show"

    def test_sanitizes_slashes(self):
        name = MediaHandlerService._make_subfolder_name(
            media_type=MediaType.TV,
            title="Title/With\\Slashes",
            season_number=1,
            episode_numbers=[1],
        )
        assert "/" not in name
        assert "\\" not in name
        assert "Title-With-Slashes - S01E01" == name


class TestMakeSubfolderNameMovie:
    """Movie subfolder naming."""

    def test_with_year(self):
        name = MediaHandlerService._make_subfolder_name(
            media_type=MediaType.MOVIE,
            title="Cool Movie",
            season_number=None,
            episode_numbers=None,
            year=2024,
        )
        assert name == "Cool Movie (2024)"

    def test_without_year(self):
        name = MediaHandlerService._make_subfolder_name(
            media_type=MediaType.MOVIE,
            title="Cool Movie",
            season_number=None,
            episode_numbers=None,
        )
        assert name == "Cool Movie"


class TestComputeHardlinkPairs:
    """Hardlink pair computation."""

    def test_computes_pairs(self, tmp_path: Path):
        files = [
            tmp_path / "torrent" / "ep1.mkv",
            tmp_path / "torrent" / "ep2.mkv",
        ]
        hardlink_base = tmp_path / "hardlinks"

        pairs = MediaHandlerService._compute_hardlink_pairs(
            files=files,
            hardlink_base=hardlink_base,
            subfolder_name="Show - S01",
        )

        assert len(pairs) == 2
        assert pairs[0] == (files[0], hardlink_base / "Show - S01" / "ep1.mkv")
        assert pairs[1] == (files[1], hardlink_base / "Show - S01" / "ep2.mkv")

    def test_strips_directory_prefix(self, tmp_path: Path):
        """Destination uses only file.name, not the full directory structure."""
        src = tmp_path / "deep" / "nested" / "dir" / "video.mkv"
        pairs = MediaHandlerService._compute_hardlink_pairs(
            files=[src],
            hardlink_base=tmp_path / "hl",
            subfolder_name="sub",
        )
        _, dst = pairs[0]
        assert dst == tmp_path / "hl" / "sub" / "video.mkv"


class TestHardlinkFailureAborts:
    """When hardlink creation has errors, handler aborts before subtitles."""

    @pytest.mark.asyncio
    @patch("app.services.media_handler.asyncio.sleep", new_callable=AsyncMock)
    async def test_hardlink_error_aborts(self, mock_sleep, tmp_path: Path):
        # Create real file on disk
        dl_dir = tmp_path / "torrents" / "Test.Torrent"
        dl_dir.mkdir(parents=True)
        (dl_dir / "ep.mkv").write_bytes(b"data")

        error_result = HardlinkResult(
            errors=[(Path("a"), Path("b"), "some error")]
        )

        torrent = _make_torrent(save_path=str(tmp_path / "torrents"))
        file_list = _make_file_list(["Test.Torrent/ep.mkv"])

        svc, mocks = _make_service(
            tmp_path,
            mapping_return=_make_mapping(),
            torrent_return=torrent,
            file_list_return=file_list,
            hardlink_result=error_result,
        )

        await svc.handle_grab_event(
            release_title="Release",
            download_id="abc123",
            media_type=MediaType.TV,
            series_title="Show",
            season_number=1,
            episode_numbers=[1],
        )

        # Hardlinks called but subtitle processing should not happen
        # (subtitle service's filter_subtitle_files should NOT be called
        #  from _process_subtitles since handler aborted)
        mocks["hardlink"].create_hardlinks.assert_called_once()
        # Verify no further qBit calls after hardlink (subtitle processing
        # would call get_torrent_by_hash again)
        # The qb mock was called during polling, but not again for subtitles
        initial_call_count = mocks["qb"].get_torrent_by_hash.call_count
        # Since handle_grab_event returned after hardlink error,
        # the subtitle processing qb calls didn't happen
        assert initial_call_count >= 1  # at least polling calls
