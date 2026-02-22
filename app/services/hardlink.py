"""Hardlink service for creating filesystem hardlinks from download to library directories."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)


class CrossDeviceError(Exception):
    """Raised when download and library paths are on different block devices."""


ALLOWED_EXTENSIONS: frozenset[str] = frozenset(
    {
        # Video
        ".mkv",
        ".mp4",
        ".avi",
        # Subtitles
        ".srt",
        ".ass",
        ".sub",
        # External audio
        ".mka",
        ".ac3",
        ".dts",
        ".flac",
    }
)


@dataclass
class HardlinkResult:
    """Structured result from a batch hardlink operation."""

    created: list[tuple[Path, Path]] = field(default_factory=list)
    skipped: list[tuple[Path, Path]] = field(default_factory=list)
    errors: list[tuple[Path, Path, str]] = field(default_factory=list)

    @property
    def total(self) -> int:
        """Total number of file pairs processed."""
        return len(self.created) + len(self.skipped) + len(self.errors)

    @property
    def success(self) -> bool:
        """True if no errors occurred."""
        return len(self.errors) == 0


class HardlinkService:
    """Creates hardlinks from download directory to library directories.

    The service receives pre-computed (src, dst) path pairs and creates
    hardlinks. File naming/renaming is handled upstream by the LLM service.

    Args:
        download_path: Root download directory.
        library_paths: Library directories that must be on the same device.
        dry_run: If True, report what would happen without creating links.

    Raises:
        CrossDeviceError: If any library path is on a different block device
            than the download path.
    """

    def __init__(
        self,
        download_path: Path,
        library_paths: list[Path],
        dry_run: bool = False,
    ) -> None:
        self.download_path = download_path
        self.library_paths = library_paths
        self.dry_run = dry_run

        self._validate_same_device()

    def _validate_same_device(self) -> None:
        """Validate all paths are on the same block device."""
        dl_dev = self.download_path.stat().st_dev
        for lib_path in self.library_paths:
            lib_dev = lib_path.stat().st_dev
            if dl_dev != lib_dev:
                raise CrossDeviceError(
                    f"Download path {self.download_path} (dev={dl_dev}) and "
                    f"library path {lib_path} (dev={lib_dev}) are on different devices. "
                    f"Hardlinks require the same filesystem."
                )

    @staticmethod
    def _should_hardlink(src: Path) -> bool:
        """Check if a file should be hardlinked based on its extension.

        Args:
            src: Source file path.

        Returns:
            True if the file extension is in ALLOWED_EXTENSIONS.
        """
        return src.suffix.lower() in ALLOWED_EXTENSIONS

    def create_hardlinks(self, file_pairs: list[tuple[Path, Path]]) -> HardlinkResult:
        """Create hardlinks for a batch of (src, dst) file pairs.

        Args:
            file_pairs: List of (source, destination) path tuples.

        Returns:
            HardlinkResult with created, skipped, and errors lists.
        """
        result = HardlinkResult()

        for src, dst in file_pairs:
            if not self._should_hardlink(src):
                logger.debug("skipped non-media file", src=str(src), ext=src.suffix)
                result.skipped.append((src, dst))
                continue

            if self.dry_run:
                logger.debug("dry-run: would hardlink", src=str(src), dst=str(dst))
                result.created.append((src, dst))
                continue

            try:
                dst.parent.mkdir(parents=True, exist_ok=True)
                os.link(src, dst)
                logger.debug("hardlink created", src=str(src), dst=str(dst))
                result.created.append((src, dst))
            except FileExistsError:
                logger.debug("destination exists, skipping", dst=str(dst))
                result.skipped.append((src, dst))
            except OSError as exc:
                logger.debug("hardlink failed", src=str(src), dst=str(dst), error=str(exc))
                result.errors.append((src, dst, str(exc)))

        logger.info(
            "hardlink batch complete",
            created=len(result.created),
            skipped=len(result.skipped),
            failed=len(result.errors),
        )

        return result
