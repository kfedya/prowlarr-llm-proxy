"""Tests for ProxyService media type detection and routing."""
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.services.proxy import ProxyService
from app.services.torrent_mapping import MediaType


SAMPLE_XML = '''<?xml version="1.0" encoding="UTF-8"?>
<rss><channel>
<item>
  <title>Test Torrent Title</title>
  <guid>test-guid-123</guid>
  <category>2000</category>
  <size>1000000</size>
  <link>http://example.com/dl</link>
</item>
</channel></rss>'''


def _make_request(query_params: dict | None = None) -> MagicMock:
    """Create a mock Request with the given query params."""
    request = MagicMock()
    request.query_params = query_params or {}
    return request


def _make_proxy_service(
    llm_service: AsyncMock | None = None,
    mapping_service: AsyncMock | None = None,
) -> ProxyService:
    """Create a ProxyService with mocked dependencies."""
    return ProxyService(
        routes={80: "http://localhost:9696"},
        timeout=10.0,
        llm_service=llm_service,
        llm_enabled=True,
        torrent_mapping_service=mapping_service,
    )


class TestMediaTypeDetection:
    """Tests for _get_media_type() routing logic."""

    def setup_method(self):
        self.proxy = _make_proxy_service()

    def test_movie_param_returns_movie(self):
        request = _make_request({"t": "movie"})
        assert self.proxy._get_media_type(request) == MediaType.MOVIE

    def test_tvsearch_param_returns_tv(self):
        request = _make_request({"t": "tvsearch"})
        assert self.proxy._get_media_type(request) == MediaType.TV

    def test_search_param_returns_tv(self):
        request = _make_request({"t": "search"})
        assert self.proxy._get_media_type(request) == MediaType.TV

    def test_missing_t_param_returns_tv(self):
        request = _make_request({})
        assert self.proxy._get_media_type(request) == MediaType.TV

    def test_book_param_returns_tv(self):
        request = _make_request({"t": "book"})
        assert self.proxy._get_media_type(request) == MediaType.TV


class TestProcessTorznabResponseMediaType:
    """Tests for media_type threading through _process_torznab_response."""

    def _make_llm_service(self) -> AsyncMock:
        llm = AsyncMock()
        llm.parse_items_batch = AsyncMock(return_value=["Normalized Title"])
        return llm

    def _make_mapping_service(self) -> AsyncMock:
        mapping = AsyncMock()
        mapping.store = AsyncMock(return_value=None)
        return mapping

    @pytest.mark.asyncio
    async def test_movie_request_passes_movie_media_type_to_llm(self):
        llm = self._make_llm_service()
        proxy = _make_proxy_service(llm_service=llm)

        await proxy._process_torznab_response(
            SAMPLE_XML, series_name="The Matrix", media_type=MediaType.MOVIE
        )

        llm.parse_items_batch.assert_called_once()
        call_kwargs = llm.parse_items_batch.call_args
        assert call_kwargs.kwargs["media_type"] == MediaType.MOVIE

    @pytest.mark.asyncio
    async def test_movie_request_stores_movie_media_type(self):
        llm = self._make_llm_service()
        mapping = self._make_mapping_service()
        proxy = _make_proxy_service(llm_service=llm, mapping_service=mapping)

        await proxy._process_torznab_response(
            SAMPLE_XML, series_name="The Matrix", media_type=MediaType.MOVIE
        )

        mapping.store.assert_called_once()
        call_kwargs = mapping.store.call_args
        assert call_kwargs.kwargs["media_type"] == MediaType.MOVIE

    @pytest.mark.asyncio
    async def test_tv_request_passes_tv_media_type_to_llm(self):
        llm = self._make_llm_service()
        proxy = _make_proxy_service(llm_service=llm)

        await proxy._process_torznab_response(
            SAMPLE_XML, series_name="Breaking Bad", media_type=MediaType.TV
        )

        llm.parse_items_batch.assert_called_once()
        call_kwargs = llm.parse_items_batch.call_args
        assert call_kwargs.kwargs["media_type"] == MediaType.TV

    @pytest.mark.asyncio
    async def test_default_media_type_is_tv(self):
        llm = self._make_llm_service()
        proxy = _make_proxy_service(llm_service=llm)

        # Call WITHOUT media_type parameter -- should default to TV
        await proxy._process_torznab_response(
            SAMPLE_XML, series_name="Breaking Bad"
        )

        llm.parse_items_batch.assert_called_once()
        call_kwargs = llm.parse_items_batch.call_args
        assert call_kwargs.kwargs["media_type"] == MediaType.TV
