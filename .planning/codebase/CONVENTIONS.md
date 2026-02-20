# Coding Conventions

**Analysis Date:** 2026-02-20

## Naming Patterns

**Files:**
- Module files: `snake_case.py` (e.g., `qbittorrent.py`, `sonarr_handler.py`)
- Class-based services: `service_name.py` housing single primary class (e.g., `QBittorrentService` in `qbittorrent.py`)
- Controller/router files: Named after their domain (e.g., `webhook.py`, `proxy.py`, `filemapper.py`)
- Model/schema files: Named by domain (e.g., `sonarr.py`, `qbittorrent.py`)
- Entry point: `main.py` for FastAPI app initialization

**Classes:**
- Service classes: `{Domain}Service` suffix (e.g., `QBittorrentService`, `LLMService`, `TorrentMappingService`)
- Exception classes: `{Domain}Error` or `{Domain}{ErrorType}` (e.g., `QBittorrentError`, `QBittorrentAuthError`)
- Model/Pydantic classes: Descriptive noun forms (e.g., `SonarrGrabWebhook`, `TorrentInfo`, `FileRenameMapping`)
- Router/controller instances: Just `router` (convention across `webhook.py`, `proxy.py`, etc.)

**Functions and Methods:**
- camelCase for async methods: `async_context_manager_entry` = `__aenter__`
- snake_case for all other methods
- Private methods: Leading underscore `_method_name()` (e.g., `_ensure_client()`, `_extract_item_data()`)
- Public methods: No underscore
- Handler/processor methods: `handle_{action}` or `process_{thing}` pattern (e.g., `handle_grab_event()`, `handle_sonarr_grab()`)
- Getter/property methods: `get_{thing}()` or `{thing}()` (e.g., `get_torrent_list()`, `get_upstream_url()`)

**Variables and Constants:**
- Local variables: snake_case
- Module-level constants: UPPER_SNAKE_CASE (e.g., `BATCH_SIZE = 10`, `SYSTEM_PROMPT`)
- Instance variables: snake_case with leading underscore for private (e.g., `self._client`, `self._cookie`)
- Type hints: Use Python 3.11+ union syntax `Type1 | Type2` instead of `Union[Type1, Type2]`

**Parameters:**
- Function parameters: snake_case
- Optional parameters: Use `| None` in type hints (e.g., `name: str | None = None`)

## Code Style

**Formatting:**
- Line length: 100 characters (configured in `pyproject.toml`)
- Tool: `ruff` (Python linter/formatter)
- Configuration in `pyproject.toml`:
  ```toml
  [tool.ruff]
  target-version = "py311"
  line-length = 100
  ```

**Linting:**
- Tool: `ruff` with selective rules
- Active rule groups: E (errors), F (pyflakes), I (imports), N (naming), W (warnings), UP (upgrades)
- Configuration:
  ```toml
  [tool.ruff.lint]
  select = ["E", "F", "I", "N", "W", "UP"]
  ```
- Type checking: `mypy` with strict mode
  ```toml
  [tool.mypy]
  python_version = "3.11"
  strict = true
  ignore_missing_imports = true
  ```

**Docstrings:**
- Use Google-style docstrings for functions and methods
- Format:
  ```python
  def method_name(param1: str, param2: int) -> ReturnType:
      """Short description.

      Longer description if needed.

      Args:
          param1: Description of param1
          param2: Description of param2

      Returns:
          Description of return value

      Raises:
          ExceptionType: When this exception occurs
      """
  ```
- Always include docstrings for public methods and functions
- Use triple quotes for module docstrings: `"""Module description."""`

## Import Organization

**Order:**
1. Standard library imports (e.g., `asyncio`, `json`, `re`)
2. Third-party imports (e.g., `fastapi`, `pydantic`, `httpx`, `structlog`)
3. Local/relative imports (e.g., `from app.models.sonarr import ...`)

**Grouping:**
- Blank line between each group
- Example:
  ```python
  import asyncio
  import json
  import re

  import httpx
  import structlog
  from fastapi import APIRouter, HTTPException
  from pydantic import BaseModel

  from app.models.sonarr import SonarrGrabWebhook
  from app.services.llm import LLMService
  ```

**TYPE_CHECKING blocks:**
- Used for forward references and circular import avoidance:
  ```python
  from typing import TYPE_CHECKING

  if TYPE_CHECKING:
      from app.services.llm import LLMService
  ```
- This allows type hints without runtime imports

## Error Handling

**Exception Patterns:**
- Create domain-specific exception hierarchies (base + specific)
  ```python
  class QBittorrentError(Exception):
      """Base exception for qBittorrent service errors."""
      pass

  class QBittorrentAuthError(QBittorrentError):
      """Authentication error."""
      pass
  ```

- Raise with context using `from e`:
  ```python
  except httpx.RequestError as e:
      raise QBittorrentError(f"Request error: {str(e)}") from e
  ```

- Log errors with context before raising:
  ```python
  logger.error("Failed to do thing", error=str(e), context_var=value)
  raise CustomError(f"Failed to do thing: {str(e)}")
  ```

- Handle errors gracefully in background tasks:
  ```python
  try:
      await self.logout()
  except Exception as e:
      logger.warning("Error during logout", error=str(e))
  finally:
      self._client = None
  ```

## Logging

**Framework:** `structlog` with structured logging

**Configuration:**
- Set up in `app/main.py` via `configure_logging()`
- Processors: context vars merge, log level, timestamps, console renderer
- Logger factory: PrintLoggerFactory (outputs to stdout)
- Caching: enabled on first use

**Patterns:**
- Get logger: `logger = structlog.get_logger(__name__)` at module level
- Info for normal flow: `logger.info("message", key=value, key2=value)`
- Warning for recoverable issues: `logger.warning("issue", error=str(e), context=val)`
- Error for failures: `logger.error("failed operation", error=str(e), path=path)`
- Debug for development: `logger.debug("detail", data=data)`

**Style:**
- Use present tense for messages: "Logging in" not "Logged in"
- Use action verb + object: "Renaming file" not just "File"
- Include key context as keyword arguments (not in message string)
- Use consistent keys across similar operations (e.g., always `error=` for exceptions)

## Comments

**When to Comment:**
- Complex algorithms or non-obvious logic
- Why something is done, not what (code shows what)
- Important rules or constraints (e.g., "User scopes must be validated before use")
- Workarounds or known limitations

**When NOT to Comment:**
- Self-explanatory code with clear names
- Simple loops or conditionals
- Implementation details visible from code

**Style:**
- Use `#` for inline comments (single line)
- Avoid commented-out code (use git history instead)

## Function Design

**Size:**
- Keep functions focused: one responsibility per function
- Typical range: 10-40 lines of code
- Long functions (100+ lines) should be broken into smaller helpers

**Parameters:**
- Max 4-5 positional parameters
- Use kwargs/BaseModel for multiple related parameters
- Example: instead of `func(host, port, user, pass, timeout)`, use config object or grouped kwargs

**Return Values:**
- Return single values for simple cases: `bool`, `str`, `int`
- Return tuple or BaseModel for multiple related values
- Return `None` explicitly when no value (don't rely on implicit None)
- For optional returns, use `Type | None` in type hint

**Async Functions:**
- Prefix with `async def`
- Use `await` explicitly for calls
- Always type-hint with return type (required by mypy strict)
- Example:
  ```python
  async def get_torrent_list(self) -> list[TorrentInfo]:
      """Get list of torrents."""
      response = await self._request("GET", "torrents/info")
      return [TorrentInfo(**t) for t in response.json()]
  ```

## Module Design

**Exports:**
- Define `__all__` if module is part of public API
- Single service class per module (e.g., `QBittorrentService` in `qbittorrent.py`)
- Helper exception classes in same module as service

**Barrel Files:**
- Used in `app/models/__init__.py` and `app/controllers/__init__.py`
- Import and re-export key classes/routers:
  ```python
  from app.controllers.webhook import router as webhook_router
  from app.controllers.proxy import router as proxy_router

  __all__ = ["webhook_router", "proxy_router"]
  ```

**Dependency Injection:**
- Container in `app/container.py` uses `dependency-injector` library
- Services registered as Singletons for request-scoped dependencies
- Configuration injected via `Settings` singleton
- Wiring configured for specific modules in `Container.wiring_config`

## Type Hints

**Always provide:**
- Return types on all functions
- Parameter types on all function arguments
- Use `|` union syntax (Python 3.10+): `str | None`
- Generic types with parameters: `list[TorrentInfo]`, `dict[str, str]`

**Special cases:**
- Self-referencing classes: Use string annotations or `from __future__ import annotations`
- Context manager: Type as `Self` or class name in `__aenter__` return
- Variadic arguments: `*args: Any`, `**kwargs: Any`

## Pydantic Models

**Naming:**
- Descriptive nouns with clear context
- Examples: `SonarrGrabWebhook`, `WebhookSeries`, `TorrentFile`

**Field Patterns:**
- Always include `Field(...)` for documentation
- Use descriptions in `Field(..., description="...")`
- Set defaults explicitly: `Field(default="")` or `Field(default_factory=list)`
- Use `|` for optional fields: `field: str | None = None`

**Validation:**
- Use pydantic validators for business logic
- Keep models simple; validation in services if complex

---

*Convention analysis: 2026-02-20*
