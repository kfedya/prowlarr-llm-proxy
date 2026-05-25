# Codebase Structure

**Analysis Date:** 2026-02-20

## Directory Layout

```
prowlarr-llm-proxy/
├── app/                    # Main application package
│   ├── __init__.py         # Package marker
│   ├── main.py             # FastAPI app factory and lifespan management
│   ├── config.py           # Pydantic BaseSettings for configuration
│   ├── container.py        # Dependency injection container
│   ├── controllers/        # HTTP request handlers (routers)
│   │   ├── __init__.py     # Router exports
│   │   ├── proxy.py        # Catch-all proxy endpoints
│   │   ├── webhook.py      # Sonarr webhook endpoints
│   │   ├── health.py       # Health check endpoints
│   │   └── filemapper.py   # File-to-episode mapping endpoint
│   ├── services/           # Business logic and integrations
│   │   ├── __init__.py     # Service exports
│   │   ├── proxy.py        # ProxyService (request forwarding + LLM processing)
│   │   ├── llm.py          # LLMService (OpenAI integration)
│   │   ├── sonarr_handler.py # SonarrHandlerService (webhook event processing)
│   │   ├── qbittorrent.py  # QBittorrentService (qBittorrent API client)
│   │   ├── torrent_mapping.py # TorrentMappingService (Redis title cache)
│   │   └── redis.py        # Redis client initialization
│   └── models/             # Pydantic data models
│       ├── __init__.py     # Model exports
│       ├── sonarr.py       # Sonarr webhook payload models
│       └── qbittorrent.py  # qBittorrent API response models
├── tests/                  # Test directory (when created)
├── pyproject.toml          # Poetry project configuration
├── README.md               # Project documentation
├── WEBHOOK_SETUP.md        # Webhook configuration guide
├── QBITTORRENT_SERVICE.md  # qBittorrent integration documentation
└── SUBTITLE_PROCESSING.md  # Subtitle processing documentation
```

## Directory Purposes

**app/:**
- Purpose: Main application package
- Contains: All production code
- Key files: `main.py`, `config.py`, `container.py`
- Entry point: `app.main:app` (FastAPI instance)

**app/controllers/:**
- Purpose: HTTP endpoint handlers (FastAPI routers)
- Contains: Four routers for different endpoint families
- Key files:
  - `proxy.py`: Catch-all proxy routing (must be last in include order)
  - `webhook.py`: Sonarr event handling
  - `health.py`: Service health checks
  - `filemapper.py`: File mapping API
- Design: Each router is a separate module, imported and registered in `main.py`

**app/services/:**
- Purpose: Core business logic and external system integration
- Contains: Service classes that implement application logic
- Key files:
  - `proxy.py`: HTTP request proxying + Torznab response transformation
  - `llm.py`: OpenAI integration with multi-tier caching
  - `sonarr_handler.py`: Webhook event orchestration
  - `qbittorrent.py`: qBittorrent Web API client
  - `torrent_mapping.py`: Redis-based mapping cache
- Design: Service classes are instantiated in `container.py` as singletons
- Dependencies: External libraries (httpx, openai, redis)

**app/models/:**
- Purpose: Data validation using Pydantic
- Contains: BaseModel subclasses for type safety
- Key files:
  - `sonarr.py`: SonarrGrabWebhook, WebhookSeries, WebhookEpisode, WebhookRelease
  - `qbittorrent.py`: TorrentInfo, TorrentFile, TorrentFileList
- Design: Models define request/response shapes, validate at route entry points
- No business logic - pure data structures

## Key File Locations

**Entry Points:**
- `app/main.py`: FastAPI application factory, lifespan manager, router registration
- `uvicorn` CLI: `python -m uvicorn app.main:app --host 0.0.0.0 --port 8080`

**Configuration:**
- `app/config.py`: Settings class with environment variable loading
  - Routes: JSON-encoded mapping of `{port: upstream_url}`
  - OpenAI: API key, model name, enable/disable flag
  - qBittorrent: URL, username, password, timeout
  - Redis: Host, port, database, password, TTL
  - Fallback single-port mode for simple setups

**Dependency Injection:**
- `app/container.py`: DeclarativeContainer with singleton providers
  - Wires: Controllers that use @inject decorator
  - Manages: Service lifecycle and initialization order

**Core Logic:**

**Proxy Service:**
- File: `app/services/proxy.py`
- Purpose: Transparent HTTP proxying with request/response transformation
- Key methods:
  - `proxy_request()`: Main entry point from controller
  - `_is_torznab_search()`: Detects search requests (check `/api` + `t=` param)
  - `_process_torznab_response()`: XML parsing, LLM batch processing, title replacement
  - `_extract_item_data()`: Regex-based XML item parsing
- Patterns: Regex-based XML manipulation (preserves original structure)

**LLM Service:**
- File: `app/services/llm.py`
- Purpose: OpenAI integration with intelligent caching
- Key methods:
  - `parse_items_batch()`: Cache lookup + batch processing entry point
  - `_parse_batch()`: Send batch of 10 items to OpenAI, handle retries
  - `normalize_file_names()`: Rename files to `{Series} - S{S}E{E}.ext`
  - `normalize_subtitle_names()`: Match subtitles to videos, rename with language code
- Caching: Three-tier (memory → Redis → OpenAI API)
- Rate limiting: 10 items/request, 2 concurrent batches, exponential backoff on 429

**Sonarr Handler:**
- File: `app/services/sonarr_handler.py`
- Purpose: Orchestrate webhook event processing pipeline
- Key methods:
  - `handle_grab_event()`: Main webhook handler (orchestrates 8-step process)
  - `_find_torrent()`: Find torrent in qBittorrent with retries
  - `_get_video_files_with_retry()`: Get file list with metadata retry logic
  - `_normalize_file_names()`: Delegate to LLMService
  - `_rename_torrent_for_sonarr()`: Rename torrent folder
  - `_rename_files()`: Rename individual files in qBittorrent
  - `_process_subtitles()`: Handle subtitle file matching and renaming
  - `_move_remaining_files()`: Move non-video/subtitle files to bonus folder
- Retry logic: 10 retries, 2s initial delay, 1.5x exponential backoff

**qBittorrent Service:**
- File: `app/services/qbittorrent.py`
- Purpose: HTTP API client for qBittorrent Web UI
- Key methods:
  - `login()`: Authenticate and store session cookie
  - `get_torrent_list()`: List all torrents
  - `get_torrent_by_hash()`: Get single torrent by hash
  - `get_torrent_files()`: Get file list with metadata
  - `rename_file()`: Rename file in torrent
- Session management: Cookie-based (SID cookie)
- Context manager: Supports `async with service:` for cleanup

**Torrent Mapping Service:**
- File: `app/services/torrent_mapping.py`
- Purpose: Redis-based title mapping cache
- Key methods:
  - `store()`: Save mapping by normalized_title and GUID
  - `get_by_title()`: Lookup by normalized_title
  - `get_by_guid()`: Lookup by GUID
  - `get_stats()`: Cache statistics (count, memory usage)
  - `store_normalized_cache()`: LLM result cache (raw_title|series_name → normalized)
  - `get_normalized_cache()`: Lookup LLM result cache

**Testing:**
- Location: Root directory (loose test files)
- Files: `test_*.py` (manual integration tests)
- Framework: Not configured in pyproject.toml (pytest installed but no test suite)
- Note: Run tests manually via `python test_file.py`

## Naming Conventions

**Files:**
- Pattern: `snake_case.py`
- Example: `proxy.py`, `sonarr_handler.py`, `torrent_mapping.py`
- Controllers/Services/Models: Single responsibility, named after primary class

**Directories:**
- Pattern: `snake_case/`
- Examples: `app/controllers/`, `app/services/`, `app/models/`
- Grouping: By architectural layer

**Classes:**
- Pattern: `PascalCase`
- Examples: `ProxyService`, `LLMService`, `SonarrGrabWebhook`, `TorrentMappingService`
- Suffixes: `Service` for business logic, `Error` for exceptions

**Functions/Methods:**
- Pattern: `snake_case`
- Examples: `proxy_request()`, `_normalize_file_names()`, `handle_grab_event()`
- Private methods: Prefix with `_` (e.g., `_process_torznab_response()`)

**Constants:**
- Pattern: `UPPER_CASE`
- Examples: `BATCH_SIZE = 10`, `MAX_RETRIES = 2`, `TORZNAB_SEARCH_PARAMS`
- Location: Module-level, usually at top near imports

**Models/Types:**
- Pattern: Plural for collections
- Examples: `list[TorrentItem]`, `dict[str, str]`, `set[str]`
- Optional: Use `Type | None` syntax (Python 3.10+)

**Pydantic Models:**
- Pattern: `BaseModel` subclass, field names match external API
- Examples: `WebhookSeries.tvdbId` (matches Sonarr JSON), not `tvdb_id`
- Use `Field()` for documentation and constraints

**Environment Variables:**
- Pattern: `UPPER_CASE_WITH_UNDERSCORES`
- Examples: `OPENAI_API_KEY`, `QBITTORRENT_URL`, `REDIS_HOST`
- Loaded by Pydantic BaseSettings with env file support

## Where to Add New Code

**New Feature (e.g., new API endpoint):**
- Create new router in `app/controllers/{feature}.py`
- Import and register in `app/main.py`: `app.include_router({feature}_router)`
- Create service in `app/services/{feature}.py` if business logic needed
- Add service to container in `app/container.py` if using DI
- Add models in `app/models/{feature}.py` for request/response validation
- Add tests in `tests/test_{feature}.py`

**New Service Class:**
- File: `app/services/{name}.py`
- Pattern: Class that takes dependencies in `__init__`
- Registration: Add provider to `app/container.py` as singleton
- Wiring: If used in controller, add module to `container.wiring_config`
- Logging: Use `logger = structlog.get_logger(__name__)`
- Async support: Use `async def` for I/O operations

**New Data Model:**
- File: `app/models/{domain}.py`
- Pattern: Pydantic BaseModel with Field descriptions
- Validation: Use Pydantic validators if complex logic needed
- Import: Export in `app/models/__init__.py` for convenience
- Documentation: Include docstring explaining when model is used

**New Configuration Option:**
- File: `app/config.py` in Settings class
- Pattern: Add field with `Field(default=..., description=...)`
- Loading: Automatic via env variable (snake_case becomes UPPER_CASE)
- Validation: Use Pydantic validators for complex checks
- Access: Via `config.provided.field_name` in container

**Utilities/Helpers:**
- Location: Create `app/utils/` directory if many helpers
- Files: `app/utils/{category}.py` (e.g., `app/utils/xml_parsing.py`)
- Export: Add to `app/utils/__init__.py`
- Use: Import in services/controllers
- No circular dependencies: Utils should not import services

**Middleware/Hooks:**
- Location: `app/middleware/` (if extensive)
- Registration: In `app/main.py` via `app.add_middleware()`
- Logging: Use structured logging
- Error handling: Graceful degradation

## Special Directories

**app/__pycache__/:**
- Purpose: Python compiled bytecode cache
- Generated: Yes (automatic by Python)
- Committed: No (.gitignore)
- Action: Delete if size grows

**.venv/:**
- Purpose: Virtual environment
- Generated: Yes (via `poetry install`)
- Committed: No (.gitignore)
- Action: Manage via Poetry

**tests/:**
- Purpose: Automated test suite
- Generated: No (user-created)
- Committed: Yes
- Current: Not yet created (test files are loose in root)
- Setup: Configured in `pyproject.toml` but no tests directory

**Root Test Files:**
- Location: `test_*.py` in root directory
- Purpose: Manual integration tests for development
- Not in test runner: Need to run manually (`python test_file.py`)
- Should migrate: To `tests/` directory with proper fixtures

---

*Structure analysis: 2026-02-20*
