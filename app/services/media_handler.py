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
FAST_INTERVAL = 2.0   # seconds between polls: 0–30s
SLOW_INTERVAL = 10.0  # seconds between polls: 30s–10min
VERY_SLOW_INTERVAL = 60.0  # seconds between polls: 10min+
FAST_CUTOFF = 30.0    # switch fast→slow after this many seconds
SLOW_CUTOFF = 600.0   # switch slow→very_slow after this many seconds
MAX_TIMEOUT = 259200.0  # max total polling time: 3 days

# qBittorrent states that indicate download is fully complete (all files on disk)
COMPLETED_STATES: frozenset[str] = frozenset({
    "uploading", "stalledUP", "checkingUP", "pausedUP", "queuedUP", "forcedUP",
})


class MediaHandlerService:
    """Thin orchestrator that replaces SonarrHandlerService.

    Flow: webhook -> lookup mapping -> poll qBit for metadata -> verify files on disk
    -> compute hardlink pairs -> create hardlinks -> process subtitles.

    TV files: LLM-normalized names, placed flat in hardlink_path/{torrent.name}/.
    Movie files: torrent-relative structure preserved under hardlink_path/{torrent.name}/ (multi-file).
    Single-file movies: placed flat in hardlink_path/{filename} (no wrapper folder).

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

        Creates hardlinks incrementally as torrent files appear on disk.
        Continues polling until torrent is complete (all files hardlinked) or timeout.
        """
        title_label = series_title or movie_title or release_title[:60]
        try:
            if self._hardlink_path is None:
                logger.error("No hardlink_path configured, cannot create hardlinks")
                return
            if not self._hardlink_service:
                logger.error("HardlinkService not available, cannot create hardlinks")
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

            logger.info("Found torrent mapping", original_title=mapping.original_title[:80])

            resolved_series = series_title or mapping.series_name or "Unknown"
            resolved_movie = movie_title or "Unknown"

            # Step 2: Incremental polling loop — hardlink files as they appear on disk
            hardlinked: set[Path] = set()
            hardlinked_subs: set[str] = set()  # subtitle files already hardlinked (torrent-relative paths)
            all_video_mappings: dict[str, str] = {}  # accumulated for subtitle processing
            save_path: Path | None = None
            torrent_name: str | None = None
            elapsed = 0.0

            while elapsed < MAX_TIMEOUT:
                interval = (
                    FAST_INTERVAL if elapsed < FAST_CUTOFF
                    else SLOW_INTERVAL if elapsed < SLOW_CUTOFF
                    else VERY_SLOW_INTERVAL
                )

                try:
                    async with self._qb_service:
                        torrent = await self._qb_service.get_torrent_by_hash(download_id)
                        if not torrent:
                            logger.debug("Torrent not found yet", elapsed=elapsed)
                            await asyncio.sleep(interval)
                            elapsed += interval
                            continue

                        if torrent.state == "metaDL":
                            logger.debug("Torrent downloading metadata", elapsed=elapsed)
                            await asyncio.sleep(interval)
                            elapsed += interval
                            continue

                        save_path = Path(torrent.save_path)
                        torrent_name = torrent.name
                        torrent_done = torrent.state in COMPLETED_STATES

                        file_list = await self._qb_service.get_torrent_files(download_id)
                        if not file_list.files:
                            await asyncio.sleep(interval)
                            elapsed += interval
                            continue

                        total_expected = len(file_list.files)

                        # Find files on disk that haven't been hardlinked yet
                        new_files = [
                            save_path / f.name
                            for f in file_list.files
                            if (save_path / f.name).exists()
                            and (save_path / f.name) not in hardlinked
                        ]

                        if new_files:
                            logger.info(
                                "New files on disk",
                                new=len(new_files),
                                total_done=len(hardlinked) + len(new_files),
                                total_expected=total_expected,
                                elapsed=elapsed,
                            )
                            if media_type == MediaType.TV:
                                batch_mappings = await self._handle_tv_grab(
                                    files_on_disk=new_files,
                                    save_path=save_path,
                                    series_title=resolved_series,
                                    season_number=season_number,
                                    episode_numbers=episode_numbers,
                                    hardlink_base=hardlink_base,
                                    download_id=download_id,
                                    torrent_name=torrent_name,
                                )
                                all_video_mappings.update(batch_mappings)
                                # Process subtitles incrementally alongside videos
                                await self._process_subtitles_incremental(
                                    download_id=download_id,
                                    save_path=save_path,
                                    video_mappings=all_video_mappings,
                                    torrent_name=torrent_name,
                                    hardlink_base=hardlink_base,
                                    already_hardlinked_subs=hardlinked_subs,
                                )
                            else:
                                await self._handle_movie_grab(
                                    files_on_disk=new_files,
                                    save_path=save_path,
                                    movie_title=resolved_movie,
                                    year=year,
                                    hardlink_base=hardlink_base,
                                    total_files=total_expected,
                                    torrent_name=torrent_name,
                                )
                            hardlinked.update(new_files)

                        if torrent_done and len(hardlinked) >= total_expected:
                            logger.info(
                                "All files hardlinked, torrent complete",
                                total=len(hardlinked),
                                title=title_label,
                            )
                            break

                        if torrent_done and not new_files:
                            # Torrent done but no new files this poll — check again once more
                            logger.info(
                                "Torrent complete",
                                hardlinked=len(hardlinked),
                                expected=total_expected,
                            )
                            break

                except Exception as e:
                    logger.warning("qBittorrent poll error", error=str(e), elapsed=elapsed)

                await asyncio.sleep(interval)
                elapsed += interval

            if not hardlinked:
                logger.error(
                    "Polling timed out, no files hardlinked",
                    download_id=download_id,
                    elapsed=elapsed,
                )
                return

            logger.info(
                "Grab event processing completed",
                title=title_label,
                media_type=media_type.value,
                total_hardlinked=len(hardlinked),
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
        torrent_name: str,
    ) -> dict[str, str]:
        """Handle TV grab: LLM-normalize file names, hardlink flat into {torrent_name}/.

        Returns the name_mapping (old_name -> new_name) for subtitle accumulation.
        """
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

        # 3. Compute TV hardlink pairs (flat, LLM-renamed, torrent_name subfolder)
        pairs = self._compute_tv_hardlink_pairs(
            video_files=video_files,
            name_mapping=name_mapping,
            series_title=series_title,
            hardlink_base=hardlink_base,
            torrent_name=torrent_name,
        )

        logger.info("Computed TV hardlink pairs", pair_count=len(pairs))

        # 4. Create hardlinks
        result = self._hardlink_service.create_hardlinks(pairs, filter_extensions=False)
        if result.errors:
            logger.error("TV hardlink creation failed", errors=len(result.errors))

        logger.info("TV hardlinks created", created=len(result.created))
        return name_mapping

    async def _handle_movie_grab(
        self,
        files_on_disk: list[Path],
        save_path: Path,
        movie_title: str,
        year: int | None,
        hardlink_base: Path,
        total_files: int = 1,
        torrent_name: str = "",
    ) -> None:
        """Handle movie grab: single-file flat in hardlink_base, multi-file under {torrent_name}/."""
        pairs = self._compute_movie_hardlink_pairs(
            files_on_disk=files_on_disk,
            save_path=save_path,
            movie_title=movie_title,
            year=year,
            hardlink_base=hardlink_base,
            total_files=total_files,
            torrent_name=torrent_name,
        )

        logger.info("Computed movie hardlink pairs", pair_count=len(pairs))

        # Movies hardlink ALL files (no extension filter)
        result = self._hardlink_service.create_hardlinks(pairs, filter_extensions=False)
        if result.errors:
            logger.error("Movie hardlink creation failed", errors=len(result.errors))
            return

        logger.info("Movie hardlinks created", created=len(result.created))

    @staticmethod
    def _compute_tv_hardlink_pairs(
        video_files: list[Path],
        name_mapping: dict[str, str],
        series_title: str,
        hardlink_base: Path,
        torrent_name: str = "",
    ) -> list[tuple[Path, Path]]:
        """Compute (src, dst) hardlink pairs for TV files.

        Files are placed flat in hardlink_base/{torrent_name}/ with LLM-normalized names.
        Falls back to original name if LLM mapping not available.

        The subfolder uses torrent_name (sanitized) so Sonarr/Radarr Remote Path Mapping
        resolves correctly: content_path = {save_path}/{torrent.name} -> hardlinks/{torrent.name}.
        series_title is kept for LLM context only, not used for the destination directory.
        """
        # Use torrent_name as subfolder if provided, else fall back to series_title
        folder_source = torrent_name if torrent_name else series_title
        safe_torrent = MediaHandlerService._sanitize_title(folder_source)
        pairs = []
        for src in video_files:
            dst_name = name_mapping.get(src.name, src.name)
            dst = hardlink_base / safe_torrent / dst_name
            pairs.append((src, dst))
        return pairs

    @staticmethod
    def _compute_movie_hardlink_pairs(
        files_on_disk: list[Path],
        save_path: Path,
        movie_title: str,
        year: int | None,
        hardlink_base: Path,
        total_files: int = 1,
        torrent_name: str = "",
    ) -> list[tuple[Path, Path]]:
        """Compute (src, dst) hardlink pairs for movie files.

        Single-file torrent (total_files==1): hardlink_base/{filename} (no wrapper folder).
        Multi-file torrent: hardlink_base/{torrent_name}/{torrent-relative path}.

        The torrent_name subfolder (not movie_title) is used so Sonarr/Radarr Remote Path
        Mapping can resolve content_path = {save_path}/{torrent.name} -> hardlinks/{torrent.name}.
        """
        if total_files == 1:
            src = files_on_disk[0]
            dst = hardlink_base / src.name
            return [(src, dst)]

        # Multi-file: use torrent_name as subfolder if provided, else fall back to movie title
        if torrent_name:
            safe_torrent = MediaHandlerService._sanitize_title(torrent_name)
        else:
            safe_title = MediaHandlerService._sanitize_title(movie_title)
            safe_torrent = f"{safe_title} ({year})" if year else safe_title

        pairs = []
        for src in files_on_disk:
            try:
                relative = src.relative_to(save_path)
            except ValueError:
                relative = Path(src.name)
            dst = hardlink_base / safe_torrent / relative
            pairs.append((src, dst))
        return pairs

    @staticmethod
    def _subtitle_dst_name(sub_name: str, video_mappings: dict[str, str]) -> str:
        """Compute subtitle destination filename without LLM.

        Strategy:
        1. Extract episode number from the subtitle bare filename.
        2. Find normalized video name with the same episode (from video_mappings values).
        3. Result: "{norm_stem}.{group_folder}.{ext}" — unique per group, named after video.
        4. Fallback: preserve original torrent-relative path (keeps group dir).

        Examples:
            sub_name="SovetRomantica/01.ass", video "Show.S01E01.mkv"
              → "Show.S01E01.SovetRomantica.ass"
            sub_name="Cqur Far/01.ass", video "Show.S01E01.mkv"
              → "Show.S01E01.Cqur Far.ass"
            sub_name="01.ass" (root-level), video "Show.S01E01.mkv"
              → "Show.S01E01.ass"
            No video match → "SovetRomantica/01.ass" (preserves group dir)
        """
        sub_path = Path(sub_name)
        sub_stem = sub_path.stem        # e.g. "01"
        sub_ext = sub_path.suffix       # e.g. ".ass"
        group_name = sub_path.parent.name  # e.g. "SovetRomantica" or "" if at root

        # Extract episode number from subtitle stem
        ep_num = MediaHandlerService._extract_episode_number(sub_stem)

        if ep_num is not None and video_mappings:
            # Find normalized video with matching episode number (SxxEyy pattern)
            for norm_name in video_mappings.values():
                m = re.search(r'[Ee](\d{2,3})', Path(norm_name).stem)
                if m and int(m.group(1)) == ep_num:
                    norm_stem = Path(norm_name).stem
                    if group_name:
                        return f"{norm_stem}.{group_name}{sub_ext}"
                    return f"{norm_stem}{sub_ext}"

        # Fallback: preserve group directory structure (no collision between groups)
        return sub_name

    @staticmethod
    def _extract_episode_number(stem: str) -> int | None:
        """Extract a single episode number from a filename stem.

        Handles: "01", "E01", "e01", "01v2", " - 01", "_01_".
        Returns None if ambiguous or not found.
        """
        # Bare number or number with version suffix: "01", "01v2", "01 [720p]"
        m = re.match(r'^[Ee]?(\d{1,3})(?:[vV]\d+)?(?:\s|$|\[|_)', stem)
        if m:
            return int(m.group(1))
        # Preceded by separator: " - 01", "_01_"
        m = re.search(r'[-_\s](\d{1,3})(?:[vV]\d+)?(?:[-_\s\[]|$)', stem)
        if m:
            return int(m.group(1))
        return None

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

    async def _process_subtitles_incremental(
        self,
        download_id: str,
        save_path: Path,
        video_mappings: dict[str, str],
        torrent_name: str,
        hardlink_base: Path,
        already_hardlinked_subs: set[str],
    ) -> None:
        """Find subtitle files in the torrent and create hardlinks for them.

        Called incrementally inside the polling loop (for TV media type only).
        Movies hardlink all files as-is via _handle_movie_grab.

        Args:
            download_id: Torrent hash / download ID.
            save_path: Torrent save path (root of torrent files).
            video_mappings: LLM mapping of old_video_name -> new_video_name.
            torrent_name: qBittorrent torrent.name — used as destination subfolder.
            hardlink_base: Hardlink staging root path.
            already_hardlinked_subs: Set of torrent-relative sub paths already hardlinked.
                Mutated in place — newly hardlinked subs are added after processing.
        """
        try:
            file_list = await self._qb_service.get_torrent_files(download_id)
            if not file_list.files:
                return

            # Filter subtitle files (returns torrent-relative paths)
            subtitle_names = self._subtitle_service.filter_subtitle_files(
                file_list.files
            )
            if not subtitle_names:
                logger.debug("No subtitle files found in torrent")
                return

            # Only process subs not yet hardlinked
            new_subs = [s for s in subtitle_names if s not in already_hardlinked_subs]
            if not new_subs:
                return

            logger.info(
                "Found subtitle files",
                count=len(new_subs),
            )

            # Build subtitle hardlink pairs using torrent_name subfolder.
            # No LLM: derive name from already-normalized video names in video_mappings.
            safe_torrent = MediaHandlerService._sanitize_title(torrent_name)
            subtitle_pairs: list[tuple[Path, Path]] = []
            successfully_hardlinked: list[str] = []

            for sub_name in new_subs:
                src = save_path / sub_name
                if src.exists():
                    dst_name = MediaHandlerService._subtitle_dst_name(sub_name, video_mappings)
                    dst = hardlink_base / safe_torrent / dst_name
                    subtitle_pairs.append((src, dst))
                    successfully_hardlinked.append(sub_name)

            if subtitle_pairs and self._hardlink_service:
                result = self._hardlink_service.create_hardlinks(subtitle_pairs)
                logger.info(
                    "Subtitle hardlinks created",
                    created=len(result.created),
                    skipped=len(result.skipped),
                    errors=len(result.errors),
                )
                # Mark successfully attempted subs as done (avoid retrying every poll)
                already_hardlinked_subs.update(successfully_hardlinked)

        except Exception as e:
            logger.warning(
                "Subtitle processing failed (non-fatal)",
                error=str(e),
            )
