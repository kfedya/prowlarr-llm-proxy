"""MediaHandlerService: thin orchestrator replacing SonarrHandlerService grab workflow.

Flow: webhook -> lookup mapping -> poll qBit for metadata -> verify files on disk
-> compute hardlink pairs -> create hardlinks -> process subtitles.

No qBittorrent rename API calls. No rescan trigger (files fill in-place).
Rescan deferred per user decision -- hardlinks fill in-place.
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from app.services.hardlink import HardlinkService
    from app.services.llm import LLMService
    from app.services.qbittorrent import QBittorrentService
    from app.services.subtitle import SubtitleService
    from app.services.torrent_mapping import TorrentMappingService

from app.services.torrent_mapping import MediaType

logger = structlog.get_logger(__name__)

# Polling constants
FAST_INTERVAL = 2.0  # seconds between polls during fast phase
SLOW_INTERVAL = 10.0  # seconds between polls during slow phase
FAST_CUTOFF = 30.0  # switch from fast to slow after this many seconds
MAX_TIMEOUT = 600.0  # max total polling time per attempt (10 min)
RETRY_DELAY = 300.0  # delay before retry attempt (5 min)
MAX_ATTEMPTS = 2  # total polling attempts


class MediaHandlerService:
    """Thin orchestrator that replaces SonarrHandlerService.

    Flow: webhook -> lookup mapping -> poll qBit for metadata -> verify files on disk
    -> compute hardlink pairs -> create hardlinks -> process subtitles.

    No qBittorrent rename API calls. No rescan trigger (files fill in-place).
    """

    def __init__(
        self,
        torrent_mapping_service: TorrentMappingService,
        qbittorrent_service: QBittorrentService,
        hardlink_service: HardlinkService | None,
        subtitle_service: SubtitleService,
        llm_service: LLMService | None = None,
        download_path: Path = Path("/downloads"),
        sonarr_library_path: Path | None = None,
        radarr_library_path: Path | None = None,
    ) -> None:
        self._mapping_service = torrent_mapping_service
        self._qb_service = qbittorrent_service
        self._hardlink_service = hardlink_service
        self._subtitle_service = subtitle_service
        self._llm_service = llm_service
        self._download_path = download_path
        self._sonarr_library_path = sonarr_library_path
        self._radarr_library_path = radarr_library_path

        logger.info(
            "MediaHandlerService initialized",
            download_path=str(download_path),
            sonarr_library_path=str(sonarr_library_path),
            radarr_library_path=str(radarr_library_path),
            hardlink_service_available=hardlink_service is not None,
        )

    async def handle_grab_event(
        self,
        release_title: str,
        download_id: str,
        media_type: MediaType,
        series_title: str | None = None,
        movie_title: str | None = None,
        season_number: int | None = None,
        episode_numbers: list[int] | None = None,
        year: int | None = None,
    ) -> None:
        """Handle a grab event from Sonarr or Radarr webhook.

        Orchestrates: mapping lookup -> poll qBit -> hardlink -> subtitles.
        """
        title_label = series_title or movie_title or release_title[:60]
        try:
            # Select library path by media type
            if media_type == MediaType.TV:
                library_base = self._sonarr_library_path
            else:
                library_base = self._radarr_library_path

            if library_base is None:
                logger.error(
                    "No library path configured for media type",
                    media_type=media_type.value,
                )
                return

            logger.info(
                "Processing grab event",
                release_title=release_title[:80],
                download_id=download_id,
                media_type=media_type.value,
                title=title_label,
                library_base=str(library_base),
            )

            # Step 1: Look up torrent mapping
            mapping = await self._mapping_service.get_by_title(release_title)
            if not mapping:
                logger.warning(
                    "No mapping found for release",
                    release_title=release_title[:80],
                    download_id=download_id,
                )
                return

            logger.info(
                "Found torrent mapping",
                original_title=mapping.original_title[:80],
            )

            # Step 2: Poll for torrent files on disk
            files_on_disk = await self._poll_for_files_on_disk(
                download_id, mapping.original_title
            )
            if not files_on_disk:
                logger.error(
                    "Polling timed out, no files found on disk",
                    download_id=download_id,
                    original_title=mapping.original_title[:80],
                )
                return

            logger.info(
                "Files found on disk",
                file_count=len(files_on_disk),
            )

            # Step 3: Compute hardlink pairs
            subfolder = self._make_subfolder_name(
                media_type=media_type,
                title=series_title or movie_title or mapping.series_name or "Unknown",
                season_number=season_number,
                episode_numbers=episode_numbers,
                year=year,
            )
            pairs = self._compute_hardlink_pairs(
                files=files_on_disk,
                hardlink_base=library_base,
                subfolder_name=subfolder,
            )

            logger.info(
                "Computed hardlink pairs",
                pair_count=len(pairs),
                subfolder=subfolder,
            )

            # Step 4: Create hardlinks
            if not self._hardlink_service:
                logger.error("HardlinkService not available, cannot create hardlinks")
                return

            # Movies hardlink ALL files (no extension filter, no subtitle processing)
            use_filter = media_type == MediaType.TV
            result = self._hardlink_service.create_hardlinks(
                pairs, filter_extensions=use_filter
            )
            if result.errors:
                logger.error(
                    "Hardlink creation failed, aborting",
                    errors=len(result.errors),
                    created=len(result.created),
                    first_error=result.errors[0][2] if result.errors else "",
                )
                # Per user decision: no fallback, abort on error
                return

            logger.info(
                "Hardlinks created",
                created=len(result.created),
                skipped=len(result.skipped),
            )

            # Step 5: Process subtitles (TV only -- movies hardlink all files as-is)
            if media_type == MediaType.TV:
                await self._process_subtitles(
                    download_id=download_id,
                    subfolder=subfolder,
                    library_base=library_base,
                )

            # Rescan deferred per user decision -- hardlinks fill in-place.
            logger.info(
                "Grab event processing completed",
                title=title_label,
                media_type=media_type.value,
                hardlinks_created=len(result.created),
                subfolder=subfolder,
            )

        except Exception as e:
            logger.error(
                "Failed to handle grab event",
                error=str(e),
                release_title=release_title[:80],
                download_id=download_id,
            )

    async def _poll_for_files_on_disk(
        self,
        download_id: str,
        original_title: str,
    ) -> list[Path]:
        """Poll qBittorrent for torrent files and verify they exist on disk.

        Uses fast-then-backoff strategy:
        - 2s intervals for 30s, then 10s intervals up to 10 min total
        - 2 attempts (retry once after 5-min delay)
        - qBittorrent API errors count toward timeout

        Returns list of verified file paths on disk, or empty list on timeout.
        """
        for attempt in range(MAX_ATTEMPTS):
            if attempt > 0:
                logger.info(
                    "Retrying file polling after delay",
                    attempt=attempt + 1,
                    delay=RETRY_DELAY,
                )
                await asyncio.sleep(RETRY_DELAY)

            files = await self._poll_attempt(download_id, original_title)
            if files:
                return files

        logger.error(
            "All polling attempts exhausted",
            download_id=download_id,
            attempts=MAX_ATTEMPTS,
        )
        return []

    async def _poll_attempt(
        self,
        download_id: str,
        original_title: str,
    ) -> list[Path]:
        """Single polling attempt with fast-then-backoff intervals."""
        elapsed = 0.0

        while elapsed < MAX_TIMEOUT:
            interval = FAST_INTERVAL if elapsed < FAST_CUTOFF else SLOW_INTERVAL

            try:
                async with self._qb_service:
                    # Get torrent info to check state and save_path
                    torrent = await self._qb_service.get_torrent_by_hash(download_id)
                    if not torrent:
                        logger.debug(
                            "Torrent not found yet",
                            download_id=download_id,
                            elapsed=elapsed,
                        )
                        await asyncio.sleep(interval)
                        elapsed += interval
                        continue

                    # Skip if still downloading metadata
                    if torrent.state == "metaDL":
                        logger.debug(
                            "Torrent still downloading metadata",
                            download_id=download_id,
                            state=torrent.state,
                            elapsed=elapsed,
                        )
                        await asyncio.sleep(interval)
                        elapsed += interval
                        continue

                    # Get file list
                    file_list = await self._qb_service.get_torrent_files(download_id)
                    if not file_list.files:
                        logger.debug(
                            "No files in torrent yet",
                            download_id=download_id,
                            elapsed=elapsed,
                        )
                        await asyncio.sleep(interval)
                        elapsed += interval
                        continue

                    # Check if files exist on disk
                    # Per research pitfall #4: file.name includes torrent folder prefix
                    # for multi-file torrents, so use save_path / file.name
                    save_path = Path(torrent.save_path)
                    verified_files: list[Path] = []

                    for f in file_list.files:
                        file_path = save_path / f.name
                        if file_path.exists():
                            verified_files.append(file_path)

                    if verified_files:
                        logger.info(
                            "Files verified on disk",
                            count=len(verified_files),
                            total=len(file_list.files),
                            elapsed=elapsed,
                        )
                        return verified_files

            except Exception as e:
                # API errors count toward timeout
                logger.warning(
                    "qBittorrent API error during polling",
                    error=str(e),
                    elapsed=elapsed,
                )

            await asyncio.sleep(interval)
            elapsed += interval

        logger.warning(
            "Polling attempt timed out",
            download_id=download_id,
            elapsed=elapsed,
        )
        return []

    @staticmethod
    def _compute_hardlink_pairs(
        files: list[Path],
        hardlink_base: Path,
        subfolder_name: str,
    ) -> list[tuple[Path, Path]]:
        """Compute (src, dst) hardlink pairs.

        For each source file, the destination strips directory prefix
        and places the file in hardlink_base/subfolder_name/.
        """
        pairs: list[tuple[Path, Path]] = []
        for src in files:
            dst = hardlink_base / subfolder_name / src.name
            pairs.append((src, dst))
        return pairs

    @staticmethod
    def _sanitize_title(title: str) -> str:
        """Sanitize a title for use as a filesystem path component.

        Replaces colons with ' -', slashes with '-', removes *?<>|",
        strips trailing dots and spaces.
        """
        safe = title.replace(":", " -")
        safe = re.sub(r"[/\\]", "-", safe)
        safe = re.sub(r'[*?<>|"]', "", safe)
        safe = safe.rstrip(". ")
        return safe

    @staticmethod
    def _make_subfolder_name(
        media_type: MediaType,
        title: str,
        season_number: int | None,
        episode_numbers: list[int] | None,
        year: int | None = None,
    ) -> str:
        """Build a sanitized subfolder path for hardlink destinations.

        TV: "{Title}/Season {NN}" (nested path for Sonarr library structure)
        Movie: "{Title} ({Year})" or just "{Title}"
        """
        safe_title = MediaHandlerService._sanitize_title(title)

        if media_type == MediaType.TV:
            if season_number is None:
                return safe_title
            return f"{safe_title}/Season {season_number:02d}"
        else:
            # Movie
            if year:
                return f"{safe_title} ({year})"
            return safe_title

    async def _process_subtitles(
        self,
        download_id: str,
        subfolder: str,
        library_base: Path,
    ) -> None:
        """Find subtitle files in the torrent and create hardlinks for them.

        Only called for TV media type. Movies hardlink all files as-is.

        Args:
            download_id: Torrent hash / download ID.
            subfolder: Subfolder path relative to library base.
            library_base: Library root path (e.g. sonarr_library_path).
        """
        try:
            async with self._qb_service:
                torrent = await self._qb_service.get_torrent_by_hash(download_id)
                if not torrent:
                    return

                file_list = await self._qb_service.get_torrent_files(download_id)
                if not file_list.files:
                    return

                # Filter subtitle files
                subtitle_names = self._subtitle_service.filter_subtitle_files(
                    file_list.files
                )
                if not subtitle_names:
                    logger.debug("No subtitle files found in torrent")
                    return

                logger.info(
                    "Found subtitle files",
                    count=len(subtitle_names),
                )

                # Build subtitle hardlink pairs directly
                # Subtitles are hardlinked to the same subfolder as video files
                save_path = Path(torrent.save_path)
                subtitle_pairs: list[tuple[Path, Path]] = []

                for sub_name in subtitle_names:
                    src = save_path / sub_name
                    if src.exists():
                        dst = library_base / subfolder / Path(sub_name).name
                        subtitle_pairs.append((src, dst))

                if subtitle_pairs and self._hardlink_service:
                    result = self._hardlink_service.create_hardlinks(subtitle_pairs)
                    logger.info(
                        "Subtitle hardlinks created",
                        created=len(result.created),
                        skipped=len(result.skipped),
                        errors=len(result.errors),
                    )

        except Exception as e:
            logger.warning(
                "Subtitle processing failed (non-fatal)",
                error=str(e),
            )
