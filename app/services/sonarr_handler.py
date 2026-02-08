"""Service for handling Sonarr webhook events."""
import asyncio
import structlog
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.torrent_mapping import TorrentMappingService
    from app.services.qbittorrent import QBittorrentService
    from app.services.llm import LLMService

from app.models.sonarr import SonarrGrabWebhook

logger = structlog.get_logger(__name__)


class SonarrHandlerService:
    """Service for handling Sonarr webhook events and file renaming."""
    
    def __init__(
        self,
        torrent_mapping_service: "TorrentMappingService",
        qbittorrent_service: "QBittorrentService",
        llm_service: "LLMService | None" = None,
        video_extensions: set[str] | None = None,
        subtitle_extensions: set[str] | None = None,
        max_retries: int = 10,
        retry_delay: float = 2.0,
        retry_backoff: float = 1.5,
    ):
        """Initialize Sonarr handler service.
        
        Args:
            torrent_mapping_service: Service for torrent mappings
            qbittorrent_service: Service for qBittorrent API
            llm_service: Service for LLM file normalization (optional)
            video_extensions: Set of video file extensions to process
            subtitle_extensions: Set of subtitle file extensions to process
            max_retries: Maximum number of retries for getting torrent metadata
            retry_delay: Initial delay between retries in seconds
            retry_backoff: Multiplier for retry delay (exponential backoff)
        """
        self._mapping_service = torrent_mapping_service
        self._qb_service = qbittorrent_service
        self._llm_service = llm_service
        self._video_extensions = video_extensions or {
            ".mkv", ".mp4", ".avi", ".ts", ".m2ts", ".mov", ".wmv"
        }
        self._subtitle_extensions = subtitle_extensions or {
            ".ass", ".srt", ".sub", ".ssa", ".vtt", ".sup"
        }
        self._max_retries = max_retries
        self._retry_delay = retry_delay
        self._retry_backoff = retry_backoff
        
        logger.info(
            "SonarrHandlerService initialized",
            llm_enabled=llm_service is not None,
            video_extensions=self._video_extensions,
            subtitle_extensions=self._subtitle_extensions,
            max_retries=max_retries,
            retry_delay=retry_delay,
        )
    
    async def handle_grab_event(self, payload: SonarrGrabWebhook) -> None:
        """Handle Sonarr Grab event.
        
        This method:
        1. Looks up original torrent title from mapping cache
        2. Finds torrent in qBittorrent
        3. Gets file list from torrent
        4. Normalizes file names using LLM
        5. Renames files through qBittorrent API
        
        Args:
            payload: Webhook payload from Sonarr
        """
        try:
            logger.info(
                "Processing Sonarr Grab event",
                series=payload.series.title,
                episodes=len(payload.episodes),
                release=payload.release.releaseTitle[:80],
                download_id=payload.downloadId,
            )
            
            # Step 1: Get torrent mapping from Redis
            mapping = await self._mapping_service.get_by_title(payload.release.releaseTitle)
            
            if not mapping:
                logger.warning(
                    "No mapping found for release",
                    release_title=payload.release.releaseTitle[:80],
                    download_id=payload.downloadId,
                )
                # TODO: Implement fallback search by download_id
                return
            
            logger.info(
                "Found torrent mapping",
                normalized_title=payload.release.releaseTitle[:80],
                original_title=mapping.original_title[:80],
                series_name=mapping.series_name,
            )
            
            # Step 2: Find torrent in qBittorrent
            torrent = await self._find_torrent(payload.downloadId, mapping.original_title)
            
            if not torrent:
                logger.error(
                    "Torrent not found in qBittorrent",
                    download_id=payload.downloadId,
                    original_title=mapping.original_title[:80],
                )
                return
            
            logger.info(
                "Found torrent in qBittorrent",
                torrent_hash=torrent.hash,
                torrent_name=torrent.name[:80],
            )
            
            # Step 3: Get and filter video files (with retries for metadata)
            logger.info(
                "Waiting for torrent metadata to load...",
                torrent_hash=torrent.hash,
                max_retries=self._max_retries,
            )
            video_files = await self._get_video_files_with_retry(torrent.hash)
            
            if not video_files:
                logger.warning("No video files found in torrent", torrent_hash=torrent.hash)
                return
            
            logger.info(
                "Found video files",
                torrent_hash=torrent.hash,
                video_count=len(video_files),
            )
            
            # Step 4: Normalize file names with LLM
            name_mappings = await self._normalize_file_names(
                file_names=[f.name for f in video_files],
                series_name=payload.series.title,
                season_number=payload.episodes[0].seasonNumber if payload.episodes else 1,
                episode_numbers=[ep.episodeNumber for ep in payload.episodes],
            )
            
            if not name_mappings:
                logger.warning("No file name mappings generated", torrent_hash=torrent.hash)
                return
            
            logger.info(
                "Generated file name mappings",
                torrent_hash=torrent.hash,
                mapping_count=len(name_mappings),
            )
            
            # Step 5: Rename torrent FIRST to create proper folder structure
            torrent_folder_name = await self._rename_torrent_for_sonarr(
                torrent_hash=torrent.hash,
                series_name=payload.series.title,
                season_number=payload.episodes[0].seasonNumber if payload.episodes else 1,
                episode_numbers=[ep.episodeNumber for ep in payload.episodes],
            )
            
            # Step 6: Rename files in the torrent
            rename_count = await self._rename_files(
                torrent_hash=torrent.hash,
                name_mappings=name_mappings,
                torrent_folder=torrent_folder_name,
            )
            
            logger.info(
                "Video file renaming completed",
                torrent_hash=torrent.hash,
                renamed=rename_count,
                total=len(name_mappings),
            )
            
            # Step 7: Process subtitles
            subtitle_count = await self._process_subtitles(
                torrent_hash=torrent.hash,
                video_mappings=name_mappings,
                torrent_folder=torrent_folder_name,
            )
            
            # Step 8: Move remaining files to new folder
            moved_count = await self._move_remaining_files(
                torrent_hash=torrent.hash,
                torrent_folder=torrent_folder_name,
                old_torrent_name=torrent.name,
            )
            
            logger.info(
                "Processing completed",
                torrent_hash=torrent.hash,
                videos_renamed=rename_count,
                subtitles_processed=subtitle_count,
                remaining_files_moved=moved_count,
                series=payload.series.title,
                torrent_name=torrent_folder_name[:60],
            )
        
        except Exception as e:
            logger.error(
                "Failed to handle Grab event",
                error=str(e),
                series=payload.series.title,
                release=payload.release.releaseTitle[:80],
            )
    
    async def _find_torrent(self, download_id: str, original_title: str):
        """Find torrent in qBittorrent by download ID or title with retry logic.
        
        Torrent might not be immediately available after Sonarr sends the download request.
        This method retries with exponential backoff.
        
        Args:
            download_id: Download ID from Sonarr (might be hash)
            original_title: Original torrent title from mapping
            
        Returns:
            TorrentInfo if found, None otherwise
        """
        delay = self._retry_delay
        
        for attempt in range(self._max_retries):
            try:
                async with self._qb_service:
                    # Try by hash first
                    try:
                        torrent = await self._qb_service.get_torrent_by_hash(download_id)
                        if torrent:
                            if attempt > 0:
                                logger.info(
                                    "Found torrent after retries",
                                    download_id=download_id,
                                    attempt=attempt + 1,
                                    torrent_name=torrent.name[:60],
                                )
                            return torrent
                    except Exception as e:
                        logger.debug("Failed to find torrent by hash", error=str(e))
                    
                    # Try by name
                    torrents = await self._qb_service.get_torrent_list()
                    for torrent in torrents:
                        if original_title.lower() in torrent.name.lower():
                            if attempt > 0:
                                logger.info(
                                    "Found torrent by name after retries",
                                    original_title=original_title[:60],
                                    attempt=attempt + 1,
                                    torrent_name=torrent.name[:60],
                                )
                            return torrent
                
                # Torrent not found yet
                if attempt < self._max_retries - 1:
                    logger.debug(
                        "Torrent not found, retrying...",
                        download_id=download_id,
                        original_title=original_title[:60],
                        attempt=attempt + 1,
                        max_retries=self._max_retries,
                        retry_in=delay,
                    )
                
            except Exception as e:
                logger.warning(
                    "Error searching for torrent, retrying...",
                    download_id=download_id,
                    attempt=attempt + 1,
                    error=str(e),
                    retry_in=delay,
                )
            
            # Wait before retry
            if attempt < self._max_retries - 1:
                await asyncio.sleep(delay)
                delay *= self._retry_backoff
        
        logger.error(
            "Torrent not found after all retries",
            download_id=download_id,
            original_title=original_title[:60],
            max_retries=self._max_retries,
        )
        return None
    
    async def _get_video_files_with_retry(self, torrent_hash: str):
        """Get list of video files from torrent with retry logic.
        
        Metadata may not be immediately available after torrent is added.
        This method retries with exponential backoff.
        
        Args:
            torrent_hash: Torrent hash
            
        Returns:
            List of video files
        """
        delay = self._retry_delay
        
        for attempt in range(self._max_retries):
            try:
                video_files = await self._get_video_files(torrent_hash)
                
                if video_files:
                    if attempt > 0:
                        logger.info(
                            "Successfully retrieved video files after retries",
                            torrent_hash=torrent_hash,
                            attempt=attempt + 1,
                            video_count=len(video_files),
                        )
                    return video_files
                
                # No video files yet - metadata might not be loaded
                logger.debug(
                    "No video files found, retrying...",
                    torrent_hash=torrent_hash,
                    attempt=attempt + 1,
                    max_retries=self._max_retries,
                    retry_in=delay,
                )
                
            except Exception as e:
                logger.warning(
                    "Error getting torrent files, retrying...",
                    torrent_hash=torrent_hash,
                    attempt=attempt + 1,
                    error=str(e),
                    retry_in=delay,
                )
            
            # Wait before retry
            if attempt < self._max_retries - 1:
                await asyncio.sleep(delay)
                delay *= self._retry_backoff
        
        logger.error(
            "Failed to get video files after all retries",
            torrent_hash=torrent_hash,
            max_retries=self._max_retries,
        )
        return []
    
    async def _get_video_files(self, torrent_hash: str):
        """Get list of video files from torrent.
        
        Args:
            torrent_hash: Torrent hash
            
        Returns:
            List of video files
        """
        async with self._qb_service:
            file_list = await self._qb_service.get_torrent_files(torrent_hash)
            
            video_files = [
                f for f in file_list.files
                if any(f.name.lower().endswith(ext) for ext in self._video_extensions)
            ]
            
            return video_files
    
    async def _normalize_file_names(
        self,
        file_names: list[str],
        series_name: str,
        season_number: int,
        episode_numbers: list[int],
    ) -> dict[str, str]:
        """Normalize file names using LLM.
        
        Args:
            file_names: List of file names
            series_name: Series name
            season_number: Season number
            episode_numbers: Episode numbers
            
        Returns:
            Dict mapping old file name to new file name
        """
        if not self._llm_service:
            logger.warning("LLM service not available, skipping normalization")
            return {}
        
        return await self._llm_service.normalize_file_names(
            file_names=file_names,
            series_name=series_name,
            season_number=season_number,
            episodes=episode_numbers,
        )
    
    async def _rename_files(
        self,
        torrent_hash: str,
        name_mappings: dict[str, str],
        torrent_folder: str,
    ) -> int:
        """Rename files in qBittorrent.
        
        Args:
            torrent_hash: Torrent hash
            name_mappings: Dict mapping old file name to new file name
            torrent_folder: New torrent folder name (from rename_torrent)
            
        Returns:
            Number of successfully renamed files
        """
        rename_count = 0
        
        async with self._qb_service:
            for old_path, new_name in name_mappings.items():
                try:
                    # Construct new path with torrent folder
                    new_path = f"{torrent_folder}/{new_name}"
                    
                    await self._qb_service.rename_file(
                        torrent_hash=torrent_hash,
                        old_path=old_path,
                        new_path=new_path,
                    )
                    
                    rename_count += 1
                    
                    logger.info(
                        "File renamed",
                        torrent_hash=torrent_hash,
                        old=old_path[:60],
                        new=new_path[:60],
                    )
                
                except Exception as e:
                    logger.error(
                        "Failed to rename file",
                        error=str(e),
                        torrent_hash=torrent_hash,
                        old_path=old_path[:60],
                        new_path=f"{torrent_folder}/{new_name}"[:60],
                    )
        
        return rename_count
    
    async def _process_subtitles(
        self,
        torrent_hash: str,
        video_mappings: dict[str, str],
        torrent_folder: str,
    ) -> int:
        """Process and rename subtitle files using LLM.
        
        Uses LLM to match subtitles to videos and generate proper names.
        
        Args:
            torrent_hash: Torrent hash
            video_mappings: Dict of old video paths to new video names
            torrent_folder: New torrent folder name (from rename_torrent)
            
        Returns:
            Number of subtitles processed
        """
        if not video_mappings or not self._llm_service:
            return 0
        
        logger.info("Processing subtitles", torrent_hash=torrent_hash)
        
        async with self._qb_service:
            # Get all files
            file_list = await self._qb_service.get_torrent_files(torrent_hash)
            
            # Find subtitle files
            subtitle_files = [
                f.name for f in file_list.files
                if any(f.name.lower().endswith(ext) for ext in self._subtitle_extensions)
            ]
            
            if not subtitle_files:
                logger.debug("No subtitle files found", torrent_hash=torrent_hash)
                return 0
            
            logger.info(
                "Found subtitle files",
                torrent_hash=torrent_hash,
                count=len(subtitle_files),
            )
            
            # Use LLM to match and rename subtitles
            subtitle_mappings = await self._llm_service.normalize_subtitle_names(
                subtitle_files=subtitle_files,
                video_mappings=video_mappings,
            )
            
            if not subtitle_mappings:
                logger.warning("No subtitle mappings generated", torrent_hash=torrent_hash)
                return 0
            
            logger.info(
                "Generated subtitle mappings",
                torrent_hash=torrent_hash,
                mapping_count=len(subtitle_mappings),
            )
            
            # Rename subtitles
            processed_count = 0
            for old_path, new_name in subtitle_mappings.items():
                try:
                    # Skip if names are the same
                    if old_path == new_name:
                        continue
                    
                    # Construct new path with torrent folder
                    new_path = f"{torrent_folder}/{new_name}"
                    
                    await self._qb_service.rename_file(
                        torrent_hash=torrent_hash,
                        old_path=old_path,
                        new_path=new_path,
                    )
                    
                    processed_count += 1
                    
                    logger.info(
                        "Subtitle processed",
                        torrent_hash=torrent_hash,
                        old=old_path[:60],
                        new=new_path[:60],
                    )
                
                except Exception as e:
                    logger.error(
                        "Failed to process subtitle",
                        error=str(e),
                        torrent_hash=torrent_hash,
                        old_path=old_path[:60],
                        new_path=f"{torrent_folder}/{new_name}"[:60],
                    )
            
            return processed_count
    
    async def _move_remaining_files(
        self,
        torrent_hash: str,
        torrent_folder: str,
        old_torrent_name: str,
    ) -> int:
        """Move all remaining files from old folder to new torrent folder.
        
        This handles files that weren't renamed (like bonus content, extra subtitles, etc.)
        
        Args:
            torrent_hash: Torrent hash
            torrent_folder: New torrent folder name
            old_torrent_name: Original torrent name (for detecting old paths)
            
        Returns:
            Number of files moved
        """
        moved_count = 0
        
        try:
            async with self._qb_service:
                # Get all files in torrent
                file_list = await self._qb_service.get_torrent_files(torrent_hash)
                
                # Find files still in old folder
                files_to_move = []
                for file in file_list.files:
                    # Check if file is still in old folder structure
                    if file.name.startswith(old_torrent_name + "/"):
                        # Extract relative path from old folder
                        relative_path = file.name[len(old_torrent_name) + 1:]
                        files_to_move.append((file.name, relative_path))
                
                if not files_to_move:
                    logger.debug(
                        "No remaining files to move",
                        torrent_hash=torrent_hash,
                    )
                    return 0
                
                logger.info(
                    "Moving remaining files to new folder",
                    torrent_hash=torrent_hash,
                    file_count=len(files_to_move),
                    new_folder=torrent_folder[:60],
                )
                
                # Move each file to new folder
                for old_path, relative_path in files_to_move:
                    try:
                        new_path = f"{torrent_folder}/{relative_path}"
                        
                        await self._qb_service.rename_file(
                            torrent_hash=torrent_hash,
                            old_path=old_path,
                            new_path=new_path,
                        )
                        
                        moved_count += 1
                        
                        logger.debug(
                            "File moved",
                            torrent_hash=torrent_hash,
                            old=old_path[:60],
                            new=new_path[:60],
                        )
                    
                    except Exception as e:
                        logger.error(
                            "Failed to move file",
                            error=str(e),
                            torrent_hash=torrent_hash,
                            old_path=old_path[:60],
                            new_path=f"{torrent_folder}/{relative_path}"[:60],
                        )
                
                logger.info(
                    "Remaining files moved",
                    torrent_hash=torrent_hash,
                    moved=moved_count,
                    total=len(files_to_move),
                )
        
        except Exception as e:
            logger.error(
                "Failed to move remaining files",
                error=str(e),
                torrent_hash=torrent_hash,
            )
        
        return moved_count
    
    async def _rename_torrent_for_sonarr(
        self,
        torrent_hash: str,
        series_name: str,
        season_number: int,
        episode_numbers: list[int],
    ) -> str:
        """Rename torrent to a format Sonarr can parse.
        
        Args:
            torrent_hash: Torrent hash
            series_name: Series name
            season_number: Season number
            episode_numbers: List of episode numbers
            
        Returns:
            The new torrent folder name
        """
        try:
            # Build torrent name in Sonarr-parseable format
            # Format: "Series Name - S01" or "Series Name - S01E01-E12"
            if len(episode_numbers) > 1:
                # Multi-episode: "Series Name - S01E01-E12"
                episode_range = f"E{min(episode_numbers):02d}-E{max(episode_numbers):02d}"
                new_torrent_name = f"{series_name} - S{season_number:02d}{episode_range}"
            else:
                # Single episode: "Series Name - S01E01" or season pack: "Series Name - S01"
                if episode_numbers:
                    new_torrent_name = f"{series_name} - S{season_number:02d}E{episode_numbers[0]:02d}"
                else:
                    new_torrent_name = f"{series_name} - S{season_number:02d}"
            
            logger.info(
                "Renaming torrent for Sonarr",
                torrent_hash=torrent_hash,
                new_name=new_torrent_name[:80],
            )
            
            async with self._qb_service:
                await self._qb_service.rename_torrent(
                    torrent_hash=torrent_hash,
                    new_name=new_torrent_name,
                )
            
            logger.info(
                "Torrent renamed successfully",
                torrent_hash=torrent_hash,
                new_name=new_torrent_name[:80],
            )
            
            return new_torrent_name
        
        except Exception as e:
            logger.error(
                "Failed to rename torrent",
                error=str(e),
                torrent_hash=torrent_hash,
                series_name=series_name,
            )
            # Return series name as fallback
            return series_name

