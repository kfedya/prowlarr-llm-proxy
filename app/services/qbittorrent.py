"""qBittorrent API service."""
import httpx
import structlog
from typing import Any

from app.models.qbittorrent import TorrentFile, TorrentInfo, TorrentFileList


logger = structlog.get_logger(__name__)


class QBittorrentError(Exception):
    """Base exception for qBittorrent service errors."""
    pass


class QBittorrentAuthError(QBittorrentError):
    """Authentication error."""
    pass


class QBittorrentService:
    """Service for interacting with qBittorrent Web API."""
    
    def __init__(
        self,
        base_url: str,
        username: str,
        password: str,
        timeout: float = 30.0,
    ):
        """Initialize qBittorrent service.
        
        Args:
            base_url: qBittorrent Web UI URL (e.g. http://localhost:8080)
            username: qBittorrent username
            password: qBittorrent password
            timeout: Request timeout in seconds
        """
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None
        self._cookie: str | None = None
        
    async def __aenter__(self) -> "QBittorrentService":
        """Async context manager entry."""
        await self._ensure_client()
        await self.login()
        return self
    
    async def __aexit__(self, *args: Any) -> None:
        """Async context manager exit."""
        await self.close()
    
    async def _ensure_client(self) -> None:
        """Ensure HTTP client is initialized."""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout)
    
    async def close(self) -> None:
        """Close HTTP client and logout."""
        if self._client is not None:
            try:
                await self.logout()
            except Exception as e:
                logger.warning("Error during logout", error=str(e))
            finally:
                await self._client.aclose()
                self._client = None
                self._cookie = None
    
    async def login(self) -> None:
        """Authenticate with qBittorrent."""
        await self._ensure_client()
        
        logger.info("Logging in to qBittorrent", base_url=self.base_url)
        
        if self._client is None:
            raise QBittorrentError("HTTP client not initialized")
        
        response = await self._client.post(
            f"{self.base_url}/api/v2/auth/login",
            data={
                "username": self.username,
                "password": self.password,
            },
        )
        
        if response.status_code != 200:
            raise QBittorrentAuthError(
                f"Login failed with status {response.status_code}: {response.text}"
            )
        
        if response.text != "Ok.":
            raise QBittorrentAuthError(f"Login failed: {response.text}")
        
        # Store session cookie
        cookies = response.cookies
        if "SID" in cookies:
            self._cookie = cookies["SID"]
            logger.info("Successfully logged in to qBittorrent")
        else:
            raise QBittorrentAuthError("No session cookie received")
    
    async def logout(self) -> None:
        """Logout from qBittorrent."""
        if self._client is None or self._cookie is None:
            return
        
        try:
            await self._client.post(
                f"{self.base_url}/api/v2/auth/logout",
                cookies={"SID": self._cookie},
            )
            logger.info("Logged out from qBittorrent")
        except Exception as e:
            logger.warning("Error during logout", error=str(e))
        finally:
            self._cookie = None
    
    async def _request(
        self,
        method: str,
        endpoint: str,
        **kwargs: Any,
    ) -> httpx.Response:
        """Make authenticated request to qBittorrent API.
        
        Args:
            method: HTTP method
            endpoint: API endpoint (without /api/v2/ prefix)
            **kwargs: Additional arguments for httpx request
            
        Returns:
            Response object
            
        Raises:
            QBittorrentAuthError: If not authenticated
            QBittorrentError: On request error
        """
        await self._ensure_client()
        
        if self._client is None:
            raise QBittorrentError("HTTP client not initialized")
        
        if self._cookie is None:
            raise QBittorrentAuthError("Not authenticated. Call login() first.")
        
        # Add session cookie
        if "cookies" not in kwargs:
            kwargs["cookies"] = {}
        kwargs["cookies"]["SID"] = self._cookie
        
        url = f"{self.base_url}/api/v2/{endpoint}"
        
        try:
            response = await self._client.request(method, url, **kwargs)
            response.raise_for_status()
            return response
        except httpx.HTTPStatusError as e:
            raise QBittorrentError(
                f"Request failed with status {e.response.status_code}: {e.response.text}"
            ) from e
        except httpx.RequestError as e:
            raise QBittorrentError(f"Request error: {str(e)}") from e
    
    async def get_torrent_list(self, filter: str | None = None) -> list[TorrentInfo]:
        """Get list of torrents.
        
        Args:
            filter: Optional filter (all, downloading, seeding, completed, etc.)
            
        Returns:
            List of torrents
        """
        params = {}
        if filter:
            params["filter"] = filter
        
        response = await self._request("GET", "torrents/info", params=params)
        torrents_data = response.json()
        
        logger.info("Retrieved torrent list", count=len(torrents_data))
        
        return [TorrentInfo(**torrent) for torrent in torrents_data]
    
    async def get_torrent_by_hash(self, torrent_hash: str) -> TorrentInfo | None:
        """Get torrent by hash.
        
        Args:
            torrent_hash: Torrent hash
            
        Returns:
            Torrent info or None if not found
        """
        torrents = await self.get_torrent_list()
        
        for torrent in torrents:
            if torrent.hash.lower() == torrent_hash.lower():
                return torrent
        
        return None
    
    async def get_torrent_files(self, torrent_hash: str) -> TorrentFileList:
        """Get list of files in a torrent.
        
        Args:
            torrent_hash: Torrent hash
            
        Returns:
            List of files in the torrent
            
        Raises:
            QBittorrentError: If torrent not found or request fails
        """
        logger.info("Getting torrent files", torrent_hash=torrent_hash)
        
        # First get torrent info to get the name
        torrent = await self.get_torrent_by_hash(torrent_hash)
        if torrent is None:
            raise QBittorrentError(f"Torrent not found: {torrent_hash}")
        
        # Get files
        response = await self._request(
            "GET",
            "torrents/files",
            params={"hash": torrent_hash},
        )
        
        files_data = response.json()
        
        # Parse files
        files = []
        for file_data in files_data:
            try:
                files.append(TorrentFile(
                    name=file_data.get("name", ""),
                    size=file_data.get("size", 0),
                    progress=file_data.get("progress", 0.0),
                    priority=file_data.get("priority", 1),
                    is_seed=file_data.get("is_seed", False),
                    piece_range=file_data.get("piece_range", []),
                    availability=file_data.get("availability", 0.0),
                ))
            except Exception as e:
                logger.warning(
                    "Failed to parse file",
                    error=str(e),
                    file_data=file_data,
                )
                continue
        
        logger.info(
            "Retrieved torrent files",
            torrent_hash=torrent_hash,
            torrent_name=torrent.name,
            file_count=len(files),
        )
        
        return TorrentFileList(
            torrent_hash=torrent_hash,
            torrent_name=torrent.name,
            files=files,
        )
    
    async def rename_file(
        self,
        torrent_hash: str,
        old_path: str,
        new_path: str,
    ) -> None:
        """Rename a file in torrent.
        
        Args:
            torrent_hash: Torrent hash
            old_path: Current file path within torrent
            new_path: New file path
            
        Raises:
            QBittorrentError: On rename error
        """
        logger.info(
            "Renaming file in torrent",
            torrent_hash=torrent_hash,
            old_path=old_path,
            new_path=new_path,
        )
        
        await self._request(
            "POST",
            "torrents/renameFile",
            data={
                "hash": torrent_hash,
                "oldPath": old_path,
                "newPath": new_path,
            },
        )
        
        logger.info("File renamed successfully")
    
    async def rename_folder(
        self,
        torrent_hash: str,
        old_path: str,
        new_path: str,
    ) -> None:
        """Rename a folder in torrent.
        
        Args:
            torrent_hash: Torrent hash
            old_path: Current folder path within torrent
            new_path: New folder path
            
        Raises:
            QBittorrentError: On rename error
        """
        logger.info(
            "Renaming folder in torrent",
            torrent_hash=torrent_hash,
            old_path=old_path,
            new_path=new_path,
        )
        
        await self._request(
            "POST",
            "torrents/renameFolder",
            data={
                "hash": torrent_hash,
                "oldPath": old_path,
                "newPath": new_path,
            },
        )
        
        logger.info("Folder renamed successfully")
    
    async def recheck_torrent(self, torrent_hash: str) -> None:
        """Recheck torrent files.
        
        Forces qBittorrent to verify all files and update their status.
        
        Args:
            torrent_hash: Torrent hash
            
        Raises:
            QBittorrentError: On recheck error
        """
        logger.info("Rechecking torrent", torrent_hash=torrent_hash)
        
        await self._request(
            "POST",
            "torrents/recheck",
            data={"hashes": torrent_hash},
        )
        
        logger.info("Torrent recheck initiated")

    async def rename_torrent(self, torrent_hash: str, new_name: str) -> None:
        """Rename torrent (not files inside, but the torrent itself).
        
        This renames the display name of the torrent in qBittorrent.
        This is what Sonarr sees when tracking downloads.
        
        Args:
            torrent_hash: Torrent hash
            new_name: New display name for the torrent
            
        Raises:
            QBittorrentError: On rename error
        """
        logger.info(
            "Renaming torrent",
            torrent_hash=torrent_hash,
            new_name=new_name[:80],
        )
        
        await self._request(
            "POST",
            "torrents/rename",
            data={
                "hash": torrent_hash,
                "name": new_name,
            },
        )
        
        logger.info("Torrent renamed successfully")
