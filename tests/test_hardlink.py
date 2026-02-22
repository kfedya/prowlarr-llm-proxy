"""Comprehensive tests for HardlinkService."""
from pathlib import Path

import pytest

from app.services.hardlink import CrossDeviceError, HardlinkResult, HardlinkService


class TestHardlinkResult:
    """Tests for HardlinkResult dataclass."""

    def test_total_property(self):
        result = HardlinkResult(
            created=[(Path("a"), Path("b"))],
            skipped=[(Path("c"), Path("d"))],
            errors=[(Path("e"), Path("f"), "err")],
        )
        assert result.total == 3

    def test_success_property_no_errors(self):
        result = HardlinkResult(created=[(Path("a"), Path("b"))], skipped=[], errors=[])
        assert result.success is True

    def test_success_property_with_errors(self):
        result = HardlinkResult(
            created=[], skipped=[], errors=[(Path("a"), Path("b"), "fail")]
        )
        assert result.success is False


class TestCrossDeviceValidation:
    """Tests for cross-device validation at construction time."""

    def test_same_device_passes(self, tmp_path: Path):
        """Paths on same filesystem should not raise."""
        dl = tmp_path / "downloads"
        lib = tmp_path / "library"
        dl.mkdir()
        lib.mkdir()
        svc = HardlinkService(download_path=dl, library_paths=[lib])
        assert svc is not None

    def test_cross_device_raises(self, tmp_path: Path):
        """Paths on different filesystems should raise CrossDeviceError."""
        dl = tmp_path / "downloads"
        dl.mkdir()
        # /proc is always a different filesystem on Linux; /dev on macOS
        cross_path = Path("/proc") if Path("/proc").exists() else Path("/dev")
        with pytest.raises(CrossDeviceError):
            HardlinkService(download_path=dl, library_paths=[cross_path])


class TestCreateHardlinks:
    """Tests for create_hardlinks method."""

    def test_single_file_hardlink(self, tmp_path: Path):
        """Single file hardlink creates link with same inode."""
        dl = tmp_path / "downloads"
        lib = tmp_path / "library"
        dl.mkdir()
        lib.mkdir()

        src = dl / "movie.mkv"
        src.write_text("video content")
        dst = lib / "movie.mkv"

        svc = HardlinkService(download_path=dl, library_paths=[lib])
        result = svc.create_hardlinks([(src, dst)])

        assert len(result.created) == 1
        assert dst.exists()
        assert src.stat().st_ino == dst.stat().st_ino

    def test_inode_verification(self, tmp_path: Path):
        """After hardlink, src and dst share the same inode."""
        dl = tmp_path / "downloads"
        lib = tmp_path / "library"
        dl.mkdir()
        lib.mkdir()

        src = dl / "file.mkv"
        src.write_text("content")
        dst = lib / "file.mkv"

        svc = HardlinkService(download_path=dl, library_paths=[lib])
        svc.create_hardlinks([(src, dst)])

        assert src.stat().st_ino == dst.stat().st_ino
        assert src.stat().st_nlink >= 2

    def test_existing_destination_skipped(self, tmp_path: Path):
        """If destination already exists, it's skipped silently."""
        dl = tmp_path / "downloads"
        lib = tmp_path / "library"
        dl.mkdir()
        lib.mkdir()

        src = dl / "movie.mkv"
        src.write_text("video content")
        dst = lib / "movie.mkv"

        # Pre-create the link
        import os

        os.link(src, dst)

        svc = HardlinkService(download_path=dl, library_paths=[lib])
        result = svc.create_hardlinks([(src, dst)])

        assert len(result.skipped) == 1
        assert len(result.created) == 0

    def test_missing_parent_dirs_created(self, tmp_path: Path):
        """Parent directories are auto-created for destination."""
        dl = tmp_path / "downloads"
        lib = tmp_path / "library"
        dl.mkdir()
        lib.mkdir()

        src = dl / "movie.mkv"
        src.write_text("video content")
        dst = lib / "deep" / "nested" / "movie.mkv"

        svc = HardlinkService(download_path=dl, library_paths=[lib])
        result = svc.create_hardlinks([(src, dst)])

        assert len(result.created) == 1
        assert dst.exists()

    def test_multiple_files_batch(self, tmp_path: Path):
        """Batch of multiple files all get created."""
        dl = tmp_path / "downloads"
        lib = tmp_path / "library"
        dl.mkdir()
        lib.mkdir()

        pairs = []
        for i in range(3):
            src = dl / f"file{i}.mkv"
            src.write_text(f"content {i}")
            dst = lib / f"file{i}.mkv"
            pairs.append((src, dst))

        svc = HardlinkService(download_path=dl, library_paths=[lib])
        result = svc.create_hardlinks(pairs)

        assert len(result.created) == 3

    def test_original_file_untouched(self, tmp_path: Path):
        """Original source file remains readable after hardlink."""
        dl = tmp_path / "downloads"
        lib = tmp_path / "library"
        dl.mkdir()
        lib.mkdir()

        src = dl / "movie.mkv"
        src.write_text("original content")
        dst = lib / "movie.mkv"

        svc = HardlinkService(download_path=dl, library_paths=[lib])
        svc.create_hardlinks([(src, dst)])

        assert src.read_text() == "original content"

    def test_partial_failure_continues(self, tmp_path: Path):
        """Batch continues past individual failures, collecting errors."""
        dl = tmp_path / "downloads"
        lib = tmp_path / "library"
        dl.mkdir()
        lib.mkdir()

        good_src = dl / "good.mkv"
        good_src.write_text("good content")
        good_dst = lib / "good.mkv"

        bad_src = dl / "nonexistent.mkv"  # Does not exist
        bad_dst = lib / "nonexistent.mkv"

        svc = HardlinkService(download_path=dl, library_paths=[lib])
        result = svc.create_hardlinks([(good_src, good_dst), (bad_src, bad_dst)])

        assert len(result.created) == 1
        assert len(result.errors) == 1
        assert result.success is False


class TestDryRun:
    """Tests for dry-run mode."""

    def test_dry_run_no_files_created(self, tmp_path: Path):
        """Dry-run mode does not create any files."""
        dl = tmp_path / "downloads"
        lib = tmp_path / "library"
        dl.mkdir()
        lib.mkdir()

        src = dl / "movie.mkv"
        src.write_text("video content")
        dst = lib / "movie.mkv"

        svc = HardlinkService(download_path=dl, library_paths=[lib], dry_run=True)
        result = svc.create_hardlinks([(src, dst)])

        assert len(result.created) == 1  # Shows what WOULD happen
        assert not dst.exists()  # But no actual file

    def test_dry_run_no_dirs_created(self, tmp_path: Path):
        """Dry-run mode does not create directories."""
        dl = tmp_path / "downloads"
        lib = tmp_path / "library"
        dl.mkdir()
        lib.mkdir()

        src = dl / "movie.mkv"
        src.write_text("video content")
        dst = lib / "deep" / "nested" / "movie.mkv"

        svc = HardlinkService(download_path=dl, library_paths=[lib], dry_run=True)
        svc.create_hardlinks([(src, dst)])

        assert not (lib / "deep").exists()


class TestFileFiltering:
    """Tests for file extension filtering."""

    def test_accepts_mkv(self, tmp_path: Path):
        dl = tmp_path / "downloads"
        lib = tmp_path / "library"
        dl.mkdir()
        lib.mkdir()
        src = dl / "movie.mkv"
        src.write_text("video")
        dst = lib / "movie.mkv"

        svc = HardlinkService(download_path=dl, library_paths=[lib])
        result = svc.create_hardlinks([(src, dst)])
        assert len(result.created) == 1

    def test_accepts_mp4(self, tmp_path: Path):
        dl = tmp_path / "downloads"
        lib = tmp_path / "library"
        dl.mkdir()
        lib.mkdir()
        src = dl / "movie.mp4"
        src.write_text("video")
        dst = lib / "movie.mp4"

        svc = HardlinkService(download_path=dl, library_paths=[lib])
        result = svc.create_hardlinks([(src, dst)])
        assert len(result.created) == 1

    def test_accepts_srt(self, tmp_path: Path):
        dl = tmp_path / "downloads"
        lib = tmp_path / "library"
        dl.mkdir()
        lib.mkdir()
        src = dl / "subs.srt"
        src.write_text("subtitle")
        dst = lib / "subs.srt"

        svc = HardlinkService(download_path=dl, library_paths=[lib])
        result = svc.create_hardlinks([(src, dst)])
        assert len(result.created) == 1

    def test_accepts_mka(self, tmp_path: Path):
        dl = tmp_path / "downloads"
        lib = tmp_path / "library"
        dl.mkdir()
        lib.mkdir()
        src = dl / "audio.mka"
        src.write_text("audio")
        dst = lib / "audio.mka"

        svc = HardlinkService(download_path=dl, library_paths=[lib])
        result = svc.create_hardlinks([(src, dst)])
        assert len(result.created) == 1

    def test_rejects_nfo(self, tmp_path: Path):
        dl = tmp_path / "downloads"
        lib = tmp_path / "library"
        dl.mkdir()
        lib.mkdir()
        src = dl / "info.nfo"
        src.write_text("nfo data")
        dst = lib / "info.nfo"

        svc = HardlinkService(download_path=dl, library_paths=[lib])
        result = svc.create_hardlinks([(src, dst)])
        assert len(result.skipped) == 1
        assert len(result.created) == 0
        assert not dst.exists()

    def test_rejects_txt(self, tmp_path: Path):
        dl = tmp_path / "downloads"
        lib = tmp_path / "library"
        dl.mkdir()
        lib.mkdir()
        src = dl / "readme.txt"
        src.write_text("text")
        dst = lib / "readme.txt"

        svc = HardlinkService(download_path=dl, library_paths=[lib])
        result = svc.create_hardlinks([(src, dst)])
        assert len(result.skipped) == 1
        assert not dst.exists()

    def test_rejects_jpg(self, tmp_path: Path):
        dl = tmp_path / "downloads"
        lib = tmp_path / "library"
        dl.mkdir()
        lib.mkdir()
        src = dl / "cover.jpg"
        src.write_text("image")
        dst = lib / "cover.jpg"

        svc = HardlinkService(download_path=dl, library_paths=[lib])
        result = svc.create_hardlinks([(src, dst)])
        assert len(result.skipped) == 1
        assert not dst.exists()

    def test_mixed_batch_with_filtering(self, tmp_path: Path):
        """2 .mkv + 1 .nfo -> created=2, skipped=1."""
        dl = tmp_path / "downloads"
        lib = tmp_path / "library"
        dl.mkdir()
        lib.mkdir()

        pairs = []
        for name in ["movie1.mkv", "movie2.mkv", "info.nfo"]:
            src = dl / name
            src.write_text("content")
            dst = lib / name
            pairs.append((src, dst))

        svc = HardlinkService(download_path=dl, library_paths=[lib])
        result = svc.create_hardlinks(pairs)

        assert len(result.created) == 2
        assert len(result.skipped) == 1
