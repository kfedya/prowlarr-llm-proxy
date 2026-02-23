---
phase: 05-radarr-webhook-and-movie-hardlinks
plan: 01
subsystem: api, hardlinks
tags: [radarr, webhook, pydantic, hardlink, library-path, fastapi]

# Dependency graph
requires:
  - phase: 04-architecture-refactor
    provides: MediaHandlerService orchestrator, HardlinkService, SubtitleService
provides:
  - RadarrGrabWebhook Pydantic model
  - POST /webhook/radarr/grab endpoint
  - Library-path-aware hardlink destinations (sonarr_library_path, radarr_library_path)
  - Movie behavior (filter_extensions=False, skip subtitles)
  - Nested TV subfolder format ({Title}/Season {NN})
  - Filesystem-unsafe character sanitization
affects: [05-02, deployment, docker-compose]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Library-path routing by MediaType (TV->sonarr, MOVIE->radarr)"
    - "filter_extensions parameter for extension-agnostic hardlinking"
    - "Nested subfolder paths for Sonarr library structure"
    - "_sanitize_title for filesystem-safe path components"

key-files:
  created:
    - app/models/radarr.py
    - tests/test_radarr_webhook.py
  modified:
    - app/controllers/webhook.py
    - app/services/media_handler.py
    - app/services/hardlink.py
    - app/container.py
    - tests/test_media_handler.py

key-decisions:
  - "No feature flag for Radarr endpoint -- direct to MediaHandlerService"
  - "No Radarr rescan API call -- hardlinks fill in-place per user decision"
  - "TV nested subfolder format: {Title}/Season {NN} (matches Sonarr library structure)"
  - "Movies hardlink ALL files (filter_extensions=False) and skip subtitle processing"

patterns-established:
  - "Library-path routing: MediaType.TV->sonarr_library_path, MediaType.MOVIE->radarr_library_path"
  - "Extension filter bypass via filter_extensions=False for movie hardlinks"

requirements-completed: [WHOK-02, WHOK-03, WHOK-04, HDLK-02, HDLK-03]

# Metrics
duration: 5min
completed: 2026-02-23
---

# Phase 5 Plan 1: Radarr Webhook and Library-Path Hardlinks Summary

**Radarr grab webhook endpoint with library-path-aware hardlinks: movies hardlink all files to RADARR_LIBRARY_PATH, TV uses nested {Series}/Season {NN} structure in SONARR_LIBRARY_PATH**

## Performance

- **Duration:** 5 min
- **Started:** 2026-02-23T00:19:51Z
- **Completed:** 2026-02-23T00:24:34Z
- **Tasks:** 3
- **Files modified:** 7

## Accomplishments
- RadarrGrabWebhook Pydantic model validates Radarr grab payloads with all camelCase fields
- POST /webhook/radarr/grab endpoint routes directly to MediaHandlerService (no feature flag)
- Library-path routing: TV hardlinks to SONARR_LIBRARY_PATH, movies to RADARR_LIBRARY_PATH
- Movies hardlink ALL files (no extension filter) and skip subtitle processing
- TV subfolder changed from flat "Title - S01E05" to nested "Title/Season 01" structure
- Filesystem-unsafe character sanitization (_sanitize_title) handles colons, slashes, wildcards
- 109 tests all passing (19 new tests added)

## Task Commits

Each task was committed atomically:

1. **Task 1: Create RadarrGrabWebhook model and Radarr webhook endpoint** - `40c4e24` (feat)
2. **Task 2: Library-path-aware hardlinks with proper folder structure and movie behavior** - `6d6e34f` (feat)
3. **Task 3: Unit tests for Radarr webhook and library-path hardlinks** - `3fbff7a` (test)

## Files Created/Modified
- `app/models/radarr.py` - RadarrGrabWebhook, WebhookMovieInfo, RadarrWebhookRelease Pydantic models
- `app/controllers/webhook.py` - POST /webhook/radarr/grab endpoint
- `app/services/media_handler.py` - Library-path routing, nested TV subfolders, movie behavior, _sanitize_title
- `app/services/hardlink.py` - filter_extensions parameter on create_hardlinks
- `app/container.py` - Injects sonarr_library_path/radarr_library_path into MediaHandlerService
- `tests/test_radarr_webhook.py` - RadarrGrabWebhook model tests
- `tests/test_media_handler.py` - Phase 5 tests: sanitization, movie behavior, library paths

## Decisions Made
- No USE_NEW_HANDLER feature flag for Radarr -- always uses MediaHandlerService directly
- No Radarr rescan API call (WHOK-07 intentionally skipped per user decision -- hardlinks fill in-place)
- TV subfolder format changed to nested for proper Sonarr library structure
- _sanitize_title replaces colons with " -" (common media naming convention)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Updated existing tests for new constructor signature**
- **Found during:** Task 2
- **Issue:** Existing test helper used `hardlink_base=` which was renamed to `sonarr_library_path`/`radarr_library_path`
- **Fix:** Updated _make_service helper and test assertions for new nested TV subfolder format
- **Files modified:** tests/test_media_handler.py
- **Verification:** All 90 existing tests pass
- **Committed in:** 6d6e34f (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Necessary fix for test compatibility with API change. No scope creep.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required. SONARR_LIBRARY_PATH and RADARR_LIBRARY_PATH env vars were already defined in config.py from Phase 4.

## Next Phase Readiness
- Radarr webhook endpoint ready for deployment
- Library-path hardlinks ready for both TV and movies
- Phase 5 Plan 2 (config/env updates, integration testing) can proceed

## Self-Check: PASSED

All 7 files verified on disk. All 3 task commits verified in git log. 109 tests passing.

---
*Phase: 05-radarr-webhook-and-movie-hardlinks*
*Completed: 2026-02-23*
