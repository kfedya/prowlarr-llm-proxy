"""Unit tests for RadarrGrabWebhook model."""

from app.models.radarr import RadarrGrabWebhook


class TestRadarrGrabWebhookModel:
    """Tests for RadarrGrabWebhook Pydantic model."""

    def test_valid_grab_payload(self):
        """Full Grab payload with all fields populated parses correctly."""
        data = {
            "eventType": "Grab",
            "instanceName": "Radarr",
            "applicationUrl": "http://radarr:7878",
            "movie": {
                "id": 1,
                "title": "Cool Movie",
                "year": 2024,
                "filePath": "/movies/Cool Movie (2024)/Cool.Movie.2024.mkv",
                "releaseDate": "2024-06-15",
                "folderPath": "/movies/Cool Movie (2024)",
                "tmdbId": 12345,
                "imdbId": "tt1234567",
                "overview": "A cool movie about stuff.",
            },
            "remoteMovie": {
                "tmdbId": 12345,
                "imdbId": "tt1234567",
                "title": "Cool Movie",
                "year": 2024,
            },
            "release": {
                "quality": "Bluray-1080p",
                "qualityVersion": 1,
                "releaseGroup": "SPARKS",
                "releaseTitle": "Cool.Movie.2024.1080p.BluRay.x264-SPARKS",
                "indexer": "TorrentLeech",
                "size": 8589934592,
                "customFormatScore": 10,
                "customFormats": ["Remux"],
                "languages": [{"id": 1, "name": "English"}],
                "indexerFlags": [],
            },
            "downloadClient": "qBittorrent",
            "downloadClientType": "qBittorrent",
            "downloadId": "ABCDEF1234567890",
            "customFormatInfo": {"customFormats": [], "customFormatScore": 0},
        }
        payload = RadarrGrabWebhook.model_validate(data)
        assert payload.eventType == "Grab"
        assert payload.movie.title == "Cool Movie"
        assert payload.movie.year == 2024
        assert payload.release.releaseTitle == "Cool.Movie.2024.1080p.BluRay.x264-SPARKS"
        assert payload.downloadId == "ABCDEF1234567890"

    def test_minimal_grab_payload(self):
        """Minimal Grab payload with only required fields."""
        data = {
            "eventType": "Grab",
            "movie": {"id": 1, "title": "Movie"},
            "release": {
                "quality": "HDTV-720p",
                "releaseTitle": "Movie.2024.720p.HDTV",
            },
        }
        payload = RadarrGrabWebhook.model_validate(data)
        assert payload.eventType == "Grab"
        assert payload.movie.title == "Movie"
        assert payload.release.releaseTitle == "Movie.2024.720p.HDTV"
        assert payload.downloadId == ""
        assert payload.instanceName == ""

    def test_test_event_payload(self):
        """Test event payload has no movie or release."""
        data = {"eventType": "Test"}
        payload = RadarrGrabWebhook.model_validate(data)
        assert payload.eventType == "Test"
        assert payload.movie is None
        assert payload.release is None

    def test_movie_year_defaults_to_zero(self):
        """When year is missing from movie, it defaults to 0."""
        data = {
            "eventType": "Grab",
            "movie": {"id": 1, "title": "Unknown Year Movie"},
        }
        payload = RadarrGrabWebhook.model_validate(data)
        assert payload.movie.year == 0
