import structlog
import httpx
from fastapi import Request, Response

logger = structlog.get_logger()


class ProxyService:
    """Service for proxying requests to Prowlarr with logging."""

    def __init__(
        self,
        prowlarr_url: str,
        timeout: float,
    ):
        self._prowlarr_url = prowlarr_url.rstrip("/")
        self._timeout = timeout
        self._client = httpx.AsyncClient(timeout=timeout)
        
        logger.info("ProxyService initialized", prowlarr_url=self._prowlarr_url)

    async def proxy_request(self, request: Request) -> Response:
        """
        Proxy a request to Prowlarr with full logging.
        """
        path = request.url.path
        query_string = request.url.query
        
        target_url = f"{self._prowlarr_url}{path}"
        if query_string:
            target_url = f"{target_url}?{query_string}"

        # Prepare headers - pass everything through as-is
        headers = dict(request.headers)
        headers.pop("host", None)

        # Get request body
        body = await request.body()

        # Log request
        logger.info(
            ">>> REQUEST",
            method=request.method,
            path=path,
            query=query_string,
            target_url=target_url,
            headers=dict(request.headers),
            body=body.decode("utf-8") if body else None,
        )

        try:
            # Make proxied request
            response = await self._client.request(
                method=request.method,
                url=target_url,
                headers=headers,
                content=body,
            )

            # Log response
            response_body = response.content.decode("utf-8", errors="replace")
            logger.info(
                "<<< RESPONSE",
                status_code=response.status_code,
                headers=dict(response.headers),
                body_preview=response_body[:2000] if len(response_body) > 2000 else response_body,
                body_length=len(response_body),
            )

            return Response(
                content=response.content,
                status_code=response.status_code,
                headers=dict(response.headers),
            )

        except httpx.TimeoutException:
            logger.error("Request to Prowlarr timed out", path=path)
            return Response(
                content='{"error": "Upstream timeout"}',
                status_code=504,
                media_type="application/json",
            )
        except Exception as e:
            logger.error("Proxy request failed", path=path, error=str(e))
            return Response(
                content='{"error": "Proxy error"}',
                status_code=502,
                media_type="application/json",
            )

    async def close(self) -> None:
        """Close HTTP client."""
        await self._client.aclose()
