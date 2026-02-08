"""Service for storing and retrieving torrent title mappings."""
import json
from datetime import datetime, timedelta
from typing import Any

import redis.asyncio as redis
import structlog
from pydantic import BaseModel, Field

logger = structlog.get_logger(__name__)


class TorrentMapping(BaseModel):
    """Mapping between normalized and original torrent data."""
    
    original_title: str = Field(..., description="Original torrent title from indexer")
    normalized_title: str = Field(..., description="Normalized title sent to Sonarr")
    series_name: str = Field(default="", description="Series name from Sonarr search")
    guid: str = Field(default="", description="Unique identifier from Prowlarr")
    indexer: str = Field(default="", description="Indexer name")
    category: str = Field(default="", description="Category ID")
    size: int = Field(default=0, description="Torrent size in bytes")
    download_url: str = Field(default="", description="Download URL or magnet link")
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class TorrentMappingService:
    """Service for managing torrent title mappings in Redis."""
    
    def __init__(
        self,
        redis_client: redis.Redis,
        ttl_hours: int = 48,
    ):
        """Initialize mapping service.
        
        Args:
            redis_client: Redis client instance
            ttl_hours: Time-to-live for mappings in hours
        """
        self._redis = redis_client
        self._ttl = timedelta(hours=ttl_hours)
        logger.info("TorrentMappingService initialized", ttl_hours=ttl_hours)
    
    def _make_key(self, identifier: str) -> str:
        """Create Redis key for a mapping."""
        return f"torrent:mapping:{identifier}"
    
    async def store(
        self,
        normalized_title: str,
        original_title: str,
        series_name: str = "",
        guid: str = "",
        indexer: str = "",
        category: str = "",
        size: int = 0,
        download_url: str = "",
    ) -> None:
        """Store a torrent mapping.
        
        Args:
            normalized_title: Normalized title sent to Sonarr
            original_title: Original title from indexer
            series_name: Series name from search query
            guid: Unique GUID from Prowlarr
            indexer: Indexer name
            category: Category ID
            size: Torrent size in bytes
            download_url: Download URL or magnet
        """
        mapping = TorrentMapping(
            original_title=original_title,
            normalized_title=normalized_title,
            series_name=series_name,
            guid=guid,
            indexer=indexer,
            category=category,
            size=size,
            download_url=download_url,
        )
        
        # Store by normalized title (primary key for webhook lookup)
        key = self._make_key(normalized_title)
        ttl_seconds = int(self._ttl.total_seconds())
        
        try:
            await self._redis.setex(
                key,
                ttl_seconds,
                mapping.model_dump_json(),
            )
            
            logger.debug(
                "Stored torrent mapping",
                normalized_title=normalized_title[:60],
                original_title=original_title[:60],
                series_name=series_name,
                ttl_hours=ttl_seconds / 3600,
            )
            
            # Also store by GUID if available (alternative lookup)
            if guid:
                guid_key = self._make_key(f"guid:{guid}")
                await self._redis.setex(
                    guid_key,
                    ttl_seconds,
                    mapping.model_dump_json(),
                )
        
        except Exception as e:
            logger.error(
                "Failed to store torrent mapping",
                error=str(e),
                normalized_title=normalized_title[:60],
            )
    
    async def get_by_title(self, normalized_title: str) -> TorrentMapping | None:
        """Get mapping by normalized title.
        
        Args:
            normalized_title: Normalized title to look up
            
        Returns:
            TorrentMapping if found, None otherwise
        """
        key = self._make_key(normalized_title)
        
        try:
            data = await self._redis.get(key)
            if data:
                mapping = TorrentMapping.model_validate_json(data)
                logger.debug(
                    "Found torrent mapping",
                    normalized_title=normalized_title[:60],
                    original_title=mapping.original_title[:60],
                )
                return mapping
            
            logger.debug("Mapping not found", normalized_title=normalized_title[:60])
            return None
        
        except Exception as e:
            logger.error(
                "Failed to get torrent mapping",
                error=str(e),
                normalized_title=normalized_title[:60],
            )
            return None
    
    async def get_by_guid(self, guid: str) -> TorrentMapping | None:
        """Get mapping by GUID.
        
        Args:
            guid: GUID to look up
            
        Returns:
            TorrentMapping if found, None otherwise
        """
        key = self._make_key(f"guid:{guid}")
        
        try:
            data = await self._redis.get(key)
            if data:
                mapping = TorrentMapping.model_validate_json(data)
                logger.debug("Found torrent mapping by GUID", guid=guid)
                return mapping
            
            return None
        
        except Exception as e:
            logger.error("Failed to get torrent mapping by GUID", error=str(e), guid=guid)
            return None
    
    async def search_by_original_title(self, original_title: str) -> list[TorrentMapping]:
        """Search mappings by original title pattern.
        
        This is a slower operation as it scans keys.
        Use sparingly.
        
        Args:
            original_title: Original title to search for
            
        Returns:
            List of matching mappings
        """
        pattern = self._make_key("*")
        results = []
        
        try:
            # Scan for all mapping keys
            cursor = 0
            while True:
                cursor, keys = await self._redis.scan(
                    cursor,
                    match=pattern,
                    count=100,
                )
                
                if keys:
                    # Get all values
                    values = await self._redis.mget(keys)
                    
                    for value in values:
                        if value:
                            try:
                                mapping = TorrentMapping.model_validate_json(value)
                                if original_title.lower() in mapping.original_title.lower():
                                    results.append(mapping)
                            except Exception:
                                continue
                
                if cursor == 0:
                    break
            
            logger.debug(
                "Searched mappings by original title",
                original_title=original_title[:60],
                found=len(results),
            )
            
            return results
        
        except Exception as e:
            logger.error(
                "Failed to search mappings",
                error=str(e),
                original_title=original_title[:60],
            )
            return []
    
    async def delete(self, normalized_title: str) -> bool:
        """Delete a mapping.
        
        Args:
            normalized_title: Normalized title to delete
            
        Returns:
            True if deleted, False if not found
        """
        key = self._make_key(normalized_title)
        
        try:
            deleted = await self._redis.delete(key)
            if deleted:
                logger.debug("Deleted mapping", normalized_title=normalized_title[:60])
                return True
            return False
        
        except Exception as e:
            logger.error(
                "Failed to delete mapping",
                error=str(e),
                normalized_title=normalized_title[:60],
            )
            return False
    
    async def get_stats(self) -> dict[str, Any]:
        """Get statistics about stored mappings.
        
        Returns:
            Dictionary with stats
        """
        try:
            pattern = self._make_key("*")
            cursor = 0
            count = 0
            
            while True:
                cursor, keys = await self._redis.scan(cursor, match=pattern, count=100)
                count += len(keys)
                
                if cursor == 0:
                    break
            
            return {
                "total_mappings": count,
                "ttl_hours": self._ttl.total_seconds() / 3600,
            }
        
        except Exception as e:
            logger.error("Failed to get stats", error=str(e))
            return {"error": str(e)}

