from dependency_injector import containers, providers
import redis.asyncio as redis

from app.config import Settings
from app.services.llm import LLMService
from app.services.proxy import ProxyService
from app.services.qbittorrent import QBittorrentService
from app.services.torrent_mapping import TorrentMappingService
from app.services.sonarr_handler import SonarrHandlerService
from app.services.subtitle import SubtitleService


class Container(containers.DeclarativeContainer):
    """Dependency injection container."""

    wiring_config = containers.WiringConfiguration(
        modules=[
            "app.controllers.proxy",
            "app.controllers.health",
            "app.controllers.filemapper",
            "app.controllers.webhook",
        ]
    )

    # Configuration
    config = providers.Singleton(Settings)

    # Redis Client
    redis_client = providers.Singleton(
        redis.Redis,
        host=config.provided.redis_host,
        port=config.provided.redis_port,
        db=config.provided.redis_db,
        password=config.provided.redis_password,
        decode_responses=True,
    )

    # Torrent Mapping Service
    torrent_mapping_service = providers.Singleton(
        TorrentMappingService,
        redis_client=redis_client,
        ttl_hours=config.provided.redis_ttl_hours,
    )

    # LLM Service (optional - only created if API key is provided)
    llm_service = providers.Singleton(
        LLMService,
        api_key=config.provided.openai_api_key,
        model=config.provided.openai_model,
        torrent_mapping_service=torrent_mapping_service,
    )

    # Proxy Service
    proxy_service = providers.Singleton(
        ProxyService,
        routes=config.provided.get_routes.call(),
        timeout=config.provided.proxy_timeout,
        llm_service=llm_service,
        llm_enabled=config.provided.llm_enabled,
        torrent_mapping_service=torrent_mapping_service,
        port_media_types=config.provided.get_port_media_types.call(),
    )

    # qBittorrent Service
    qbittorrent_service = providers.Singleton(
        QBittorrentService,
        base_url=config.provided.qbittorrent_url,
        username=config.provided.qbittorrent_username,
        password=config.provided.qbittorrent_password,
        timeout=config.provided.qbittorrent_timeout,
    )

    # Subtitle Service
    subtitle_service = providers.Singleton(
        SubtitleService,
        llm_service=llm_service,
    )

    # Sonarr Handler Service
    sonarr_handler_service = providers.Singleton(
        SonarrHandlerService,
        torrent_mapping_service=torrent_mapping_service,
        qbittorrent_service=qbittorrent_service,
        llm_service=llm_service,
    )


async def shutdown_services(container: Container) -> None:
    """Cleanup services on shutdown."""
    proxy_service: ProxyService = container.proxy_service()
    await proxy_service.close()
    
    # Close qBittorrent service if initialized
    try:
        qbittorrent_service: QBittorrentService = container.qbittorrent_service()
        await qbittorrent_service.close()
    except Exception:
        pass  # Service may not be initialized
    
    # Close Redis connection
    try:
        redis_client: redis.Redis = container.redis_client()
        await redis_client.aclose()
    except Exception:
        pass  # Redis may not be initialized
