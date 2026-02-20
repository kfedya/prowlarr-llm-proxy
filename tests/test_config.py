"""Tests for config loading and path validation."""
from pathlib import Path

import pytest


class TestDefaultSettings:
    def test_default_settings_load(self):
        """Settings() loads without error with defaults."""
        from app.config import Settings

        s = Settings()
        assert s.app_name == "prowlarr-llm-proxy"

    def test_download_path_default(self):
        from app.config import Settings

        s = Settings()
        assert s.download_path == Path("/downloads")

    def test_library_paths_default_none(self):
        from app.config import Settings

        s = Settings()
        assert s.sonarr_library_path is None
        assert s.radarr_library_path is None


class TestPathValidation:
    def test_path_validation_with_valid_paths(self, test_settings):
        """Settings with existing tmp_path dirs validates OK."""
        assert test_settings.download_path.exists()
        assert test_settings.sonarr_library_path.exists()
        assert test_settings.radarr_library_path.exists()

    def test_path_validation_rejects_nonexistent_download(self, monkeypatch):
        """Non-default DOWNLOAD_PATH that doesn't exist raises ValueError."""
        monkeypatch.setenv("DOWNLOAD_PATH", "/nonexistent/path/xyz")

        from app.config import Settings

        with pytest.raises(ValueError, match="DOWNLOAD_PATH does not exist"):
            Settings()

    def test_path_validation_rejects_nonexistent_sonarr_library(self, monkeypatch):
        """SONARR_LIBRARY_PATH that doesn't exist raises ValueError."""
        monkeypatch.setenv("SONARR_LIBRARY_PATH", "/nonexistent/sonarr/path")

        from app.config import Settings

        with pytest.raises(ValueError, match="SONARR_LIBRARY_PATH does not exist"):
            Settings()

    def test_optional_library_paths_not_validated_when_none(self):
        """When library paths are None, no validation error."""
        from app.config import Settings

        # Default has None for library paths -- should not raise
        s = Settings()
        assert s.sonarr_library_path is None
        assert s.radarr_library_path is None
