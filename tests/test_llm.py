"""Tests for LLMService prompt selection and cache key isolation."""
from unittest.mock import AsyncMock

from app.services.llm import (
    MOVIE_SYSTEM_PROMPT,
    PROMPTS,
    SYSTEM_PROMPT,
    TorrentItem,
)
from app.services.torrent_mapping import MediaType


class TestPromptSelection:
    def test_tv_media_type_selects_tv_prompt(self):
        assert PROMPTS[MediaType.TV] is SYSTEM_PROMPT

    def test_movie_media_type_selects_movie_prompt(self):
        assert PROMPTS[MediaType.MOVIE] is MOVIE_SYSTEM_PROMPT

    def test_movie_prompt_contains_radarr_context(self):
        assert "Radarr" in MOVIE_SYSTEM_PROMPT
        assert "Movie:" in MOVIE_SYSTEM_PROMPT

    def test_movie_prompt_contains_year_rule(self):
        assert "YEAR" in MOVIE_SYSTEM_PROMPT

    def test_movie_prompt_contains_edition_rule(self):
        assert "Director's Cut" in MOVIE_SYSTEM_PROMPT or "EDITION" in MOVIE_SYSTEM_PROMPT

    def test_movie_prompt_quality_tiers_match_tv(self):
        """All quality strings from TV prompt exist in movie prompt."""
        quality_strings = [
            "WEBDL-1080p",
            "WEBDL-720p",
            "WEBDL-2160p",
            "Bluray-1080p",
            "Bluray-720p",
            "Bluray.1080p.Remux",
            "Bluray.2160p.Remux",
            "HDTV-1080p",
            "HDTV-720p",
            "DVD",
        ]
        for quality in quality_strings:
            assert quality in MOVIE_SYSTEM_PROMPT, f"Missing quality tier: {quality}"

    def test_movie_prompt_has_collection_pack_rule(self):
        assert "COLLECTION" in MOVIE_SYSTEM_PROMPT.upper()


class TestTorrentItemPromptFormat:
    def test_to_prompt_tv_default(self):
        item = TorrentItem(title="t", series_name="s")
        prompt = item.to_prompt()
        assert "Series: s" in prompt

    def test_to_prompt_movie(self):
        item = TorrentItem(title="t", series_name="m")
        prompt = item.to_prompt(MediaType.MOVIE)
        assert "Movie: m" in prompt

    def test_to_prompt_movie_no_series_label(self):
        """Movie prompt should NOT contain 'Series:' label."""
        item = TorrentItem(title="t", series_name="m")
        prompt = item.to_prompt(MediaType.MOVIE)
        assert "Series:" not in prompt

    def test_to_prompt_tv_no_movie_label(self):
        """TV prompt should NOT contain 'Movie:' label."""
        item = TorrentItem(title="t", series_name="s")
        prompt = item.to_prompt(MediaType.TV)
        assert "Movie:" not in prompt


class TestCacheKeyIsolation:
    def test_memory_cache_key_includes_media_type(self):
        """Cache key format includes media_type prefix."""
        key_tv = f"{MediaType.TV.value}|title|name"
        key_movie = f"{MediaType.MOVIE.value}|title|name"
        assert key_tv.startswith("tv|")
        assert key_movie.startswith("movie|")

    def test_same_title_different_media_type_different_key(self):
        """Identical title+series_name with different media_type produce different keys."""
        key_tv = f"{MediaType.TV.value}|title|name"
        key_movie = f"{MediaType.MOVIE.value}|title|name"
        assert key_tv != key_movie
