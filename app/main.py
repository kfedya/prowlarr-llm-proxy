import structlog
from contextlib import asynccontextmanager
from fastapi import FastAPI

from app.container import Container, shutdown_services
from app.controllers import proxy_router, health_router


def configure_logging() -> None:
    """Configure structured logging."""
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    logger = structlog.get_logger()
    logger.info("Starting application...")
    
    # Initialize DI container
    container = Container()
    app.state.container = container
    
    logger.info("Application started successfully")
    
    yield
    
    # Shutdown
    logger.info("Shutting down application...")
    await shutdown_services(container)
    logger.info("Application stopped")


def create_app() -> FastAPI:
    """Create and configure FastAPI application."""
    configure_logging()
    
    app = FastAPI(
        title="Prowlarr LLM Proxy",
        description=(
            "Proxy between Sonarr/Radarr and Prowlarr that uses LLM to parse "
            "and transform torrent search results."
        ),
        version="0.1.0",
        lifespan=lifespan,
    )
    
    # Include routers
    # Health routes first (without proxy catch-all)
    app.include_router(health_router)
    
    # Proxy catch-all last
    app.include_router(proxy_router)
    
    return app


# Application instance
app = create_app()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8080,
        reload=True,
    )
