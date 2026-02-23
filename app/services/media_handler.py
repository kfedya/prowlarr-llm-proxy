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

from app.services.subtitle import SubtitleService
from app.services.torrent_mapping import MediaType

logger = structlog.get_logger(__name__)

# Video file extensions for finding the primary video in a torrent
VIDEO_EXTENSIONS: frozenset[str] = frozenset({".mkv", ".mp4", ".avi", ".wmv", ".flv", ".mov"})

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

    TV files: LLM-normalized names, placed flat in hardlink_path/{Series Name}/.
    Movie files: torrent-relative structure preserved under hardlink_path/{Movie (Year)}/.

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
        hardlink_path: Path | None = None,
    ) -> None:
        self._mapping_service = torrent_mapping_service
        self._qb_service = qbittorrent_service
        self._hardlink_service = hardlink_service
        self._subtitle_service = subtitle_service
        self._llm_service = llm_service
        self._download_path = download_path
        self._hardlink_path = hardlink_path

        logger.info(
            "MediaHandlerService initialized",
            download_path=str(download_path),
            hardlink_path=str(hardlink_path),
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
            if self._hardlink_path is None:
                logger.error("No hardlink_path configured, cannot create hardlinks")
                return

            hardlink_base = self._hardlink_path

            logger.info(
                "Processing grab event",
                release_title=release_title[:80],
                download_id=download_id,
                media_type=media_type.value,
                title=title_label,
                hardlink_base=str(hardlink_base),
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

            # Step 2: Poll for torrent files on disk (returns save_path + files)
            save_path, files_on_disk = await self._poll_for_files_on_disk(
                download_id, mapping.original_title
            )
            if not files_on_disk or save_path is None:
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

            if not self._hardlink_service:
                logger.error("HardlinkService not available, cannot create hardlinks")
                return

            # Step 3: Split into TV or movie flow
            if media_type == MediaType.TV:
                await self._handle_tv_grab(
                    files_on_disk=files_on_disk,
                    save_path=save_path,
                    series_title=series_title or mapping.series_name or "Unknown",
                    season_number=season_number,
                    episode_numbers=episode_numbers,
                    hardlink_base=hardlink_base,
                    download_id=download_id,
                )
            else:
                await self._handle_movie_grab(
                    files_on_disk=files_on_disk,
                    save_path=save_path,
                    movie_title=movie_title or "Unknown",
                    year=year,
                    hardlink_base=hardlink_base,
                )

            logger.info(
                "Grab event processing completed",
                title=title_label,
                media_type=media_type.value,
            )

        except Exception as e:
            logger.error(
                "Failed to handle grab event",
                error=str(e),
                release_title=release_title[:80],
                download_id=download_id,
            )

    async def _handle_tv_grab(
        self,
        files_on_disk: list[Path],
        save_path: Path,
        series_title: str,
        season_number: int | None,
        episode_numbers: list[int] | None,
        hardlink_base: Path,
        download_id: str,
    ) -> None:
        """Handle TV grab: LLM-normalize file names, hardlink flat into {series}/."""
        # 1. Get video files only
        video_files = [f for f in files_on_disk if f.suffix.lower() in VIDEO_EXTENSIONS]
        video_names = [f.name for f in video_files]

        # 2. LLM normalize video file names
        name_mapping: dict[str, str] = {}
        if self._llm_service and video_names:
            try:
                name_mapping = await self._llm_service.normalize_file_names(
                    file_names=video_names,
                    series_name=series_title,
                    season_number=season_number or 1,
                    episodes=episode_numbers,
                )
                logger.info("File names normalized", count=len(name_mapping))
            except Exception as e:
                logger.warning("LLM normalization failed, using original names", error=str(e))

        # 3. Compute TV hardlink pairs (flat, LLM-renamed)
        pairs = self._compute_tv_hardlink_pairs(
            video_files=video_files,
            name_mapping=name_mapping,
            series_title=series_title,
            hardlink_base=hardlink_base,
        )

        logger.info("Computed TV hardlink pairs", pair_count=len(pairs))

        # 4. Create hardlinks (TV: extension filter applied)
        result = self._hardlink_service.create_hardlinks(pairs, filter_extensions=False)
        if result.errors:
            logger.error("TV hardlink creation failed", errors=len(result.errors))
            return

        logger.info("TV hardlinks created", created=len(result.created))

        # 5. Process subtitles with LLM normalization
        await self._process_subtitles(
            download_id=download_id,
            save_path=save_path,
            video_mappings=name_mapping,
            series_title=series_title,
            hardlink_base=hardlink_base,
        )

    async def _handle_movie_grab(
        self,
        files_on_disk: list[Path],
        save_path: Path,
        movie_title: str,
        year: int | None,
        hardlink_base: Path,
    ) -> None:
        """Handle movie grab: preserve torrent-relative structure under {Movie (Year)}/."""
        pairs = self._compute_movie_hardlink_pairs(
            files_on_disk=files_on_disk,
            save_path=save_path,
            movie_title=movie_title,
            year=year,
            hardlink_base=hardlink_base,
        )

        logger.info("Computed movie hardlink pairs", pair_count=len(pairs))

        # Movies hardlink ALL files (no extension filter)
        result = self._hardlink_service.create_hardlinks(pairs, filter_extensions=False)
        if result.errors:
            logger.error("Movie hardlink creation failed", errors=len(result.errors))
            return

        logger.info("Movie hardlinks created", created=len(result.created))

    async def _poll_for_files_on_disk(
        self,
        download_id: str,
        original_title: str,
    ) -> tuple[Path | None, list[Path]]:
        """Poll qBittorrent for torrent files and verify they exist on disk.

        Uses fast-then-backoff strategy:
        - 2s intervals for 30s, then 10s intervals up to 10 min total
        - 2 attempts (retry once after 5-min delay)
        - qBittorrent API errors count toward timeout

        Returns (save_path, list of verified file paths on disk), or (None, []) on timeout.
        """
        for attempt in range(MAX_ATTEMPTS):
            if attempt > 0:
                logger.info(
                    "Retrying file polling after delay",
                    attempt=attempt + 1,
                    delay=RETRY_DELAY,
                )
                await asyncio.sleep(RETRY_DELAY)

            result = await self._poll_attempt(download_id, original_title)
            if result[1]:  # files found
                return result

        logger.error(
            "All polling attempts exhausted",
            download_id=download_id,
            attempts=MAX_ATTEMPTS,
        )
        return None, []

    async def _poll_attempt(
        self,
        download_id: str,
        original_title: str,
    ) -> tuple[Path | None, list[Path]]:
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
                        return save_path, verified_files

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
        return None, []

    @staticmethod
    def _compute_tv_hardlink_pairs(
        video_files: list[Path],
        name_mapping: dict[str, str],
        series_title: str,
        hardlink_base: Path,
    ) -> list[tuple[Path, Path]]:
        """Compute (src, dst) hardlink pairs for TV files.

        Files are placed flat in hardlink_base/{Series Name}/ with LLM-normalized names.
        Falls back to original name if LLM mapping not available.
        """
        safe_series = MediaHandlerService._sanitize_title(series_title)
        pairs = []
        for src in video_files:
            dst_name = name_mapping.get(src.name, src.name)
            dst = hardlink_base / safe_series / dst_name
            pairs.append((src, dst))
        return pairs

    @staticmethod
    def _compute_movie_hardlink_pairs(
        files_on_disk: list[Path],
        save_path: Path,
        movie_title: str,
        year: int | None,
        hardlink_base: Path,
    ) -> list[tuple[Path, Path]]:
        """Compute (src, dst) hardlink pairs for movie files.

        Preserves torrent-relative path structure under hardlink_base/{Movie (Year)}/.
        """
        safe_title = MediaHandlerService._sanitize_title(movie_title)
        folder = f"{safe_title} ({year})" if year else safe_title

        pairs = []
        for src in files_on_disk:
            try:
                relative = src.relative_to(save_path)
            except ValueError:
                relative = Path(src.name)
            dst = hardlink_base / folder / relative
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

    async def _process_subtitles(
        self,
        download_id: str,
        save_path: Path,
        video_mappings: dict[str, str],
        series_title: str,
        hardlink_base: Path,
    ) -> None:
        """Find subtitle files in the torrent and create hardlinks for them.

        Only called for TV media type. Movies hardlink all files as-is.

        Args:
            download_id: Torrent hash / download ID.
            save_path: Torrent save path (root of torrent files).
            video_mappings: LLM mapping of old_video_name -> new_video_name.
            series_title: Series title for destination directory.
            hardlink_base: Hardlink staging root path.
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

                # Use LLM to match subtitles to video files with normalization
                subtitle_mappings: dict[str, str] = {}
                if video_mappings:
                    try:
                        subtitle_mappings = await self._subtitle_service.match_subtitles_to_videos(
                            subtitle_files=subtitle_names,
                            video_mappings=video_mappings,
                        )
                    except Exception as e:
                        logger.warning("Subtitle LLM matching failed, using original names", error=str(e))

                # Build subtitle hardlink pairs
                safe_series = MediaHandlerService._sanitize_title(series_title)
                subtitle_pairs: list[tuple[Path, Path]] = []

                for sub_name in subtitle_names:
                    src = save_path / sub_name
                    if src.exists():
                        sub_basename = Path(sub_name).name
                        new_name = subtitle_mappings.get(sub_basename, sub_basename)
                        dst = hardlink_base / safe_series / new_name
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
