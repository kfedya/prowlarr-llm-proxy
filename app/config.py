from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # App settings
    app_name: str = "prowlarr-llm-proxy"
    debug: bool = False
    
    # Server port
    port: int = Field(default=8080, description="Port to listen on")

    # Upstream URL (Sonarr/Radarr) to proxy to
    upstream_url: str = Field(default="http://localhost:8989", description="Upstream URL to proxy to")

    # Proxy settings
    proxy_timeout: float = Field(default=60.0, description="Proxy request timeout in seconds")

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


settings = Settings()
