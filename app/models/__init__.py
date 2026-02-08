"""Models package."""
from app.models.qbittorrent import (
    TorrentFile,
    TorrentInfo,
    TorrentFileList,
    FileRenameRequest,
)
from app.models.sonarr import (
    FileRenameMapping,
    FileRenamePlan,
    SonarrGrabWebhook,
    SonarrImportWebhook,
    WebhookEpisode,
    WebhookRelease,
    WebhookSeries,
)

__all__ = [
    "TorrentFile",
    "TorrentInfo",
    "TorrentFileList",
    "FileRenameRequest",
    "SonarrGrabWebhook",
    "SonarrImportWebhook",
    "WebhookSeries",
    "WebhookEpisode",
    "WebhookRelease",
    "FileRenameMapping",
    "FileRenamePlan",
]

