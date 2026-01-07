from dependency_injector import containers, providers

from app.config import Settings
from app.services.llm import LLMService
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

    # LLM Service (optional - only created if API key is provided)
    llm_service = providers.Singleton(
        LLMService,
        api_key=config.provided.openai_api_key,
        model=config.provided.openai_model,
    )

    # Proxy Service
    proxy_service = providers.Singleton(
        ProxyService,
        routes=config.provided.get_routes.call(),
        timeout=config.provided.proxy_timeout,
        llm_service=llm_service,
        llm_enabled=config.provided.llm_enabled,
    )


async def shutdown_services(container: Container) -> None:
    """Cleanup services on shutdown."""
    proxy_service: ProxyService = container.proxy_service()
    await proxy_service.close()
