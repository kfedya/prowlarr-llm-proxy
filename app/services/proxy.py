import structlog
import httpx
from fastapi import Request, Response

logger = structlog.get_logger()


class ProxyService:
    """Service for proxying requests with logging."""

    def __init__(
        self,
        upstream_url: str,
        timeout: float,
    ):
        self._upstream_url = upstream_url.rstrip("/")
        self._timeout = timeout
        self._client = httpx.AsyncClient(timeout=timeout)
        
        logger.info("ProxyService initialized", upstream_url=self._upstream_url)

    async def proxy_request(self, request: Request) -> Response:
        """
        Proxy a request to upstream with full logging.
        """
        path = request.url.path
        query_string = request.url.query
        
        target_url = f"{self._upstream_url}{path}"
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
            query=query_string or None,
            body=body.decode("utf-8") if body else None,
        )

        try:
            # httpx auto-decompresses responses
            response = await self._client.request(
                method=request.method,
                url=target_url,
                headers=headers,
                content=body,
            )

            # response.content is already decompressed by httpx
            response_body = response.content.decode("utf-8", errors="replace")
            
            logger.info(
                "<<< RESPONSE",
                status_code=response.status_code,
                body_preview=response_body[:3000] if len(response_body) > 3000 else response_body,
                body_length=len(response_body),
            )

            # Remove compression headers since httpx already decompressed
            response_headers = dict(response.headers)
            response_headers.pop("content-encoding", None)
            response_headers.pop("transfer-encoding", None)
            # Set correct content-length for decompressed content
            response_headers["content-length"] = str(len(response.content))

            return Response(
                content=response.content,
                status_code=response.status_code,
                headers=response_headers,
            )

        except httpx.TimeoutException:
            logger.error("Request to upstream timed out", path=path)
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
