from dependency_injector import containers, providers
import redis.asyncio as redis
import structlog

from app.config import Settings
from app.services.hardlink import HardlinkService
from app.services.llm import LLMService
from app.services.media_handler import MediaHandlerService
from app.services.proxy import ProxyService
from app.services.qbittorrent import QBittorrentService
from app.services.torrent_mapping import TorrentMappingService
from app.services.sonarr_handler import SonarrHandlerService
from app.services.subtitle import SubtitleService

_logger = structlog.get_logger(__name__)


def _create_hardlink_service(settings: Settings) -> HardlinkService | None:
    """Create HardlinkService only if new handler is enabled and paths exist."""
    if not settings.use_new_handler:
        return None

    hardlinks_path = settings.hardlink_path
    if hardlinks_path is None:
        _logger.warning("HardlinkService: hardlink_path is None, skipping creation")
        return None

    try:
        return HardlinkService(
            download_path=settings.download_path,
            hardlinks_path=hardlinks_path,
        )
    except Exception as e:
        _logger.warning(
            "HardlinkService creation failed (paths may not exist in dev/CI)",
            error=str(e),
        )
        return None


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

    # Sonarr Handler Service (legacy, used when USE_NEW_HANDLER=false)
    sonarr_handler_service = providers.Singleton(
        SonarrHandlerService,
        torrent_mapping_service=torrent_mapping_service,
        qbittorrent_service=qbittorrent_service,
        llm_service=llm_service,
    )

    # Hardlink Service (only created when USE_NEW_HANDLER=true)
    hardlink_service = providers.Singleton(
        _create_hardlink_service,
        settings=config,
    )

    # Media Handler Service (new handler, used when USE_NEW_HANDLER=true)
    media_handler_service = providers.Singleton(
        MediaHandlerService,
        torrent_mapping_service=torrent_mapping_service,
        qbittorrent_service=qbittorrent_service,
        hardlink_service=hardlink_service,
        subtitle_service=subtitle_service,
        llm_service=llm_service,
        download_path=config.provided.download_path,
        hardlink_path=config.provided.hardlink_path,
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
