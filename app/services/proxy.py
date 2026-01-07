import gzip
import structlog
import httpx
import brotli
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
        # Disable auto-decompression to get raw response
        self._client = httpx.AsyncClient(timeout=timeout)
        
        logger.info("ProxyService initialized", upstream_url=self._upstream_url)

    def _decompress(self, content: bytes, encoding: str | None) -> str:
        """Decompress content based on encoding for logging."""
        if not content:
            return "<empty>"
            
        try:
            if encoding == "br":
                decompressed = brotli.decompress(content)
                return decompressed.decode("utf-8", errors="replace")
            elif encoding == "gzip":
                decompressed = gzip.decompress(content)
                return decompressed.decode("utf-8", errors="replace")
            elif encoding:
                # Unknown encoding, try as text
                return content.decode("utf-8", errors="replace")
            else:
                return content.decode("utf-8", errors="replace")
        except Exception as e:
            # Maybe already decompressed or plain text
            try:
                return content.decode("utf-8", errors="replace")
            except Exception:
                return f"<binary data, {len(content)} bytes>"

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
            # Make raw request without auto-decompression
            raw_request = self._client.build_request(
                method=request.method,
                url=target_url,
                headers=headers,
                content=body,
            )
            response = await self._client.send(raw_request, stream=True)
            response_content = await response.aread()

            # Decompress for logging
            content_encoding = response.headers.get("content-encoding")
            response_body = self._decompress(response_content, content_encoding)
            
            logger.info(
                "<<< RESPONSE",
                status_code=response.status_code,
                content_encoding=content_encoding,
                body_preview=response_body[:3000] if len(response_body) > 3000 else response_body,
                body_length=len(response_body),
            )

            # Return original response
            return Response(
                content=response_content,
                status_code=response.status_code,
                headers=dict(response.headers),
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
