# Testing Patterns

**Analysis Date:** 2026-02-20

## Test Framework

**Runner:**
- Framework: `pytest` 8.3.4+
- Async support: `pytest-asyncio` 0.25.2+
- Configuration in `pyproject.toml`:
  ```toml
  [tool.pytest.ini_options]
  asyncio_mode = "auto"
  testpaths = ["tests"]
  ```

**Assertion Library:**
- Built-in `assert` statements (pytest provides excellent assertion introspection)

**Run Commands:**
```bash
pytest                    # Run all tests in tests/ directory
pytest -v                 # Verbose output
pytest -x                 # Stop on first failure
pytest tests/test_file.py # Run specific test file
pytest tests/ -k "pattern" # Run tests matching pattern
pytest --tb=short         # Shorter traceback output
```

## Test File Organization

**Location:**
- Root-level test files for standalone/integration tests: `test_*.py` in project root
- Examples: `test_qbittorrent.py`, `test_subtitles.py`, `test_manual.py`
- Tests are NOT co-located with source code (separate from `app/` directory)

**Naming:**
- Test files: `test_{domain}.py` (e.g., `test_qbittorrent.py`, `test_subtitles.py`)
- Test functions: `test_{scenario}()` or `test_{function_under_test}_{condition}()`
- Examples:
  - `test_subtitle_metadata_extraction()`
  - `test_subtitle_processing_logic()`
  - `test_qbittorrent_service()`

**Test Directory Structure:**
```
project-root/
├── app/                     # Source code
│   ├── services/
│   ├── models/
│   └── controllers/
├── test_qbittorrent.py     # Integration/manual tests
├── test_subtitles.py       # Feature tests
├── test_manual.py          # Manual/exploratory tests
└── tests/                  # (Would contain unit tests if organized)
```

## Test Structure

**Typical Test Pattern:**
```python
# test_subtitles.py
import sys
sys.path.insert(0, ".")

from app.services.sonarr_handler import SonarrHandlerService
import structlog

# Configure logging for tests
structlog.configure(
    processors=[structlog.dev.ConsoleRenderer()],
    logger_factory=structlog.PrintLoggerFactory(),
)

def test_subtitle_extraction():
    """Test extracting language from subtitle filenames."""
    handler = SonarrHandlerService(
        torrent_mapping_service=MockMapping(),
        qbittorrent_service=MockQB(),
    )

    # Test cases as tuples: (input, expected_output)
    test_cases = [
        ("[SubsPlease] Show - 01.ru.ass", "ru"),
        ("[SubsPlease] Show - 01.eng.ass", "eng"),
    ]

    print("\n🧪 Testing subtitle extraction:\n")
    all_passed = True
    for input_val, expected in test_cases:
        result = handler._extract_subtitle_metadata(input_val)
        status = "✅" if result == expected else "❌"
        if result != expected:
            all_passed = False
        print(f"{input_val:<50} Expected: {expected:<15} Got: {result:<15} {status}")

    return all_passed
```

**Pattern Characteristics:**
1. Import `sys` and add project root to path: `sys.path.insert(0, ".")`
2. Configure `structlog` for test output at module level
3. Test function names start with `test_`
4. Use tuple-based test cases for parameterized testing
5. Print test results in formatted output (for manual inspection)
6. Return boolean indicating pass/fail
7. Mock external dependencies inline (not using mocking libraries)

## Mocking

**Framework:** No external mocking library; use inline mock classes

**Patterns:**
```python
# Simple inline mocks
class MockQB:
    """Mock qBittorrent service."""
    pass

class MockMapping:
    """Mock torrent mapping service."""
    pass

# Usage in tests
handler = SonarrHandlerService(
    torrent_mapping_service=MockMapping(),
    qbittorrent_service=MockQB(),
)
```

**What to Mock:**
- External service dependencies (qBittorrent, Redis, OpenAI)
- Network calls (HTTP requests)
- Database/cache operations
- Anything with side effects (file I/O, network)

**What NOT to Mock:**
- Business logic being tested
- Service initialization
- Domain models
- Logging

## Fixtures and Factories

**Test Data:**
- Inline dictionaries/objects in test functions
- Example from `test_subtitles.py`:
  ```python
  video_mappings = {
      "Season 1/[SubsPlease] Shingeki - 01 [1080p].mkv": "Attack on Titan - S01E01.mkv",
      "Season 1/[SubsPlease] Shingeki - 02 [1080p].mkv": "Attack on Titan - S01E02.mkv",
  }

  subtitle_files = [
      "Season 1/Subs/[SubsPlease] Shingeki - 01.ru.ass",
      "Season 1/[SubsPlease] Shingeki - 02.eng.srt",
  ]
  ```

**Location:**
- Data defined within test function (not in separate fixtures file)
- Keep test data close to test logic for readability
- No pytest fixtures used (keeping approach simple)

## Coverage

**Requirements:**
- Not enforced (no coverage target specified in config)
- No coverage reporting configured

**Testing Strategy:**
- Manual/exploratory tests for integration scenarios
- Focus on critical paths (webhook handling, file mapping)
- Real dependency testing where practical (actual qBittorrent, Redis can be tested against live instances)

## Test Types

**Unit Tests:**
- Isolated testing of functions/methods
- Currently limited; most tests are integration/manual
- Example: `test_subtitle_metadata_extraction()` tests a single method in isolation

**Integration Tests:**
- Test services with mocked dependencies
- Example: `test_qbittorrent.py` is integration test that connects to real qBittorrent instance
- Pattern: Create service, call methods, print results

**Manual/Exploratory Tests:**
- Located in root: `test_manual.py`
- Run with custom arguments (CLI parameters)
- Example from `test_qbittorrent.py`:
  ```python
  async def main():
      """Test qBittorrent service."""
      if len(sys.argv) < 4:
          print("Usage: python test_qbittorrent.py <url> <username> <password>")
          sys.exit(1)

      url = sys.argv[1]
      username = sys.argv[2]
      password = sys.argv[3]
      # ... test code

  if __name__ == "__main__":
      asyncio.run(main())
  ```

**E2E Tests:**
- Not currently implemented
- Would test full flow: webhook → torrent mapping → file operations

## Common Patterns

**Async Testing:**
```python
async def main():
    """Async test function."""
    async with QBittorrentService(url, username, password) as qb:
        torrents = await qb.get_torrent_list()
        print(f"Found {len(torrents)} torrents")

if __name__ == "__main__":
    asyncio.run(main())
```

**Error Testing:**
- Wrapped in try/except with traceback
  ```python
  try:
      async with QBittorrentService(url, username, password) as qb:
          # operations
  except Exception as e:
      print(f"\nError: {e}")
      import traceback
      traceback.print_exc()
      sys.exit(1)
  ```

**Parameterized Test Cases:**
- Use list/tuple of test case tuples
- Iterate and print results
  ```python
  test_cases = [
      (input1, expected1),
      (input2, expected2),
  ]

  for test_input, expected in test_cases:
      result = function_under_test(test_input)
      status = "✅" if result == expected else "❌"
      print(f"{test_input} → {result} {status}")
  ```

## Test Execution

**Running Manual Tests:**
```bash
# Test qBittorrent service
python test_qbittorrent.py http://localhost:8080 admin password

# Test subtitle processing
python test_subtitles.py

# Test with specific torrent hash
python test_qbittorrent.py http://localhost:8080 admin password abc123hash
```

**Expected Output:**
- Formatted tables with test results
- Status indicators: ✅ (pass), ❌ (fail)
- Detailed error messages if failures occur
- No test discovery required (explicitly run files)

## Current Test Coverage

**Tested Components:**
- `QBittorrentService`: Integration tests in `test_qbittorrent.py`
- `SonarrHandlerService` subtitle logic: Tests in `test_subtitles.py`
- Webhook payloads: Manual testing via `test_sonarr_webhook.json`

**Not Currently Tested:**
- `ProxyService` (integration tests would need Prowlarr/Sonarr instances)
- `LLMService` (integration tests would need OpenAI credentials)
- `TorrentMappingService` Redis operations (would need live Redis)
- Database/cache edge cases
- Error scenarios in production flows

## Test Best Practices

**Do:**
- Test against real external services when available (local qBittorrent, test Redis)
- Include descriptive test names that explain the scenario
- Print readable output for manual inspection
- Use inline mocks for unavailable dependencies
- Keep test data close to test logic
- Include both success and error paths

**Don't:**
- Mock business logic being tested
- Create complex test fixtures
- Assume pytest features that aren't configured
- Leave test functions hanging without clear pass/fail
- Test implementation details instead of behavior

---

*Testing analysis: 2026-02-20*
