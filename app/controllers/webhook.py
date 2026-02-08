"""Webhook endpoints for Sonarr/Radarr events."""
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from dependency_injector.wiring import inject, Provide
import structlog

from app.container import Container
from app.models.sonarr import SonarrGrabWebhook
from app.services.sonarr_handler import SonarrHandlerService
from app.services.torrent_mapping import TorrentMappingService

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/webhook", tags=["Webhooks"])


@router.post("/sonarr/grab")
@inject
async def handle_sonarr_grab(
    payload: SonarrGrabWebhook,
    background_tasks: BackgroundTasks,
    sonarr_handler: SonarrHandlerService = Depends(Provide[Container.sonarr_handler_service]),
) -> dict:
    """Handle Sonarr Grab event webhook.
    
    This endpoint is called by Sonarr when a release is grabbed.
    Processing is done asynchronously in the background.
    
    Args:
        payload: Webhook payload from Sonarr
        background_tasks: FastAPI background tasks
        sonarr_handler: Sonarr handler service (injected)
        
    Returns:
        Success message
    """
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
    )
    
    # Process in background to return response quickly
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

