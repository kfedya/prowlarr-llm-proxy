"""Radarr webhook payload models."""
from pydantic import BaseModel, Field


class WebhookMovieInfo(BaseModel):
    """Movie information from Radarr webhook."""

    id: int = Field(..., description="Movie ID")
    title: str = Field(..., description="Movie title")
    year: int = Field(default=0, description="Release year")
    filePath: str = Field(default="", description="File path")
    releaseDate: str = Field(default="", description="Release date")
    folderPath: str = Field(default="", description="Folder path")
    tmdbId: int = Field(default=0, description="TMDB ID")
    imdbId: str = Field(default="", description="IMDB ID")
    overview: str = Field(default="", description="Movie overview")


class WebhookRemoteMovie(BaseModel):
    """Remote movie information from Radarr webhook."""

    tmdbId: int = Field(default=0, description="TMDB ID")
    imdbId: str = Field(default="", description="IMDB ID")
    title: str = Field(default="", description="Movie title")
    year: int = Field(default=0, description="Release year")


class RadarrWebhookRelease(BaseModel):
    """Release information from Radarr webhook."""

    quality: str = Field(..., description="Quality name")
    qualityVersion: int = Field(default=1, description="Quality version")
    releaseGroup: str = Field(default="", description="Release group")
    releaseTitle: str = Field(..., description="Release title")
    indexer: str = Field(default="", description="Indexer name")
    size: int = Field(default=0, description="Size in bytes")
    customFormatScore: int = Field(default=0, description="Custom format score")
    customFormats: list[str] = Field(default_factory=list, description="Custom formats")
    languages: list = Field(default_factory=list, description="Languages")
    indexerFlags: list[str] = Field(default_factory=list, description="Indexer flags")


class RadarrGrabWebhook(BaseModel):
    """Radarr Grab event webhook payload.

    Note: Some fields are optional to support Radarr's test webhook.
    """

    eventType: str = Field(..., description="Event type (should be 'Grab' or 'Test')")
    instanceName: str = Field(default="", description="Radarr instance name")
    applicationUrl: str = Field(default="", description="Radarr application URL")
    movie: WebhookMovieInfo | None = Field(default=None, description="Movie information")
    remoteMovie: WebhookRemoteMovie | None = Field(default=None, description="Remote movie info")
    release: RadarrWebhookRelease | None = Field(default=None, description="Release information")
    downloadClient: str = Field(default="", description="Download client name")
    downloadClientType: str = Field(default="", description="Download client type")
    downloadId: str = Field(default="", description="Download ID / torrent hash")
    customFormatInfo: dict | None = Field(default=None, description="Custom format info")
