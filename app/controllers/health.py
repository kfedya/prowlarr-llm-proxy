from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["Health"])


class HealthResponse(BaseModel):
    """Health check response."""

    status: str


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Health check endpoint for Kubernetes."""
    return HealthResponse(status="healthy")


@router.get("/health/live", response_model=HealthResponse)
async def liveness() -> HealthResponse:
    """Liveness probe - returns OK if service is running."""
    return HealthResponse(status="ok")


@router.get("/health/ready", response_model=HealthResponse)
async def readiness() -> HealthResponse:
    """Readiness probe - returns OK if service is ready to accept traffic."""
    return HealthResponse(status="ready")
