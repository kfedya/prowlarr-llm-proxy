---
phase: 04-architecture-refactor
plan: 02
subsystem: api
tags: [orchestrator, hardlink, polling, feature-flag, asyncio, qbittorrent]

# Dependency graph
requires:
  - phase: 04-architecture-refactor/01
    provides: SubtitleService and HardlinkService for delegation
  - phase: 03-hardlinkservice
    provides: HardlinkService with cross-device validation
provides:
  - MediaHandlerService orchestrator (poll -> hardlink -> subtitle)
  - Feature flag routing in webhook controller (USE_NEW_HANDLER)
  - DI wiring for hardlink_service and media_handler_service
affects: [05-radarr-webhook, deployment, testing]

# Tech tracking
tech-stack:
  added: []
  patterns: [fast-then-backoff polling, factory-based DI for conditional services, feature flag routing]

key-files:
  created:
    - app/services/media_handler.py
    - tests/test_media_handler.py
  modified:
    - app/container.py
    - app/controllers/webhook.py

key-decisions:
  - "HardlinkService wrapped in factory function to handle dev/CI where paths don't exist"
  - "Subtitle hardlinks use same subfolder as video hardlinks (no separate directory)"
  - "Polling returns empty list on timeout rather than raising (caller checks result)"

patterns-established:
  - "Feature flag pattern: USE_NEW_HANDLER routes webhook to old/new handler"
  - "Factory provider pattern: _create_hardlink_service returns None when disabled"

requirements-completed: [ARCH-01, ARCH-03, WHOK-01, WHOK-05]

# Metrics
duration: 4min
completed: 2026-02-23
---

# Phase 4 Plan 2: MediaHandlerService Summary

**MediaHandlerService orchestrator with poll-then-hardlink flow, fast-then-backoff polling (2s/10s/10min), and USE_NEW_HANDLER feature flag routing in webhook controller**

## Performance

- **Duration:** 4 min
- **Started:** 2026-02-22T23:34:46Z
- **Completed:** 2026-02-22T23:38:22Z
- **Tasks:** 3
- **Files modified:** 4

## Accomplishments
- MediaHandlerService orchestrator replaces SonarrHandlerService grab workflow with poll-then-hardlink approach
- Feature flag (USE_NEW_HANDLER) routes webhook to old or new handler with zero disruption to existing behavior
- 13 unit tests covering all orchestration paths, full suite green (90 tests)

## Task Commits

Each task was committed atomically:

1. **Task 1: Create MediaHandlerService orchestrator** - `3ac3e46` (feat)
2. **Task 2: Wire MediaHandlerService in container and webhook controller** - `89698f0` (feat)
3. **Task 3: Add unit tests for MediaHandlerService** - `f2d4ca9` (test)

## Files Created/Modified
- `app/services/media_handler.py` - MediaHandlerService: poll qBit, compute hardlink pairs, delegate to HardlinkService/SubtitleService
- `app/container.py` - Added hardlink_service and media_handler_service providers with factory pattern
- `app/controllers/webhook.py` - Feature flag routing between legacy and new handler
- `tests/test_media_handler.py` - 13 tests: no-mapping, happy path, poll timeout, subfolder naming, pair computation, error abort

## Decisions Made
- HardlinkService wrapped in factory function (`_create_hardlink_service`) that returns None when USE_NEW_HANDLER=false or paths don't exist in dev/CI
- Subtitle hardlinks placed in same subfolder as video hardlinks for simplicity
- Polling returns empty list on timeout rather than raising TimeoutError (caller checks result and logs)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- MediaHandlerService is ready for Radarr webhook integration in Phase 5
- Feature flag allows safe testing: set USE_NEW_HANDLER=true to activate
- Existing SonarrHandlerService continues unchanged when flag is false

## Self-Check: PASSED

All 4 files verified on disk. All 3 task commits verified in git log.

---
*Phase: 04-architecture-refactor*
*Completed: 2026-02-23*
