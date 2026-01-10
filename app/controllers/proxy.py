from fastapi import APIRouter, Request, Depends
from fastapi.responses import Response
from dependency_injector.wiring import inject, Provide

from app.container import Container
from app.services.proxy import ProxyService

router = APIRouter(tags=["Proxy"])


@router.api_route(
    "/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"],
)
@inject
async def proxy_all(
    request: Request,
    path: str,
    proxy_service: ProxyService = Depends(Provide[Container.proxy_service]),
) -> Response:
    """
    Proxy all requests to Prowlarr.
    
    This endpoint catches all paths and methods, forwarding them to the 
    configured Prowlarr instance. Search results are automatically 
    transformed using LLM to extract structured metadata.
    """
    return await proxy_service.proxy_request(request)


