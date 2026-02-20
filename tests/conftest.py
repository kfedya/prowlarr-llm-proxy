"""Shared test fixtures."""
from pathlib import Path

import pytest


@pytest.fixture()
def tmp_paths(tmp_path: Path) -> dict[str, Path]:
    """Create temporary directory structure for path tests."""
    downloads = tmp_path / "downloads"
    tv = tmp_path / "tv"
    movies = tmp_path / "movies"

    downloads.mkdir()
    tv.mkdir()
    movies.mkdir()

    return {
        "downloads": downloads,
        "tv": tv,
        "movies": movies,
    }


@pytest.fixture()
def test_settings(monkeypatch: pytest.MonkeyPatch, tmp_paths: dict[str, Path]):
    """Create Settings instance with temporary paths."""
    monkeypatch.setenv("DOWNLOAD_PATH", str(tmp_paths["downloads"]))
    monkeypatch.setenv("SONARR_LIBRARY_PATH", str(tmp_paths["tv"]))
    monkeypatch.setenv("RADARR_LIBRARY_PATH", str(tmp_paths["movies"]))

    from app.config import Settings

    return Settings()
