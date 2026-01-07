from dependency_injector import containers, providers

from app.config import Settings
from app.services.proxy import ProxyService


class Container(containers.DeclarativeContainer):
    """Dependency injection container."""

    wiring_config = containers.WiringConfiguration(
        modules=[
            "app.controllers.proxy",
        ]
    )

    # Configuration
    config = providers.Singleton(Settings)

    # Services
    proxy_service = providers.Singleton(
        ProxyService,
        upstream_url=config.provided.upstream_url,
        timeout=config.provided.proxy_timeout,
    )


async def shutdown_services(container: Container) -> None:
    """Cleanup services on shutdown."""
    proxy_service: ProxyService = container.proxy_service()
    await proxy_service.close()
