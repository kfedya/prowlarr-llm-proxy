"""Service for filtering and matching subtitle files."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from app.models.qbittorrent import TorrentFile
    from app.services.llm import LLMService

logger = structlog.get_logger(__name__)

# Maps common subtitle language identifiers to ISO 639-2 (3-letter) codes.
# Supports 2-letter codes, 3-letter codes (passthrough), and full language names.
LANGUAGE_MAP: dict[str, str] = {
    # 2-letter codes (ISO 639-1 -> ISO 639-2)
    "en": "eng", "ru": "rus", "fr": "fre", "de": "ger", "es": "spa",
    "it": "ita", "pt": "por", "nl": "dut", "pl": "pol", "ja": "jpn",
    "ko": "kor", "zh": "chi", "ar": "ara", "he": "heb", "sv": "swe",
    "no": "nor", "da": "dan", "fi": "fin", "cs": "cze", "hu": "hun",
    "ro": "rum", "bg": "bul", "hr": "hrv", "uk": "ukr", "tr": "tur",
    "th": "tha", "vi": "vie", "id": "ind",
    # 3-letter codes (passthrough)
    "eng": "eng", "rus": "rus", "fre": "fre", "ger": "ger", "spa": "spa",
    "ita": "ita", "por": "por", "dut": "dut", "pol": "pol", "jpn": "jpn",
    "kor": "kor", "chi": "chi", "ara": "ara", "heb": "heb", "swe": "swe",
    "nor": "nor",
    # Full language names
    "english": "eng", "russian": "rus", "french": "fre", "german": "ger",
    "spanish": "spa", "italian": "ita", "portuguese": "por", "dutch": "dut",
    "polish": "pol", "japanese": "jpn", "korean": "kor", "chinese": "chi",
    "arabic": "ara", "hebrew": "heb", "swedish": "swe",
}


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

    @staticmethod
    def detect_language_from_filename(filename: str) -> str | None:
        """Detect subtitle language from filename pattern.

        Supports patterns like "video.en.srt", "video.eng.srt", "video.english.srt".
        Returns 3-letter ISO 639-2 code, or None if language cannot be determined.
        """
        path = Path(filename)
        # Get stem without subtitle extension, e.g. "video.en" from "video.en.srt"
        stem = path.stem
        # Split on last dot to extract potential language part
        if "." not in stem:
            return None
        lang_part = stem.rsplit(".", maxsplit=1)[1].lower()
        return LANGUAGE_MAP.get(lang_part)

    @staticmethod
    def rename_subtitle_with_language(original_name: str, video_name: str) -> str:
        """Rename a subtitle file with standardized language suffix.

        If language is detected from the original subtitle filename, returns
        "{video_stem}.{lang_code}{sub_extension}" (e.g. "Show S01E01.eng.srt").
        If no language detected, returns the original subtitle filename unchanged.

        Args:
            original_name: Original subtitle filename (e.g. "video.en.srt").
            video_name: Corresponding video filename (e.g. "Show S01E01.mkv").

        Returns:
            Renamed subtitle filename, or original if language unknown.
        """
        lang_code = SubtitleService.detect_language_from_filename(original_name)
        if lang_code is None:
            return original_name

        sub_ext = Path(original_name).suffix  # e.g. ".srt", ".ass"
        video_stem = Path(video_name).stem  # e.g. "Show S01E01"
        return f"{video_stem}.{lang_code}{sub_ext}"

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
