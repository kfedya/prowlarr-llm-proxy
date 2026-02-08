"""qBittorrent models."""
from pydantic import BaseModel, Field


class TorrentFile(BaseModel):
    """Single file within a torrent."""
    
    name: str = Field(..., description="File path within torrent")
    size: int = Field(..., description="File size in bytes")
    progress: float = Field(default=0.0, description="Download progress (0-1)")
    priority: int = Field(default=1, description="File priority")
    is_seed: bool = Field(default=False, description="Is file fully downloaded")
    piece_range: list[int] = Field(default_factory=list, description="Piece range")
    availability: float = Field(default=0.0, description="File availability")


class TorrentInfo(BaseModel):
    """Information about a torrent."""
    
    hash: str = Field(..., description="Torrent hash")
    name: str = Field(..., description="Torrent name")
    size: int = Field(default=0, description="Total size in bytes")
    progress: float = Field(default=0.0, description="Download progress (0-1)")
    dlspeed: int = Field(default=0, description="Download speed in bytes/s")
    upspeed: int = Field(default=0, description="Upload speed in bytes/s")
    priority: int = Field(default=0, description="Torrent priority")
    num_seeds: int = Field(default=0, description="Number of seeds")
    num_leechs: int = Field(default=0, description="Number of leechers")
    ratio: float = Field(default=0.0, description="Share ratio")
    eta: int = Field(default=0, description="ETA in seconds")
    state: str = Field(default="", description="Torrent state")
    seq_dl: bool = Field(default=False, description="Sequential download")
    f_l_piece_prio: bool = Field(default=False, description="First/last piece priority")
    category: str = Field(default="", description="Torrent category")
    tags: str = Field(default="", description="Torrent tags")
    save_path: str = Field(default="", description="Save path")
    content_path: str = Field(default="", description="Content path")


class TorrentFileList(BaseModel):
    """List of files in a torrent."""
    
    torrent_hash: str = Field(..., description="Torrent hash")
    torrent_name: str = Field(..., description="Torrent name")
    files: list[TorrentFile] = Field(default_factory=list, description="List of files")


class FileRenameRequest(BaseModel):
    """Request to rename a file in torrent."""
    
    torrent_hash: str = Field(..., description="Torrent hash")
    old_path: str = Field(..., description="Current file path")
    new_path: str = Field(..., description="New file path")

