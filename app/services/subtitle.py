"""Service for filtering and matching subtitle files."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from app.models.qbittorrent import TorrentFile
    from app.services.llm import LLMService

logger = structlog.get_logger(__name__)


class SubtitleService:
    """Independently testable service for subtitle file operations."""

    SUBTITLE_EXTENSIONS: frozenset[str] = frozenset({
        ".ass", ".srt", ".sub", ".ssa", ".vtt", ".sup",
    })

    def __init__(self, llm_service: LLMService | None = None) -> None:
        self._llm_service = llm_service
        logger.info("SubtitleService initialized", llm_enabled=llm_service is not None)

    def filter_subtitle_files(self, files: list[TorrentFile]) -> list[str]:
        """Extract subtitle file names from a torrent file list."""
        return [
            f.name for f in files
            if Path(f.name).suffix.lower() in self.SUBTITLE_EXTENSIONS
        ]

    async def match_subtitles_to_videos(
        self,
        subtitle_files: list[str],
        video_mappings: dict[str, str],
    ) -> dict[str, str]:
        """Use LLM to match subtitle files to video files.

        Returns dict mapping old subtitle names to new subtitle names.
        Returns empty dict if LLM unavailable or no files to match.
        """
        if not self._llm_service or not subtitle_files or not video_mappings:
            return {}
        return await self._llm_service.normalize_subtitle_names(
            subtitle_files=subtitle_files,
            video_mappings=video_mappings,
        )
