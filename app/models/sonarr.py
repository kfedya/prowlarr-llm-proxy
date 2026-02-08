"""Sonarr webhook payload models."""
from pydantic import BaseModel, Field


class WebhookSeries(BaseModel):
    """Series information from Sonarr webhook."""
    
    id: int = Field(..., description="Series ID")
    title: str = Field(..., description="Series title")
    path: str = Field(default="", description="Series path")
    tvdbId: int = Field(default=0, description="TVDB ID")
    tvMazeId: int = Field(default=0, description="TVMaze ID")
    tmdbId: int = Field(default=0, description="TMDB ID")
    imdbId: str = Field(default="", description="IMDB ID")
    type: str = Field(default="Standard", description="Series type (Standard/Daily/Anime)")


class WebhookEpisode(BaseModel):
    """Episode information from Sonarr webhook."""
    
    id: int = Field(..., description="Episode ID")
    episodeNumber: int = Field(..., description="Episode number")
    seasonNumber: int = Field(..., description="Season number")
    title: str = Field(default="", description="Episode title")
    airDate: str = Field(default="", description="Air date (YYYY-MM-DD)")
    airDateUtc: str | None = Field(default=None, description="Air date UTC")


class WebhookRelease(BaseModel):
    """Release information from Sonarr webhook."""
    
    quality: str = Field(..., description="Quality name (e.g. Bluray-1080p)")
    qualityVersion: int = Field(default=1, description="Quality version")
    releaseGroup: str = Field(default="", description="Release group")
    releaseTitle: str = Field(..., description="Release title")
    indexer: str = Field(..., description="Indexer name")
    size: int = Field(default=0, description="Size in bytes")


class WebhookCustomFormatInfo(BaseModel):
    """Custom format information."""
    
    customFormats: list[str] = Field(default_factory=list, description="Custom format names")
    customFormatScore: int = Field(default=0, description="Custom format score")


class SonarrGrabWebhook(BaseModel):
    """Sonarr Grab event webhook payload.
    
    Note: Some fields are optional to support Sonarr's test webhook.
    """
    
    eventType: str = Field(..., description="Event type (should be 'Grab' or 'Test')")
    instanceName: str = Field(default="", description="Sonarr instance name")
    applicationUrl: str = Field(default="", description="Sonarr application URL")
    series: WebhookSeries | None = Field(default=None, description="Series information")
    episodes: list[WebhookEpisode] = Field(default_factory=list, description="Episodes being grabbed")
    release: WebhookRelease | None = Field(default=None, description="Release information")
    downloadClient: str = Field(default="", description="Download client name")
    downloadClientType: str = Field(default="", description="Download client type")
    downloadId: str = Field(default="", description="Download ID / torrent hash")
    customFormatInfo: WebhookCustomFormatInfo | None = Field(
        default=None,
        description="Custom format info",
    )


class SonarrImportWebhook(BaseModel):
    """Sonarr Import/Download event webhook payload."""
    
    eventType: str = Field(..., description="Event type (should be 'Download')")
    series: WebhookSeries = Field(..., description="Series information")
    episodes: list[WebhookEpisode] = Field(..., description="Imported episodes")
    isUpgrade: bool = Field(default=False, description="Whether this is an upgrade")
    downloadId: str = Field(default="", description="Download ID")


class FileRenameMapping(BaseModel):
    """Mapping of old file path to new file path."""
    
    old_path: str = Field(..., description="Current file path in torrent")
    new_path: str = Field(..., description="New file path (normalized)")


class FileRenamePlan(BaseModel):
    """Plan for renaming files in a torrent."""
    
    torrent_hash: str = Field(..., description="qBittorrent torrent hash")
    torrent_name: str = Field(..., description="Torrent name")
    series_name: str = Field(..., description="Series name")
    season_number: int = Field(..., description="Season number")
    mappings: list[FileRenameMapping] = Field(
        default_factory=list,
        description="File rename mappings",
    )
    skipped_files: list[str] = Field(
        default_factory=list,
        description="Files that were skipped (not video)",
    )
