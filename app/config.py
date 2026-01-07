import json
from pydantic_settings import BaseSettings
from pydantic import Field


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

    # Proxy settings
    proxy_timeout: float = Field(default=60.0, description="Proxy request timeout in seconds")

    # OpenAI settings
    openai_api_key: str = Field(default="", description="OpenAI API key")
    openai_model: str = Field(default="gpt-4o-mini", description="OpenAI model to use")
    llm_enabled: bool = Field(default=True, description="Enable LLM title parsing")

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }

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
