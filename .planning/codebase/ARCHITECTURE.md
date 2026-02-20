# Architecture

**Analysis Date:** 2026-02-20

## Pattern Overview

**Overall:** Layered microservice proxy with dependency injection and asynchronous event processing.

**Key Characteristics:**
- Reverse proxy pattern for Torznab API (Prowlarr)
- LLM-powered title normalization pipeline
- Event-driven webhook processing (Sonarr → qBittorrent)
- Stateless service with Redis caching
- Multi-layer service architecture with clear separation of concerns

## Layers

**Controllers/Entry Points:**
- Purpose: HTTP request handling and routing
- Location: `app/controllers/`
- Contains: FastAPI routers for proxy, webhooks, health checks, file mapping
- Depends on: Services, models
- Used by: FastAPI application

**Services:**
- Purpose: Core business logic and external system integration
- Location: `app/services/`
- Contains:
  - `proxy.py`: Request proxying and Torznab response processing
  - `llm.py`: OpenAI integration for title parsing and normalization
  - `sonarr_handler.py`: Sonarr webhook event processing
  - `qbittorrent.py`: qBittorrent Web API client
  - `torrent_mapping.py`: Redis-based title mapping cache
  - `redis.py`: Redis client initialization
- Depends on: Models, external APIs (OpenAI, qBittorrent, Redis)
- Used by: Controllers, other services

**Models:**
- Purpose: Data validation and type definitions
- Location: `app/models/`
- Contains: Pydantic models for Sonarr, qBittorrent payloads
- Depends on: Pydantic
- Used by: Controllers, services

**Infrastructure:**
- Purpose: Configuration and dependency management
- Location: `app/`
- Contains:
  - `config.py`: Environment-based settings
  - `container.py`: Dependency injection container
  - `main.py`: FastAPI application factory
- Depends on: Pydantic, dependency-injector
- Used by: All layers

## Data Flow

**Torznab Search Flow (Proxy with LLM Enhancement):**

1. Sonarr sends search request → FastAPI (`app/controllers/proxy.py`)
2. ProxyService detects Torznab API request (check `/api` endpoint + `t=` parameter)
3. ProxyService forwards request to upstream Prowlarr
4. Prowlarr returns XML with torrent items
5. If LLM enabled: ProxyService extracts item titles → sends to LLMService batch processor
6. LLMService queries OpenAI with batch (max 10 items per request, up to 2 concurrent)
7. LLMService checks three caches (memory → Redis → LLM):
   - Memory cache (fast, in-process)
   - Redis cache (survives restarts, 48h TTL)
   - OpenAI API (network call)
8. Normalized titles replace original titles in XML
9. Torrent mappings stored in Redis (maps normalized_title → original_title + metadata)
10. Modified XML returned to Sonarr

**Sonarr Grab Webhook Flow (Download Event Processing):**

1. Sonarr grabs a release → sends Grab event webhook to `/webhook/sonarr/grab`
2. Controller validates webhook payload (SonarrGrabWebhook model)
3. Controller queues background task (returns immediately with 202 Accepted)
4. SonarrHandlerService runs asynchronously:
   - Looks up mapping by normalized_title (from Redis)
   - Finds torrent in qBittorrent by hash or title (with 10 retries, exponential backoff)
   - Retrieves file list from torrent (with 10 retries for metadata loading)
   - Filters to video files only
   - Calls LLMService to normalize file names to Sonarr format
   - Renames torrent folder to match expected series/season format
   - Renames individual video files in qBittorrent via API
   - Processes subtitle files (matches to video, renames, relocates)
   - Moves remaining non-video/subtitle files to bonus folder

**Subtitle Processing Flow:**

1. SonarrHandlerService identifies subtitle files by extension
2. Groups subtitles by episode (matches to renamed video files)
3. Extracts language code from subtitle filename
4. Uses LLMService to normalize subtitle names (matches to video basename)
5. Renames subtitles in qBittorrent
6. Relocates subtitles to root torrent folder (removes nested dirs)

**State Management:**
- Configuration: Loaded once at startup from environment (BaseSettings)
- Dependency Injection: Container holds singleton instances of all services
- Redis State: Torrent mappings (normalized_title → metadata), LLM cache (raw_title|series_name → normalized_title)
- Memory State: LLM in-process cache (fastest lookups)
- No persistent database - all state ephemeral or Redis-backed

## Key Abstractions

**ProxyService:**
- Purpose: Transparent HTTP proxying with content transformation
- Files: `app/services/proxy.py`
- Pattern: Decorator pattern (proxies requests, optionally transforms responses)
- Methods:
  - `proxy_request()`: Main entry point, handles routing and LLM processing
  - `_is_torznab_search()`: Detects search requests by endpoint and parameter
  - `_process_torznab_response()`: Extracts items, calls LLM, replaces titles in XML
  - `_extract_item_data()`: Parses XML to extract title/category
  - `_extract_item_metadata()`: Extracts GUID, size, indexer, download URL for Redis storage

**LLMService:**
- Purpose: OpenAI integration with intelligent caching and batch processing
- Files: `app/services/llm.py`
- Pattern: Facade pattern with multi-tier caching
- Methods:
  - `parse_items_batch()`: Main entry point, handles cache lookups + batching
  - `_parse_batch()`: Sends batch of 10 items to OpenAI, handles rate limiting + retries
  - `_parse_batch_response()`: Parses numbered output format from LLM
  - `normalize_file_names()`: Specialized method for file renaming
  - `normalize_subtitle_names()`: Specialized method for subtitle file mapping
- Caching strategy:
  - In-memory: `{original_title}|{series_name}` → normalized_title (50 tokens)
  - Redis: Persists across restarts, 48h TTL
  - LLM: Only called for cache misses

**QBittorrentService:**
- Purpose: Authenticated API client for qBittorrent Web API
- Files: `app/services/qbittorrent.py`
- Pattern: Client wrapper with session management
- Methods: Login/logout, get torrent list/info, get files, rename files
- Context manager support for automatic cleanup
- Stores session cookie after login

**SonarrHandlerService:**
- Purpose: Orchestrates webhook event processing with retry logic
- Files: `app/services/sonarr_handler.py`
- Pattern: Coordinator/Orchestrator pattern
- Responsibilities:
  - Webhook event parsing and validation
  - Torrent lookup with exponential backoff
  - File metadata retrieval with retries
  - LLM-based file normalization
  - Multi-step file renaming in qBittorrent
  - Subtitle processing and relocation
  - Bonus file handling
- Configurable retry behavior (10 retries default, 2s initial delay, 1.5x backoff)

**TorrentMappingService:**
- Purpose: Redis-based caching of torrent title mappings
- Files: `app/services/torrent_mapping.py`
- Pattern: Repository pattern with dual key indexing
- Stores: Original title, normalized title, series name, metadata (GUID, indexer, size, URL)
- Keys: Primary by normalized_title, secondary by GUID
- TTL: Configurable (48h default)

**Container:**
- Purpose: Dependency injection configuration
- Files: `app/container.py`
- Pattern: Service locator / dependency injection container
- Manages: Singleton instances of all services
- Wiring: Modules that use @inject decorator

## Entry Points

**HTTP Server:**
- Location: `app/main.py`
- Invocation: `uvicorn app.main:app --host 0.0.0.0 --port 8080`
- Responsibilities:
  - Creates FastAPI application
  - Configures structured logging
  - Initializes dependency injection container
  - Manages service lifecycle (startup, shutdown)
  - Registers routers in order (health, webhook, filemapper, proxy catch-all)

**Router: Health Checks:**
- Location: `app/controllers/health.py`
- Endpoints:
  - `GET /health`: Returns `{status: "healthy"}`
  - `GET /health/live`: Kubernetes liveness probe
  - `GET /health/ready`: Kubernetes readiness probe
- Purpose: Service availability monitoring

**Router: Proxy (Catch-all):**
- Location: `app/controllers/proxy.py`
- Endpoints: `/{path:path}` (all methods)
- Purpose: Transparent proxy to upstream Prowlarr/Sonarr with optional LLM processing

**Router: Webhooks:**
- Location: `app/controllers/webhook.py`
- Endpoints:
  - `POST /webhook/sonarr/grab`: Sonarr Grab event (release grabbed)
  - `POST /webhook/sonarr/grab/debug`: Debug endpoint for webhook inspection
  - `GET /webhook/stats`: Redis cache statistics
- Purpose: Event-driven file renaming workflow

**Router: File Mapper:**
- Location: `app/controllers/filemapper.py`
- Endpoints:
  - `POST /api/map-files`: LLM-powered file-to-episode mapper
- Purpose: Ad-hoc file mapping for problematic releases

## Error Handling

**Strategy:** Graceful degradation with structured logging

**Patterns:**

- **Proxy Errors:**
  - Upstream timeout (504 Gateway Timeout)
  - Upstream unavailable (502 Bad Gateway)
  - No upstream configured (503 Service Unavailable)
  - Responses are JSON error objects

- **Webhook Errors:**
  - Invalid payload format (422 Unprocessable Entity)
  - Missing required fields (400 Bad Request)
  - Invalid event type (400 Bad Request)
  - Processing errors logged, webhook returns 202 (background task)

- **LLM Errors:**
  - Rate limit (429) → Exponential backoff retry (1.5s, 3s, 6s)
  - Parsing errors → Returns original titles unchanged
  - Network errors → Graceful fallback to original content
  - All errors logged with context (batch size, attempt number)

- **qBittorrent Errors:**
  - Auth errors → QBittorrentAuthError raised (must login first)
  - Request errors → Logged with context, optionally retried
  - Session timeout → Automatic re-login on next request
  - Torrent not found → Returns None, caller handles

- **Redis Errors:**
  - Connection errors → Logged as warning, service continues
  - Serialization errors → Logged, mapping not stored but processing continues
  - TTL expiration → Automatic (handled by Redis)

**Logging:** Structured logging via `structlog` with context variables

```python
logger.error("Failed to handle Grab event", error=str(e), series=payload.series.title)
logger.warning("Rate limit hit, retrying batch", attempt=1, delay=1.5)
logger.info("File renamed", torrent_hash="abc123", old="old.mkv", new="new.mkv")
```

## Cross-Cutting Concerns

**Logging:** Structured logging configured in `app/main.py`
- Framework: structlog
- Format: ISO timestamps, log level, context variables
- Processor: ConsoleRenderer (dev-friendly, colored output)
- Context: Merged context variables from application state
- Applied to: All services via `structlog.get_logger()`

**Validation:** Pydantic models enforce schema
- Configuration: BaseSettings in `app/config.py`
- Webhook payloads: SonarrGrabWebhook in `app/models/sonarr.py`
- API responses: FileMapResponse in `app/controllers/filemapper.py`
- Data classes: TorrentItem, TorrentInfo, TorrentFile models

**Authentication:** HTTP client with session cookies
- qBittorrent: Cookie-based session (SID cookie)
- OpenAI: Bearer token in request header (handled by openai library)
- Prowlarr: Pass-through (proxy forwards auth headers)

**Rate Limiting:** Implemented in LLMService
- Batch size: 10 items per OpenAI request
- Concurrent batches: 2 (via asyncio.Semaphore)
- Retry on 429: Exponential backoff (max 2 retries)
- Formula: delay = 1.5s * (2 ^ attempt)

**Timeouts:**
- HTTP proxy: Configured (default 60s)
- qBittorrent API: Configured (default 30s)
- OpenAI API: Inherited from openai library defaults
- Request context: Passed via httpx.AsyncClient(timeout=...)

---

*Architecture analysis: 2026-02-20*
