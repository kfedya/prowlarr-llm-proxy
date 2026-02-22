import json
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # App settings
    app_name: str = "prowlarr-llm-proxy"
    debug: bool = False

    # Routes: JSON mapping of port -> upstream URL
    # Example: {"8585": "http://sonarr:8989", "8586": "http://prowlarr:9696"}
    routes: str = Field(
        default="{}",
        description="JSON mapping of listen ports to upstream URLs",
    )

    # Fallback for single-port mode
    port: int = Field(default=8080, description="Port to listen on")
    upstream_url: str = Field(default="http://localhost:8989", description="Upstream URL")

    # Port-to-media-type mapping: JSON mapping of port -> media type
    # Example: {"8587": "movie"} — forces all searches on port 8587 to use movie prompt
    # Ports not listed default to media type detection from Torznab t= parameter
    port_media_types: str = Field(
        default="{}",
        description="JSON mapping of listen ports to media types (movie/tv)",
    )

    # Proxy settings
    proxy_timeout: float = Field(default=60.0, description="Proxy request timeout in seconds")

    # OpenAI settings
    openai_api_key: str = Field(default="", description="OpenAI API key")
    openai_model: str = Field(default="gpt-4o-mini", description="OpenAI model to use")
    llm_enabled: bool = Field(default=True, description="Enable LLM title parsing")
    max_llm_titles: int = Field(default=50, description="Max titles to process through LLM (0 = unlimited)")

    # qBittorrent settings
    qbittorrent_url: str = Field(default="http://localhost:8080", description="qBittorrent Web UI URL")
    qbittorrent_username: str = Field(default="admin", description="qBittorrent username")
    qbittorrent_password: str = Field(default="", description="qBittorrent password")
    qbittorrent_timeout: float = Field(default=30.0, description="qBittorrent request timeout in seconds")

    # Redis settings
    redis_host: str = Field(default="localhost", description="Redis host")
    redis_port: int = Field(default=6379, description="Redis port")
    redis_db: int = Field(default=0, description="Redis database number")
    redis_password: str = Field(default="", description="Redis password (if required)")
    redis_ttl_hours: int = Field(default=48, description="TTL for cached mappings in hours")

    # Path settings
    download_path: Path = Field(default=Path("/downloads"), description="qBittorrent download directory")
    sonarr_library_path: Path | None = Field(default=None, description="Sonarr library root (e.g., /tv). Required when Sonarr webhook is used.")
    radarr_library_path: Path | None = Field(default=None, description="Radarr library root (e.g., /movies). Required when Radarr webhook is used.")

    # New handler settings
    use_new_handler: bool = Field(default=False, description="Use new MediaHandlerService instead of SonarrHandlerService")
    hardlink_path: Path | None = Field(default=None, description="Hardlink destination directory (default: {download_path}/hardlinks)")

    @model_validator(mode="after")
    def validate_paths(self) -> "Settings":
        """Validate configured paths exist. Skip defaults that don't exist (dev/CI)."""
        if self.download_path != Path("/downloads") and not self.download_path.exists():
            raise ValueError(f"DOWNLOAD_PATH does not exist: {self.download_path}")
        if self.sonarr_library_path is not None and not self.sonarr_library_path.exists():
            raise ValueError(f"SONARR_LIBRARY_PATH does not exist: {self.sonarr_library_path}")
        if self.radarr_library_path is not None and not self.radarr_library_path.exists():
            raise ValueError(f"RADARR_LIBRARY_PATH does not exist: {self.radarr_library_path}")
        # Default hardlink_path when use_new_handler is enabled
        if self.hardlink_path is None and self.use_new_handler:
            self.hardlink_path = self.download_path / "hardlinks"
        return self

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }

    def get_port_media_types(self) -> dict[int, str]:
        """Parse port_media_types JSON into dict of port -> media type string."""
        try:
            mapping = json.loads(self.port_media_types)
            if mapping:
                return {int(k): v for k, v in mapping.items()}
        except (json.JSONDecodeError, ValueError):
            pass
        return {}

    def get_routes(self) -> dict[int, str]:
        """Parse routes JSON into dict of port -> upstream URL."""
        try:
            routes = json.loads(self.routes)
            if routes:
                return {int(k): v for k, v in routes.items()}
        except (json.JSONDecodeError, ValueError):
            pass
        
        # Fallback to single port mode
        return {self.port: self.upstream_url}


settings = Settings()
