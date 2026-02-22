"""Webhook endpoints for Sonarr/Radarr events."""
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Request
from fastapi.exceptions import RequestValidationError
from dependency_injector.wiring import inject, Provide
import structlog
import json

from app.config import Settings
from app.container import Container
from app.models.sonarr import SonarrGrabWebhook
from app.services.media_handler import MediaHandlerService
from app.services.sonarr_handler import SonarrHandlerService
from app.services.torrent_mapping import MediaType, TorrentMappingService

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/webhook", tags=["Webhooks"])


@router.post("/sonarr/grab/debug")
async def debug_sonarr_webhook(request: Request) -> dict:
    """Debug endpoint to see raw webhook payload."""
    try:
        body = await request.body()
        body_str = body.decode("utf-8")
        logger.info("Received raw webhook", body=body_str)
        
        try:
            json_data = json.loads(body_str)
            logger.info("Parsed JSON", json_keys=list(json_data.keys()) if isinstance(json_data, dict) else "not_dict")
            return {"status": "ok", "received": json_data}
        except json.JSONDecodeError as e:
            logger.error("Failed to parse JSON", error=str(e))
            return {"status": "error", "message": "Invalid JSON", "body": body_str}
    except Exception as e:
        logger.error("Debug endpoint error", error=str(e))
        return {"status": "error", "message": str(e)}


@router.post("/sonarr/grab")
@inject
async def handle_sonarr_grab(
    request: Request,
    background_tasks: BackgroundTasks,
    sonarr_handler: SonarrHandlerService = Depends(Provide[Container.sonarr_handler_service]),
    media_handler: MediaHandlerService = Depends(Provide[Container.media_handler_service]),
    settings: Settings = Depends(Provide[Container.config]),
) -> dict:
    """Handle Sonarr Grab event webhook.

    Routes to MediaHandlerService when USE_NEW_HANDLER=true,
    otherwise uses legacy SonarrHandlerService.

    Args:
        request: Raw HTTP request
        background_tasks: FastAPI background tasks
        sonarr_handler: Legacy Sonarr handler service (injected)
        media_handler: New media handler service (injected)
        settings: Application settings (injected)

    Returns:
        Success message
    """
    # Get and log raw body for debugging
    body = await request.body()
    body_str = body.decode("utf-8")

    try:
        json_data = json.loads(body_str)
        logger.debug("Received webhook payload", keys=list(json_data.keys()) if isinstance(json_data, dict) else None)
    except:
        pass

    # Parse payload
    try:
        payload = SonarrGrabWebhook.model_validate_json(body_str)
    except Exception as e:
        logger.error("Failed to parse webhook payload", error=str(e), body_preview=body_str[:500])
        raise HTTPException(status_code=422, detail=f"Invalid payload: {str(e)}")

    # Handle test webhook from Sonarr
    if payload.eventType == "Test":
        logger.info("Received Sonarr test webhook")
        return {
            "status": "ok",
            "message": "Webhook endpoint is working correctly",
        }

    if payload.eventType != "Grab":
        raise HTTPException(
            status_code=400,
            detail=f"Invalid event type: {payload.eventType}. Expected 'Grab'",
        )

    # Validate required fields for Grab event
    if not payload.series or not payload.release:
        raise HTTPException(
            status_code=400,
            detail="Missing required fields for Grab event",
        )

    logger.info(
        "Received Sonarr Grab webhook",
        series=payload.series.title,
        episodes=len(payload.episodes),
        release=payload.release.releaseTitle[:80],
        use_new_handler=settings.use_new_handler,
    )

    # Route to new or legacy handler based on feature flag
    if settings.use_new_handler:
        background_tasks.add_task(
            media_handler.handle_grab_event,
            release_title=payload.release.releaseTitle,
            download_id=payload.downloadId,
            media_type=MediaType.TV,
            series_title=payload.series.title,
            season_number=payload.episodes[0].seasonNumber if payload.episodes else 1,
            episode_numbers=[ep.episodeNumber for ep in payload.episodes],
        )
    else:
        background_tasks.add_task(sonarr_handler.handle_grab_event, payload)

    return {
        "status": "accepted",
        "message": "Grab event queued for processing",
        "series": payload.series.title,
        "episodes": len(payload.episodes),
    }


@router.get("/stats")
@inject
async def get_webhook_stats(
    mapping_service: TorrentMappingService = Depends(Provide[Container.torrent_mapping_service]),
) -> dict:
    """Get webhook processing statistics.
    
    Returns:
        Statistics about cached mappings
    """
    stats = await mapping_service.get_stats()
    return {
        "status": "ok",
        "mapping_cache": stats,
    }

