from app.controllers.proxy import router as proxy_router
from app.controllers.health import router as health_router
from app.controllers.filemapper import router as filemapper_router
from app.controllers.webhook import router as webhook_router

__all__ = ["proxy_router", "health_router", "filemapper_router", "webhook_router"]


