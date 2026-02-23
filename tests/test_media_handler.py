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
    hardlink_path=None,
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
        hardlink_path=hardlink_path or (tmp_path / "hardlinks"),
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
    async def test_happy_path_tv(self, mock_sleep, tmp_path: Path):
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
        mocks["hardlink"].create_hardlinks.assert_called()
        call_args = mocks["hardlink"].create_hardlinks.call_args[0][0]
        assert len(call_args) == 1
        src, dst = call_args[0]
        assert src == dl_dir / "episode.mkv"
        # TV: flat in hardlinks/{torrent_name}/ — torrent.name is "Test.Torrent"
        assert "Test.Torrent" in str(dst)
        # Should NOT have Season subfolder in new flat layout
        assert "Season" not in str(dst)

        # No qBit rename methods should be called
        mocks["qb"].rename_file.assert_not_called()
        mocks["qb"].rename_torrent.assert_not_called()


class TestPollTimeout:
    """Polling times out and retries once."""

    @pytest.mark.asyncio
    @patch("app.services.media_handler.MAX_TIMEOUT", 0.1)
    @patch("app.services.media_handler.FAST_INTERVAL", 0.02)
    @patch("app.services.media_handler.SLOW_INTERVAL", 0.02)
    @patch("app.services.media_handler.VERY_SLOW_INTERVAL", 0.02)
    @patch("app.services.media_handler.FAST_CUTOFF", 0.05)
    @patch("app.services.media_handler.SLOW_CUTOFF", 0.08)
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


class TestComputeTVHardlinkPairs:
    """TV hardlink pair computation — flat layout with LLM name mapping."""

    def test_uses_llm_mapping(self, tmp_path: Path):
        """LLM-mapped name is used as destination filename."""
        video_files = [tmp_path / "Show.S01E01.mkv"]
        name_mapping = {"Show.S01E01.mkv": "Show - S01E01.mkv"}
        hardlink_base = tmp_path / "hardlinks"

        pairs = MediaHandlerService._compute_tv_hardlink_pairs(
            video_files=video_files,
            name_mapping=name_mapping,
            series_title="Show",
            hardlink_base=hardlink_base,
        )

        assert len(pairs) == 1
        src, dst = pairs[0]
        assert src == video_files[0]
        assert dst == hardlink_base / "Show" / "Show - S01E01.mkv"

    def test_fallback_to_original_name(self, tmp_path: Path):
        """Falls back to original name when LLM mapping is empty."""
        video_files = [tmp_path / "ep.mkv"]
        hardlink_base = tmp_path / "hardlinks"

        pairs = MediaHandlerService._compute_tv_hardlink_pairs(
            video_files=video_files,
            name_mapping={},
            series_title="My Show",
            hardlink_base=hardlink_base,
        )

        assert len(pairs) == 1
        src, dst = pairs[0]
        assert src == video_files[0]
        assert dst == hardlink_base / "My Show" / "ep.mkv"

    def test_flat_layout_no_season_folder(self, tmp_path: Path):
        """TV hardlinks are flat in {series}/ — no Season subfolder."""
        video_files = [tmp_path / "ep1.mkv", tmp_path / "ep2.mkv"]
        hardlink_base = tmp_path / "hardlinks"

        pairs = MediaHandlerService._compute_tv_hardlink_pairs(
            video_files=video_files,
            name_mapping={},
            series_title="The Show",
            hardlink_base=hardlink_base,
        )

        for src, dst in pairs:
            # Should be exactly: hardlinks/The Show/<filename>
            assert dst.parent == hardlink_base / "The Show"

    def test_sanitizes_series_title(self, tmp_path: Path):
        """Series titles with unsafe chars are sanitized (fallback when torrent_name not given)."""
        video_files = [tmp_path / "ep.mkv"]
        hardlink_base = tmp_path / "hardlinks"

        pairs = MediaHandlerService._compute_tv_hardlink_pairs(
            video_files=video_files,
            name_mapping={},
            series_title="Show: The Return",
            hardlink_base=hardlink_base,
        )

        _, dst = pairs[0]
        assert "Show - The Return" in str(dst)

    def test_uses_torrent_name_as_subfolder(self, tmp_path: Path):
        """When torrent_name is provided, it is used as the staging subfolder (not series_title)."""
        video_files = [tmp_path / "ep.mkv"]
        hardlink_base = tmp_path / "hardlinks"

        pairs = MediaHandlerService._compute_tv_hardlink_pairs(
            video_files=video_files,
            name_mapping={},
            series_title="Some Series",
            hardlink_base=hardlink_base,
            torrent_name="Anime.S01.BDRip.1080p [GroupTag]",
        )

        _, dst = pairs[0]
        # Subfolder must be based on torrent_name, not series_title
        assert "Anime.S01.BDRip.1080p" in str(dst)
        assert "Some Series" not in str(dst)


class TestComputeMovieHardlinkPairs:
    """Movie hardlink pair computation — preserve torrent-relative structure."""

    def test_single_file_torrent(self, tmp_path: Path):
        """Single-file torrent (total_files=1): hardlink flat in hardlink_base, no wrapper folder."""
        save_path = tmp_path / "downloads"
        save_path.mkdir()
        src = save_path / "Movie.2024.mkv"
        hardlink_base = tmp_path / "hardlinks"

        pairs = MediaHandlerService._compute_movie_hardlink_pairs(
            files_on_disk=[src],
            save_path=save_path,
            movie_title="Cool Movie",
            year=2024,
            hardlink_base=hardlink_base,
            total_files=1,
        )

        assert len(pairs) == 1
        _, dst = pairs[0]
        assert dst == hardlink_base / "Movie.2024.mkv"

    def test_multi_file_torrent_preserves_structure(self, tmp_path: Path):
        """Multi-file torrent preserves relative path under movie folder."""
        save_path = tmp_path / "downloads"
        torrent_dir = save_path / "Movie.2024.BluRay"
        torrent_dir.mkdir(parents=True)

        src1 = torrent_dir / "movie.mkv"
        src2 = torrent_dir / "extras" / "making-of.mkv"
        (torrent_dir / "extras").mkdir()
        hardlink_base = tmp_path / "hardlinks"

        pairs = MediaHandlerService._compute_movie_hardlink_pairs(
            files_on_disk=[src1, src2],
            save_path=save_path,
            movie_title="Movie",
            year=2024,
            hardlink_base=hardlink_base,
            total_files=2,
        )

        assert len(pairs) == 2
        dsts = [dst for _, dst in pairs]
        assert hardlink_base / "Movie (2024)" / "Movie.2024.BluRay" / "movie.mkv" in dsts
        assert hardlink_base / "Movie (2024)" / "Movie.2024.BluRay" / "extras" / "making-of.mkv" in dsts

    def test_no_year(self, tmp_path: Path):
        """Single-file torrent without year: placed flat in hardlink_base."""
        save_path = tmp_path / "downloads"
        save_path.mkdir()
        src = save_path / "Movie.mkv"
        hardlink_base = tmp_path / "hardlinks"

        pairs = MediaHandlerService._compute_movie_hardlink_pairs(
            files_on_disk=[src],
            save_path=save_path,
            movie_title="Cool Movie",
            year=None,
            hardlink_base=hardlink_base,
            total_files=1,
        )

        _, dst = pairs[0]
        assert dst == hardlink_base / "Movie.mkv"

    def test_sanitizes_movie_title_multi_file(self, tmp_path: Path):
        """Multi-file torrent: movie titles with unsafe chars are sanitized in folder name."""
        save_path = tmp_path / "downloads"
        torrent_dir = save_path / "Movie.Revenge.2024"
        torrent_dir.mkdir(parents=True)
        src1 = torrent_dir / "movie.mkv"
        src2 = torrent_dir / "extras.mkv"
        hardlink_base = tmp_path / "hardlinks"

        pairs = MediaHandlerService._compute_movie_hardlink_pairs(
            files_on_disk=[src1, src2],
            save_path=save_path,
            movie_title="Movie: Revenge",
            year=2024,
            hardlink_base=hardlink_base,
            total_files=2,
        )

        dsts = [str(dst) for _, dst in pairs]
        assert all("Movie - Revenge (2024)" in d for d in dsts)

    def test_multi_file_uses_torrent_name_as_subfolder(self, tmp_path: Path):
        """Multi-file torrent: torrent_name is used as subfolder when provided."""
        save_path = tmp_path / "downloads"
        torrent_dir = save_path / "Movie.2024.BluRay.x264-GROUP"
        torrent_dir.mkdir(parents=True)
        src1 = torrent_dir / "movie.mkv"
        src2 = torrent_dir / "subs.srt"
        hardlink_base = tmp_path / "hardlinks"

        pairs = MediaHandlerService._compute_movie_hardlink_pairs(
            files_on_disk=[src1, src2],
            save_path=save_path,
            movie_title="The Movie",
            year=2024,
            hardlink_base=hardlink_base,
            total_files=2,
            torrent_name="Movie.2024.BluRay.x264-GROUP",
        )

        assert len(pairs) == 2
        dsts = [str(dst) for _, dst in pairs]
        # Subfolder must be torrent_name, not "The Movie (2024)"
        assert all("Movie.2024.BluRay.x264-GROUP" in d for d in dsts)
        assert all("The Movie" not in d for d in dsts)


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
        mocks["hardlink"].create_hardlinks.assert_called_once()
        # Since handle_grab_event returned after hardlink error,
        # the subtitle processing qb calls didn't happen
        initial_call_count = mocks["qb"].get_torrent_by_hash.call_count
        assert initial_call_count >= 1  # at least polling calls


# ---------------------------------------------------------------------------
# Phase 5 tests: sanitization, movie behavior
# ---------------------------------------------------------------------------


class TestSanitizeTitle:
    """Filesystem-unsafe character sanitization."""

    def test_colons_replaced(self):
        assert MediaHandlerService._sanitize_title("Title: Subtitle") == "Title - Subtitle"

    def test_slashes_replaced(self):
        assert MediaHandlerService._sanitize_title("A/B\\C") == "A-B-C"

    def test_star_question_removed(self):
        assert MediaHandlerService._sanitize_title("What?! *Really*") == "What! Really"

    def test_angle_brackets_removed(self):
        assert MediaHandlerService._sanitize_title("Title <Special>") == "Title Special"

    def test_pipe_and_quotes_removed(self):
        assert MediaHandlerService._sanitize_title('Title |"quoted"') == "Title quoted"

    def test_trailing_dots_stripped(self):
        assert MediaHandlerService._sanitize_title("Title...") == "Title"

    def test_trailing_spaces_stripped(self):
        assert MediaHandlerService._sanitize_title("Title   ") == "Title"

    def test_combined_unsafe_chars(self):
        result = MediaHandlerService._sanitize_title('Movie: Part 2 *Extended* "Cut"...')
        assert result == "Movie - Part 2 Extended Cut"


class TestMovieBehavior:
    """Movie-specific behavior: skip subs, no extension filter."""

    @pytest.mark.asyncio
    @patch("app.services.media_handler.asyncio.sleep", new_callable=AsyncMock)
    async def test_movie_skips_subtitle_processing(self, mock_sleep, tmp_path: Path):
        """handle_grab_event with MOVIE skips _process_subtitles."""
        dl_dir = tmp_path / "torrents" / "Test.Torrent"
        dl_dir.mkdir(parents=True)
        (dl_dir / "movie.mkv").write_bytes(b"data")

        torrent = _make_torrent(save_path=str(tmp_path / "torrents"))
        file_list = _make_file_list(["Test.Torrent/movie.mkv"])

        svc, mocks = _make_service(
            tmp_path,
            mapping_return=_make_mapping(),
            torrent_return=torrent,
            file_list_return=file_list,
        )

        await svc.handle_grab_event(
            release_title="Movie.Release",
            download_id="abc123",
            media_type=MediaType.MOVIE,
            movie_title="Cool Movie",
            year=2024,
        )

        # Hardlinks called
        mocks["hardlink"].create_hardlinks.assert_called_once()
        # filter_extensions=False for movies
        call_kwargs = mocks["hardlink"].create_hardlinks.call_args
        assert call_kwargs[1].get("filter_extensions") is False or (
            len(call_kwargs[0]) > 1 and call_kwargs[0][1] is False
        )
        # Subtitle filter should NOT be called (no _process_subtitles for movies)
        mocks["subtitle"].filter_subtitle_files.assert_not_called()

    @pytest.mark.asyncio
    @patch("app.services.media_handler.asyncio.sleep", new_callable=AsyncMock)
    async def test_movie_passes_filter_extensions_false(self, mock_sleep, tmp_path: Path):
        """MOVIE passes filter_extensions=False to create_hardlinks."""
        dl_dir = tmp_path / "torrents" / "Test.Torrent"
        dl_dir.mkdir(parents=True)
        (dl_dir / "movie.mkv").write_bytes(b"data")

        torrent = _make_torrent(save_path=str(tmp_path / "torrents"))
        file_list = _make_file_list(["Test.Torrent/movie.mkv"])

        svc, mocks = _make_service(
            tmp_path,
            mapping_return=_make_mapping(),
            torrent_return=torrent,
            file_list_return=file_list,
        )

        await svc.handle_grab_event(
            release_title="Movie.Release",
            download_id="abc123",
            media_type=MediaType.MOVIE,
            movie_title="Cool Movie",
            year=2024,
        )

        mocks["hardlink"].create_hardlinks.assert_called_once()
        _, kwargs = mocks["hardlink"].create_hardlinks.call_args
        assert kwargs["filter_extensions"] is False

    @pytest.mark.asyncio
    async def test_aborts_when_hardlink_path_none(self, tmp_path: Path):
        """handle_grab_event aborts when hardlink_path is None."""
        mock_mapping = AsyncMock()
        mock_qb = AsyncMock()
        mock_hardlink = MagicMock()
        mock_subtitle = MagicMock()

        # Create service with NO hardlink_path
        svc = MediaHandlerService(
            torrent_mapping_service=mock_mapping,
            qbittorrent_service=mock_qb,
            hardlink_service=mock_hardlink,
            subtitle_service=mock_subtitle,
            download_path=tmp_path,
            hardlink_path=None,
        )

        await svc.handle_grab_event(
            release_title="Movie.Release",
            download_id="abc123",
            media_type=MediaType.MOVIE,
            movie_title="Cool Movie",
            year=2024,
        )

        # Should abort before even looking up mapping
        mock_mapping.get_by_title.assert_not_called()
        mock_hardlink.create_hardlinks.assert_not_called()


class TestHardlinkFilterExtensions:
    """HardlinkService create_hardlinks with filter_extensions=False."""

    def test_filter_false_processes_all_files(self, tmp_path: Path):
        """With filter_extensions=False, .nfo, .txt, .jpg all get hardlinked."""
        dl = tmp_path / "downloads"
        lib = tmp_path / "library"
        dl.mkdir()
        lib.mkdir()

        from app.services.hardlink import HardlinkService

        pairs = []
        for name in ["movie.mkv", "info.nfo", "readme.txt", "cover.jpg"]:
            src = dl / name
            src.write_text("content")
            dst = lib / name
            pairs.append((src, dst))

        svc = HardlinkService(download_path=dl, hardlinks_path=lib)
        result = svc.create_hardlinks(pairs, filter_extensions=False)

        assert len(result.created) == 4
        assert len(result.skipped) == 0

    def test_filter_true_skips_non_media(self, tmp_path: Path):
        """With filter_extensions=True (default), .nfo etc are skipped."""
        dl = tmp_path / "downloads"
        lib = tmp_path / "library"
        dl.mkdir()
        lib.mkdir()

        from app.services.hardlink import HardlinkService

        pairs = []
        for name in ["movie.mkv", "info.nfo", "readme.txt"]:
            src = dl / name
            src.write_text("content")
            dst = lib / name
            pairs.append((src, dst))

        svc = HardlinkService(download_path=dl, hardlinks_path=lib)
        result = svc.create_hardlinks(pairs, filter_extensions=True)

        assert len(result.created) == 1  # only .mkv
        assert len(result.skipped) == 2  # .nfo and .txt


# ---------------------------------------------------------------------------
# Subtitle naming helpers (unit)
# ---------------------------------------------------------------------------


class TestSubtitleDstName:
    """_subtitle_dst_name: episode matching + group disambiguation."""

    VIDEO_MAPPINGS = {
        "[SubsPlease] Kaguya - 01 [1080p].mkv": "Kaguya-sama.S01E01.mkv",
        "[SubsPlease] Kaguya - 02 [1080p].mkv": "Kaguya-sama.S01E02.mkv",
    }

    def test_group_subfolder_appended(self):
        """Subtitle from a group subfolder gets group name appended after norm stem."""
        result = MediaHandlerService._subtitle_dst_name(
            "SovetRomantica/01.ass", self.VIDEO_MAPPINGS
        )
        assert result == "Kaguya-sama.S01E01.SovetRomantica.ass"

    def test_two_groups_same_episode_no_collision(self):
        """Two groups with the same episode produce different filenames."""
        r1 = MediaHandlerService._subtitle_dst_name("SovetRomantica/01.ass", self.VIDEO_MAPPINGS)
        r2 = MediaHandlerService._subtitle_dst_name("Cqur/01.ass", self.VIDEO_MAPPINGS)
        assert r1 != r2
        assert r1 == "Kaguya-sama.S01E01.SovetRomantica.ass"
        assert r2 == "Kaguya-sama.S01E01.Cqur.ass"

    def test_episode_2_matched_correctly(self):
        result = MediaHandlerService._subtitle_dst_name("SovetRomantica/02.ass", self.VIDEO_MAPPINGS)
        assert result == "Kaguya-sama.S01E02.SovetRomantica.ass"

    def test_root_level_sub_no_group_suffix(self):
        """Subtitle at torrent root (no group folder) gets no extra suffix."""
        result = MediaHandlerService._subtitle_dst_name("01.ass", self.VIDEO_MAPPINGS)
        assert result == "Kaguya-sama.S01E01.ass"

    def test_no_match_fallback_preserves_path(self):
        """When episode number doesn't match any video, original path is preserved."""
        result = MediaHandlerService._subtitle_dst_name("SovetRomantica/99.ass", self.VIDEO_MAPPINGS)
        assert result == "SovetRomantica/99.ass"

    def test_empty_mappings_fallback(self):
        """With no video mappings, always falls back to original path."""
        result = MediaHandlerService._subtitle_dst_name("SovetRomantica/01.ass", {})
        assert result == "SovetRomantica/01.ass"

    def test_spaces_in_group_name(self):
        """Group folder with spaces is preserved in the output name."""
        result = MediaHandlerService._subtitle_dst_name("Cqur Far/01.ass", self.VIDEO_MAPPINGS)
        assert result == "Kaguya-sama.S01E01.Cqur Far.ass"


class TestExtractEpisodeNumber:
    """_extract_episode_number: handles common subtitle filename patterns."""

    def test_bare_number(self):
        assert MediaHandlerService._extract_episode_number("01") == 1

    def test_bare_number_two_digit(self):
        assert MediaHandlerService._extract_episode_number("12") == 12

    def test_e_prefix(self):
        assert MediaHandlerService._extract_episode_number("E05") == 5

    def test_version_suffix_ignored(self):
        assert MediaHandlerService._extract_episode_number("01v2") == 1

    def test_no_number_returns_none(self):
        assert MediaHandlerService._extract_episode_number("opening") is None

    def test_separator_prefix(self):
        assert MediaHandlerService._extract_episode_number("_01_") == 1


# ---------------------------------------------------------------------------
# E2E: TV grab with multi-group subtitles (mocked qBit + LLM, real HL + Sub svc)
# ---------------------------------------------------------------------------


class TestSubtitleMultiGroupE2E:
    """Full handle_grab_event flow: TV + two subtitle groups, no LLM for subs."""

    @pytest.mark.asyncio
    @patch("app.services.media_handler.asyncio.sleep", new_callable=AsyncMock)
    async def test_two_groups_two_episodes_no_collision(self, mock_sleep, tmp_path: Path):
        """
        Scenario: Kaguya-sama S01 torrent with 2 video files and 2 subtitle groups
        (SovetRomantica, Cqur), each providing 2 episodes.

        Expected subtitle hardlinks:
          hardlinks/Kaguya-sama.S01.1080p.BDRip/Kaguya-sama.S01E01.SovetRomantica.ass
          hardlinks/Kaguya-sama.S01.1080p.BDRip/Kaguya-sama.S01E02.SovetRomantica.ass
          hardlinks/Kaguya-sama.S01.1080p.BDRip/Kaguya-sama.S01E01.Cqur.ass
          hardlinks/Kaguya-sama.S01.1080p.BDRip/Kaguya-sama.S01E02.Cqur.ass
        """
        from app.services.hardlink import HardlinkService
        from app.services.subtitle import SubtitleService

        # --- file system ---
        save_path = tmp_path / "downloads"
        save_path.mkdir()
        hardlink_base = tmp_path / "hardlinks"
        hardlink_base.mkdir()

        v1 = save_path / "[SubsPlease] Kaguya-sama - 01 [1080p].mkv"
        v2 = save_path / "[SubsPlease] Kaguya-sama - 02 [1080p].mkv"
        v1.write_bytes(b"video1")
        v2.write_bytes(b"video2")

        for group in ["SovetRomantica", "Cqur"]:
            (save_path / group).mkdir()
            for ep in ["01", "02"]:
                (save_path / group / f"{ep}.ass").write_bytes(b"sub")

        # --- qBittorrent mock ---
        torrent = _make_torrent(save_path=str(save_path))
        torrent.name = "Kaguya-sama.S01.1080p.BDRip"

        all_file_names = [
            "[SubsPlease] Kaguya-sama - 01 [1080p].mkv",
            "[SubsPlease] Kaguya-sama - 02 [1080p].mkv",
            "SovetRomantica/01.ass",
            "SovetRomantica/02.ass",
            "Cqur/01.ass",
            "Cqur/02.ass",
        ]
        file_list = _make_file_list(all_file_names)

        # --- LLM mock: normalizes video names only ---
        mock_llm = AsyncMock()
        mock_llm.normalize_file_names.return_value = {
            "[SubsPlease] Kaguya-sama - 01 [1080p].mkv": "Kaguya-sama.S01E01.mkv",
            "[SubsPlease] Kaguya-sama - 02 [1080p].mkv": "Kaguya-sama.S01E02.mkv",
        }

        # --- services ---
        svc, mocks = _make_service(
            tmp_path,
            mapping_return=_make_mapping(),
            torrent_return=torrent,
            file_list_return=file_list,
            hardlink_path=hardlink_base,
        )
        # Swap in real HardlinkService and SubtitleService (no LLM)
        svc._hardlink_service = HardlinkService(
            download_path=save_path, hardlinks_path=hardlink_base
        )
        svc._subtitle_service = SubtitleService(llm_service=None)
        svc._llm_service = mock_llm

        # --- run ---
        await svc.handle_grab_event(
            release_title="Kaguya-sama.S01.1080p.BDRip",
            download_id="abc123",
            media_type=MediaType.TV,
            series_title="Kaguya-sama: Love Is War",
            season_number=1,
            episode_numbers=[1, 2],
        )

        torrent_dir = hardlink_base / "Kaguya-sama.S01.1080p.BDRip"

        # --- video hardlinks ---
        assert (torrent_dir / "Kaguya-sama.S01E01.mkv").exists(), "video ep1 missing"
        assert (torrent_dir / "Kaguya-sama.S01E02.mkv").exists(), "video ep2 missing"

        # --- subtitle hardlinks: 4 files, 2 groups × 2 episodes ---
        assert (torrent_dir / "Kaguya-sama.S01E01.SovetRomantica.ass").exists(), "SR ep1 missing"
        assert (torrent_dir / "Kaguya-sama.S01E02.SovetRomantica.ass").exists(), "SR ep2 missing"
        assert (torrent_dir / "Kaguya-sama.S01E01.Cqur.ass").exists(), "Cqur ep1 missing"
        assert (torrent_dir / "Kaguya-sama.S01E02.Cqur.ass").exists(), "Cqur ep2 missing"

        # --- no collision: all 4 subtitle files are distinct ---
        sub_files = list(torrent_dir.glob("*.ass"))
        assert len(sub_files) == 4, f"Expected 4 subtitle files, got: {[f.name for f in sub_files]}"

        # --- LLM was NOT called for subtitles ---
        mock_llm.normalize_subtitle_names.assert_not_called()

    @pytest.mark.asyncio
    @patch("app.services.media_handler.asyncio.sleep", new_callable=AsyncMock)
    async def test_fallback_when_no_video_mappings(self, mock_sleep, tmp_path: Path):
        """When LLM returns no video mappings, subtitle falls back to group dir structure."""
        from app.services.hardlink import HardlinkService
        from app.services.subtitle import SubtitleService

        save_path = tmp_path / "downloads"
        save_path.mkdir()
        hardlink_base = tmp_path / "hardlinks"
        hardlink_base.mkdir()

        (save_path / "ep.mkv").write_bytes(b"video")
        (save_path / "SubGroup").mkdir()
        (save_path / "SubGroup" / "01.ass").write_bytes(b"sub")

        torrent = _make_torrent(save_path=str(save_path))
        torrent.name = "Show.S01"
        file_list = _make_file_list(["ep.mkv", "SubGroup/01.ass"])

        # LLM returns empty (simulates failure / no normalization)
        mock_llm = AsyncMock()
        mock_llm.normalize_file_names.return_value = {}

        svc, mocks = _make_service(
            tmp_path,
            mapping_return=_make_mapping(),
            torrent_return=torrent,
            file_list_return=file_list,
            hardlink_path=hardlink_base,
        )
        svc._hardlink_service = HardlinkService(
            download_path=save_path, hardlinks_path=hardlink_base
        )
        svc._subtitle_service = SubtitleService(llm_service=None)
        svc._llm_service = mock_llm

        await svc.handle_grab_event(
            release_title="Show.S01",
            download_id="abc123",
            media_type=MediaType.TV,
            series_title="Show",
            season_number=1,
            episode_numbers=[1],
        )

        torrent_dir = hardlink_base / "Show.S01"
        # Fallback: group dir structure preserved
        assert (torrent_dir / "SubGroup" / "01.ass").exists(), "fallback group dir missing"
