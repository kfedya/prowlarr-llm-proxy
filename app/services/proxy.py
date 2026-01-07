import re
from typing import TYPE_CHECKING

import httpx
import structlog
from fastapi import Request, Response

if TYPE_CHECKING:
    from app.services.llm import LLMService

logger = structlog.get_logger()

# Torznab search endpoints that return torrent results
TORZNAB_SEARCH_PARAMS = {"t": ["search", "tvsearch", "movie", "music", "book"]}

# Regex to find <title>...</title> inside <item>...</item>
TITLE_PATTERN = re.compile(r"(<item>.*?<title>)(.*?)(</title>.*?</item>)", re.DOTALL)


class ProxyService:
    """Service for proxying requests with logging and optional LLM title parsing."""

    def __init__(
        self,
        routes: dict[int, str],
        timeout: float,
        llm_service: "LLMService | None" = None,
        llm_enabled: bool = True,
    ):
        self._routes = {int(k): v.rstrip("/") for k, v in routes.items()}
        self._timeout = timeout
        self._client = httpx.AsyncClient(timeout=timeout)
        self._llm_service = llm_service
        self._llm_enabled = llm_enabled and llm_service is not None

        logger.info(
            "ProxyService initialized",
            routes=self._routes,
            llm_enabled=self._llm_enabled,
        )

    def _get_upstream_url(self, request: Request) -> str | None:
        """Get upstream URL based on request port."""
        port = request.url.port or 80

        # Check X-Forwarded-Port header (for reverse proxy setups)
        forwarded_port = request.headers.get("x-forwarded-port")
        if forwarded_port:
            try:
                port = int(forwarded_port)
            except ValueError:
                pass

        upstream = self._routes.get(port)

        # Fallback to first route if port not found
        if not upstream and self._routes:
            upstream = next(iter(self._routes.values()))

        return upstream

    def _is_torznab_search(self, request: Request) -> bool:
        """Check if request is a Torznab search request."""
        # Torznab API requests go to /api endpoint with t= parameter
        if "/api" not in request.url.path:
            return False

        query_params = dict(request.query_params)
        t_param = query_params.get("t", "")

        return t_param in TORZNAB_SEARCH_PARAMS["t"]

    async def _process_torznab_response(self, xml_content: str) -> str:
        """Process Torznab XML response and normalize titles using LLM.
        
        Uses regex to preserve original XML structure - only replaces title text.
        Processes titles in parallel for better performance.
        """
        if not self._llm_service:
            return xml_content

        try:
            # Find all <item>...</item> blocks and extract titles
            items = list(TITLE_PATTERN.finditer(xml_content))

            if not items:
                logger.debug("No items found in Torznab response")
                return xml_content

            logger.info(f"Processing {len(items)} torrent items in parallel")

            # Extract all titles
            original_titles = []
            for match in items:
                title = match.group(2)
                original_titles.append(title if title and title.strip() else "")

            # Process all titles in parallel
            normalized_titles = await self._llm_service.parse_titles_batch(original_titles)

            # Build replacement map
            replacements: list[tuple[int, int, str]] = []

            for match, original_title, normalized_title in zip(items, original_titles, normalized_titles):
                if not original_title:
                    continue

                if normalized_title != original_title:
                    # Escape XML special characters
                    safe_title = (
                        normalized_title
                        .replace("&", "&amp;")
                        .replace("<", "&lt;")
                        .replace(">", "&gt;")
                    )
                    new_content = match.group(1) + safe_title + match.group(3)
                    replacements.append((match.start(), match.end(), new_content))

                    logger.debug(
                        "Title normalized",
                        original=original_title[:50],
                        normalized=normalized_title,
                    )

            # Apply replacements in reverse order to preserve positions
            result = xml_content
            for start, end, new_content in reversed(replacements):
                result = result[:start] + new_content + result[end:]

            return result

        except Exception as e:
            logger.error("Failed to process Torznab response", error=str(e))
            return xml_content

    async def proxy_request(self, request: Request) -> Response:
        """
        Proxy a request to upstream with full logging.
        Optionally processes Torznab responses through LLM.
        """
        upstream_url = self._get_upstream_url(request)

        if not upstream_url:
            return Response(
                content='{"error": "No upstream configured"}',
                status_code=503,
                media_type="application/json",
            )

        path = request.url.path
        query_string = request.url.query

        target_url = f"{upstream_url}{path}"
        if query_string:
            target_url = f"{target_url}?{query_string}"

        # Check if this is a Torznab search request
        is_search = self._is_torznab_search(request)

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
            upstream=upstream_url,
            is_torznab_search=is_search,
            body=body.decode("utf-8") if body else None,
        )

        try:
            response = await self._client.request(
                method=request.method,
                url=target_url,
                headers=headers,
                content=body,
            )

            response_body = response.content.decode("utf-8", errors="replace")

            # Process Torznab search responses through LLM
            if is_search and self._llm_enabled and "xml" in response.headers.get("content-type", ""):
                logger.info("Processing Torznab search response through LLM")
                response_body = await self._process_torznab_response(response_body)
                response_content = response_body.encode("utf-8")
            else:
                response_content = response.content

            logger.info(
                "<<< RESPONSE",
                status_code=response.status_code,
                body_preview=response_body[:2000] if len(response_body) > 2000 else response_body,
                body_length=len(response_body),
                processed_by_llm=is_search and self._llm_enabled,
            )

            # Remove compression headers since httpx already decompressed
            response_headers = dict(response.headers)
            response_headers.pop("content-encoding", None)
            response_headers.pop("transfer-encoding", None)
            response_headers["content-length"] = str(len(response_content))

            return Response(
                content=response_content,
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
