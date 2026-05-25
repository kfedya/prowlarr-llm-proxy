"""Unit tests for SubtitleService."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.subtitle import SubtitleService


def _file(name: str) -> SimpleNamespace:
    """Create a mock TorrentFile with a .name attribute."""
    return SimpleNamespace(name=name)


class TestFilterSubtitleFiles:
    def test_returns_subtitle_names(self):
        svc = SubtitleService()
        files = [
            _file("video.mkv"),
            _file("sub.srt"),
            _file("another.ass"),
            _file("movie.mp4"),
            _file("caption.vtt"),
        ]
        result = svc.filter_subtitle_files(files)
        assert result == ["sub.srt", "another.ass", "caption.vtt"]

    def test_empty_list(self):
        svc = SubtitleService()
        assert svc.filter_subtitle_files([]) == []

    def test_no_subtitles(self):
        svc = SubtitleService()
        files = [_file("video.mkv"), _file("movie.mp4"), _file("clip.avi")]
        assert svc.filter_subtitle_files(files) == []

    def test_case_insensitive(self):
        svc = SubtitleService()
        files = [_file("sub.SRT"), _file("track.Ass"), _file("cap.VTT")]
        result = svc.filter_subtitle_files(files)
        assert result == ["sub.SRT", "track.Ass", "cap.VTT"]

    def test_all_extensions(self):
        svc = SubtitleService()
        files = [
            _file("a.ass"),
            _file("b.srt"),
            _file("c.sub"),
            _file("d.ssa"),
            _file("e.vtt"),
            _file("f.sup"),
        ]
        result = svc.filter_subtitle_files(files)
        assert len(result) == 6

    def test_nested_paths(self):
        svc = SubtitleService()
        files = [_file("Subs/Episode 01/track.srt"), _file("video.mkv")]
        result = svc.filter_subtitle_files(files)
        assert result == ["Subs/Episode 01/track.srt"]


class TestMatchSubtitlesToVideos:
    @pytest.mark.asyncio
    async def test_no_llm_returns_empty(self):
        svc = SubtitleService(llm_service=None)
        result = await svc.match_subtitles_to_videos(
            subtitle_files=["sub.srt"],
            video_mappings={"old.mkv": "new.mkv"},
        )
        assert result == {}

    @pytest.mark.asyncio
    async def test_empty_subtitle_files(self):
        mock_llm = AsyncMock()
        svc = SubtitleService(llm_service=mock_llm)
        result = await svc.match_subtitles_to_videos(
            subtitle_files=[],
            video_mappings={"old.mkv": "new.mkv"},
        )
        assert result == {}
        mock_llm.normalize_subtitle_names.assert_not_called()

    @pytest.mark.asyncio
    async def test_empty_video_mappings(self):
        mock_llm = AsyncMock()
        svc = SubtitleService(llm_service=mock_llm)
        result = await svc.match_subtitles_to_videos(
            subtitle_files=["sub.srt"],
            video_mappings={},
        )
        assert result == {}
        mock_llm.normalize_subtitle_names.assert_not_called()

    @pytest.mark.asyncio
    async def test_delegates_to_llm(self):
        expected = {"old_sub.srt": "Show - S01E01.srt"}
        mock_llm = AsyncMock()
        mock_llm.normalize_subtitle_names.return_value = expected

        svc = SubtitleService(llm_service=mock_llm)
        result = await svc.match_subtitles_to_videos(
            subtitle_files=["old_sub.srt"],
            video_mappings={"old_video.mkv": "Show - S01E01.mkv"},
        )

        assert result == expected
        mock_llm.normalize_subtitle_names.assert_awaited_once_with(
            subtitle_files=["old_sub.srt"],
            video_mappings={"old_video.mkv": "Show - S01E01.mkv"},
        )
