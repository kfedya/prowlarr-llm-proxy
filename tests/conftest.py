"""Shared test fixtures."""
from pathlib import Path

import pytest


@pytest.fixture()
def tmp_paths(tmp_path: Path) -> dict[str, Path]:
    """Create temporary directory structure for path tests."""
    downloads = tmp_path / "downloads"
    hardlinks = tmp_path / "hardlinks"

    downloads.mkdir()
    hardlinks.mkdir()

    return {
        "downloads": downloads,
        "hardlinks": hardlinks,
    }


@pytest.fixture()
def test_settings(monkeypatch: pytest.MonkeyPatch, tmp_paths: dict[str, Path]):
    """Create Settings instance with temporary paths."""
    monkeypatch.setenv("DOWNLOAD_PATH", str(tmp_paths["downloads"]))
    monkeypatch.setenv("HARDLINK_PATH", str(tmp_paths["hardlinks"]))

    from app.config import Settings

    return Settings()
