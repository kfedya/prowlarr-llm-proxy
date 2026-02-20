# External Integrations

**Analysis Date:** 2026-02-20

## APIs & External Services

**Torrent Indexing (Upstream):**
- Prowlarr - Torrent indexer aggregator
  - Purpose: Search results are proxied through this application
  - Integration: Transparent HTTP proxy via `ProxyService` in `app/services/proxy.py`
  - Protocol: Torznab XML API (parsed by regex patterns in proxy service)

**Torrent Management:**
- qBittorrent Web API - Torrent client control
  - SDK/Client: Custom async HTTP client using httpx
  - Auth: Session-based (SID cookie after login)
  - Connection: `app/services/qbittorrent.py` - `QBittorrentService`
  - Endpoints used:
    - `POST /api/v2/auth/login` - Authentication
    - `POST /api/v2/auth/logout` - Logout
    - `GET /api/v2/torrents/info` - List torrents
    - `GET /api/v2/torrents/files` - Get files in torrent
    - `POST /api/v2/torrents/renameFile` - Rename individual files
    - `POST /api/v2/torrents/renameFolder` - Rename torrent folder
    - `POST /api/v2/torrents/rename` - Rename torrent display name
    - `POST /api/v2/torrents/recheck` - Verify torrent integrity

**LLM Services:**
- OpenAI API (or OpenAI-compatible)
  - SDK/Client: openai 1.59.5 (`AsyncOpenAI` in `app/services/llm.py`)
  - Auth: `OPENAI_API_KEY` environment variable
  - Model: `OPENAI_MODEL` (default: gpt-4o-mini)
  - Base URL: Configurable via `LLM_BASE_URL` (defaults to https://api.openai.com/v1)
  - Usage:
    - Title parsing: Normalize raw torrent titles to Sonarr format
    - File renaming: Extract episode numbers and rename video files
    - Subtitle renaming: Match subtitles to video files
  - Rate limiting: Exponential backoff retry logic with max 2 retries (configurable in `BATCH_SIZE`, `MAX_RETRIES`)

**Sonarr Integration:**
- Sonarr - TV series management
  - Integration: Webhook consumer for "Grab" events (`POST /webhook/sonarr/grab`)
  - Payload model: `SonarrGrabWebhook` in `app/models/sonarr.py`
  - Event handling: `SonarrHandlerService` in `app/services/sonarr_handler.py`
  - Flow:
    1. Sonarr sends grab webhook when release is added to qBittorrent
    2. Application looks up original torrent title from mapping cache
    3. Finds torrent in qBittorrent by hash
    4. Extracts and normalizes file names using LLM
    5. Renames files via qBittorrent API
    6. Triggers recheck to update Sonarr

## Data Storage

**Databases:**
- None (Redis is used for caching only, not persistent data storage)

**Caching:**
- Redis (async client `redis.asyncio`)
  - Connection: Configured via `REDIS_HOST`, `REDIS_PORT`, `REDIS_DB`, `REDIS_PASSWORD`
  - Purpose: Cache normalized torrent titles (survives app restarts)
  - Service: `TorrentMappingService` in `app/services/torrent_mapping.py`
  - Key format: `title_mapping:{original_title}|{series_name}`
  - TTL: Configurable via `REDIS_TTL_HOURS` (default: 48 hours)
  - Graceful degradation: Works without Redis, falls back to in-memory cache

**File Storage:**
- Local filesystem (via qBittorrent)
  - Torrent downloads managed entirely by qBittorrent
  - Application interfaces via qBittorrent Web API only
  - No direct file system access required

## Authentication & Identity

**qBittorrent Auth:**
- Type: Username + password
- Flow:
  1. POST `/api/v2/auth/login` with credentials
  2. Receive SID session cookie
  3. Include SID in all subsequent requests
  4. Logout via `POST /api/v2/auth/logout`
- Implementation: `app/services/qbittorrent.py` - `QBittorrentService._request()` method

**OpenAI Auth:**
- Type: Bearer token (API key)
- Mechanism: Authorization header in httpx client
- Implementation: openai library handles header injection

**Sonarr Webhook Auth:**
- Type: None (webhook endpoints are open)
- Security: Assumes private network or firewall protection
- Endpoints: `POST /webhook/sonarr/grab`, `POST /webhook/sonarr/grab/debug`

**Prowlarr Auth:**
- Type: API Key (if required by Prowlarr)
- Usage: Transparent proxy doesn't validate - passed through to upstream
- Implementation: All headers and query parameters forwarded as-is

## Monitoring & Observability

**Error Tracking:**
- None (no Sentry or error tracking service integrated)
- Errors logged via structlog with context

**Logs:**
- Structured logging via structlog (0.24.4)
- Format: Context-aware JSON-compatible format with timestamps
- Logger: PrintLoggerFactory for development, suitable for container stdout
- Log levels: DEBUG, INFO, WARNING, ERROR
- Context tracking: Contextvars integration for request tracing

**Health Checks:**
- Endpoints:
  - `GET /health` - Overall application health
  - `GET /health/live` - Liveness probe
  - `GET /health/ready` - Readiness probe
- Implementation: `app/controllers/health.py`
- Docker healthcheck: Runs `python -c "import httpx; httpx.get(...).raise_for_status()"` every 30 seconds

## CI/CD & Deployment

**Hosting:**
- Docker Compose (development/staging)
- Docker standalone (production on NAS/Unraid)
- Manual deployment script: `deploy.sh`

**CI Pipeline:**
- None detected (no GitHub Actions, GitLab CI, or similar)
- Manual testing via `pytest` or test scripts (test_*.py files)

**Deployment Configuration:**
- `Dockerfile` - Multi-stage build
  - Stage 1: Python 3.13 + Poetry → install dependencies
  - Stage 2: Slim runtime → copy packages and app code
- `docker-compose.yml` - Service orchestration:
  - prowlarr-llm-proxy service
  - Environment variable mapping
  - Port exposure (8585 → 8080)

## Environment Configuration

**Required Environment Variables:**
- `OPENAI_API_KEY` - OpenAI API key (mandatory for LLM features)
- `QBITTORRENT_PASSWORD` - qBittorrent password (mandatory)
- `UPSTREAM_URL` - Target Sonarr/Radarr URL (mandatory for proxy)

**Optional Environment Variables:**
- All settings in `app/config.py` with defaults
- See STACK.md for complete list

**Secrets Location:**
- `.env` file (not tracked in git, listed in `.gitignore`)
- Docker Compose uses `${VAR}` substitution from .env
- Never committed to repository

## Webhooks & Callbacks

**Incoming Webhooks:**
- Sonarr Grab Event: `POST /webhook/sonarr/grab`
  - Payload: JSON with series, episodes, release, and custom formats
  - Processing: Asynchronous via FastAPI BackgroundTasks
  - Handler: `SonarrHandlerService.handle_grab_event()`
  - Debug endpoint: `POST /webhook/sonarr/grab/debug` (returns raw payload)

**Outgoing Webhooks:**
- None (application is consumer only)

**Callback Pattern:**
- qBittorrent API (not webhooks) - synchronous request-response
- All file operations return immediately
- Sonarr webhook processing is background task (returns 202 to Sonarr immediately)

## Request/Response Handling

**Proxy Service:**
- All non-health, non-webhook requests proxied transparently
- Torznab search detection: Checks for `/api` path and `t=` parameter
- If Torznab search + LLM enabled: Parses XML response and normalizes torrent titles
- XML parsing via regex patterns in `app/services/proxy.py`
- Response modification: Only titles in search results are modified, all other fields preserved

**HTTP Client Configuration:**
- httpx with async support throughout
- Timeout: Configurable per service
  - Proxy: `PROXY_TIMEOUT` (default: 60s)
  - qBittorrent: `QBITTORRENT_TIMEOUT` (default: 30s)
  - LLM: `LLM_TIMEOUT` (default: 30.0s) - Only in .env.example, actual timeout in openai library

**Multi-Port Support:**
- Single-port mode: `UPSTREAM_URL` + `PORT` (default)
- Multi-port mode: `ROUTES` JSON env variable
  - Example: `{"8585": "http://sonarr:8989", "8586": "http://prowlarr:9696"}`
  - Implementation: `app/config.py` - `Settings.get_routes()` method

---

*Integration audit: 2026-02-20*
