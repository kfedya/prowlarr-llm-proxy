# Technology Stack

**Analysis Date:** 2026-02-20

## Languages

**Primary:**
- Python 3.11+ - Core application language, specified in `pyproject.toml` with `python = "^3.11"`

**Secondary:**
- Bash - Docker entrypoint scripts (`entrypoint.sh`, `deploy.sh`)

## Runtime

**Environment:**
- Python 3.13-slim (Docker runtime, optimized for containerized deployment)
- Poetry-managed virtual environment (development)

**Package Manager:**
- Poetry - Dependency management with `pyproject.toml` and `poetry.lock`
- Lock file: Present (`poetry.lock` - 156KB)

## Frameworks

**Core:**
- FastAPI 0.115.6 - Web framework for HTTP API and webhook endpoints
- Uvicorn 0.34.0 - ASGI server for running FastAPI application with "standard" extras

**Async Runtime:**
- asyncio - Built-in async/await support for all I/O operations

**Testing:**
- pytest 8.3.4 - Test runner
- pytest-asyncio 0.25.2 - Async test support with `asyncio_mode = "auto"`

**Build/Dev:**
- ruff 0.9.2 - Fast Python linter (targets E, F, I, N, W, UP rules)
- mypy 1.14.1 - Static type checker in strict mode (`strict = true`)

## Key Dependencies

**Critical:**
- openai 1.59.5 - Official OpenAI client library for LLM integration (GPT-4o-mini for torrent title parsing)
- httpx 0.28.1 - Async HTTP client for proxying requests and external API calls
- pydantic 2.10.4 - Data validation and parsing for webhook payloads
- pydantic-settings 2.7.1 - Environment configuration management

**Infrastructure:**
- redis 5.2.1 - Async Redis client for caching normalized torrent titles (survives app restarts)
- dependency-injector 4.45.0 - IoC container for dependency injection
- structlog 24.4.0 - Structured logging with context tracking
- brotli 1.2.0 - Compression support for HTTP responses

## Configuration

**Environment:**
- Configuration via `.env` file (Pydantic Settings BaseSettings)
- Environment variables override `.env` defaults
- All settings defined in `app/config.py` with Settings class using `model_config`

**Key Configuration Files:**
- `.env` - Local environment variables (not tracked in git)
- `.env.example` - Template with default values
- `pyproject.toml` - Poetry dependency specifications and tool configurations
- `docker-compose.yml` - Multi-service orchestration (proxy, qBittorrent, Redis, Sonarr)

**Build:**
- `Dockerfile` - Two-stage build (poetry dependencies → slim runtime)
- `.dockerignore` - Excludes unnecessary files from Docker context
- Docker healthcheck via `GET /health` endpoint (30s interval)

## Platform Requirements

**Development:**
- Python 3.11+ with pip/poetry
- Redis (optional but recommended for title mapping cache)
- qBittorrent instance (for testing)
- Sonarr instance (for integration testing)

**Production:**
- Docker/Docker Compose deployment
- Deployment target: NAS systems (Unraid-compatible based on deploy.sh)
- Reverse proxy recommended (nginx) for X-Forwarded-Port header support
- Redis instance (optional caching, gracefully degrades without it)

## Key Application Configuration Variables

**App Settings:**
- `PORT` - Listen port (default: 8080)
- `DEBUG` - Debug logging enabled (default: false)
- `ROUTES` - JSON mapping of ports to upstream URLs for multi-port mode

**OpenAI/LLM Settings:**
- `OPENAI_API_KEY` - Required for title parsing
- `OPENAI_MODEL` - Model selection (default: gpt-4o-mini)
- `LLM_ENABLED` - Enable/disable LLM processing (default: true)
- `LLM_TIMEOUT` - LLM request timeout in seconds (default: 30.0)

**Proxy Settings:**
- `UPSTREAM_URL` - Target Sonarr/Radarr URL (single-port mode, default: http://localhost:8989)
- `PROXY_TIMEOUT` - Proxy request timeout (default: 60.0)

**qBittorrent Settings:**
- `QBITTORRENT_URL` - Web UI URL (default: http://localhost:8080)
- `QBITTORRENT_USERNAME` - Login username (default: admin)
- `QBITTORRENT_PASSWORD` - Login password (required)
- `QBITTORRENT_TIMEOUT` - Request timeout (default: 30.0)

**Redis Settings:**
- `REDIS_HOST` - Redis server hostname (default: localhost)
- `REDIS_PORT` - Redis port (default: 6379)
- `REDIS_DB` - Database number (default: 0)
- `REDIS_PASSWORD` - Optional password
- `REDIS_TTL_HOURS` - Cache TTL for normalized titles (default: 48)

## Code Quality Standards

**Linting:**
- Ruff rules: E (errors), F (pyflakes), I (imports), N (naming), W (warnings), UP (upgrades)
- Target Python version: 3.11
- Line length: 100 characters

**Type Checking:**
- MyPy strict mode enabled (`strict = true`)
- Ignores missing imports for third-party libraries

**Testing:**
- Test discovery: `tests/` directory
- Async test support enabled (`asyncio_mode = "auto"`)

---

*Stack analysis: 2026-02-20*
