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

    def test_hardlink_path_default_none(self):
        from app.config import Settings

        s = Settings()
        assert s.hardlink_path is None

    def test_no_library_path_fields(self):
        """sonarr_library_path and radarr_library_path no longer exist."""
        from app.config import Settings

        s = Settings()
        assert not hasattr(s, "sonarr_library_path")
        assert not hasattr(s, "radarr_library_path")


class TestPathValidation:
    def test_path_validation_with_valid_paths(self, test_settings):
        """Settings with existing tmp_path dirs validates OK."""
        assert test_settings.download_path.exists()
        assert test_settings.hardlink_path is not None
        assert test_settings.hardlink_path.exists()

    def test_path_validation_rejects_nonexistent_download(self, monkeypatch):
        """Non-default DOWNLOAD_PATH that doesn't exist raises ValueError."""
        monkeypatch.setenv("DOWNLOAD_PATH", "/nonexistent/path/xyz")

        from app.config import Settings

        with pytest.raises(ValueError, match="DOWNLOAD_PATH does not exist"):
            Settings()

    def test_path_validation_rejects_nonexistent_hardlink_path(self, monkeypatch):
        """HARDLINK_PATH that doesn't exist raises ValueError."""
        monkeypatch.setenv("HARDLINK_PATH", "/nonexistent/hardlinks/path")

        from app.config import Settings

        with pytest.raises(ValueError, match="HARDLINK_PATH does not exist"):
            Settings()

    def test_optional_hardlink_path_not_validated_when_none(self):
        """When hardlink_path is None (and use_new_handler=False), no validation error."""
        from app.config import Settings

        # Default has None for hardlink_path and use_new_handler=False -- should not raise
        s = Settings()
        assert s.hardlink_path is None
