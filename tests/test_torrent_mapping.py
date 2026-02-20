"""Tests for TorrentMapping schema extensions."""
import json

from app.services.torrent_mapping import MediaType, TorrentMapping


class TestMediaTypeEnum:
    def test_media_type_enum_values(self):
        assert MediaType.TV.value == "tv"
        assert MediaType.MOVIE.value == "movie"

    def test_media_type_is_str(self):
        """MediaType values behave as strings for JSON serialization."""
        assert isinstance(MediaType.TV, str)
        assert MediaType.TV == "tv"


class TestTorrentMappingDefaults:
    def test_torrent_mapping_defaults(self):
        m = TorrentMapping(original_title="test", normalized_title="test")
        assert m.media_type == MediaType.TV
        assert m.file_count == 0

    def test_backward_compatible_deserialization(self):
        """Old Redis data without media_type/file_count deserializes with defaults."""
        old_json = json.dumps({
            "original_title": "Some.Show.S01E01",
            "normalized_title": "Some Show S01E01",
            "created_at": "2026-01-01T00:00:00",
        })
        m = TorrentMapping.model_validate_json(old_json)
        assert m.media_type == MediaType.TV
        assert m.file_count == 0
        assert m.original_title == "Some.Show.S01E01"


class TestMediaTypeSerialization:
    def test_media_type_serialization(self):
        """model_dump_json() produces 'tv'/'movie' strings, not 'MediaType.TV'."""
        m = TorrentMapping(original_title="t", normalized_title="t", media_type=MediaType.TV)
        data = json.loads(m.model_dump_json())
        assert data["media_type"] == "tv"

    def test_torrent_mapping_with_movie_type(self):
        """Explicit MOVIE type serializes and deserializes correctly."""
        m = TorrentMapping(
            original_title="Movie.2025",
            normalized_title="Movie 2025",
            media_type=MediaType.MOVIE,
            file_count=3,
        )
        dumped = m.model_dump_json()
        data = json.loads(dumped)
        assert data["media_type"] == "movie"
        assert data["file_count"] == 3

        # Round-trip
        m2 = TorrentMapping.model_validate_json(dumped)
        assert m2.media_type == MediaType.MOVIE
        assert m2.file_count == 3
