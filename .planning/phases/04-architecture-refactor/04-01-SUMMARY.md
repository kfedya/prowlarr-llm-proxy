---
phase: 04-architecture-refactor
plan: 01
subsystem: services
tags: [subtitle, llm, dependency-injection, pydantic-settings]

requires:
  - phase: 01-foundation
    provides: "Config, Container, LLMService base"
provides:
  - "SubtitleService with filter and LLM-match methods"
  - "use_new_handler and hardlink_path config settings"
  - "subtitle_service DI provider"
affects: [04-02-mediahandler]

tech-stack:
  added: []
  patterns: ["frozenset for immutable extension sets", "optional LLM dependency with graceful fallback"]

key-files:
  created: [app/services/subtitle.py, tests/test_subtitle.py]
  modified: [app/config.py, app/container.py]

key-decisions:
  - "SubtitleService uses frozenset for SUBTITLE_EXTENSIONS (immutable, hashable)"
  - "hardlink_path defaults to download_path/hardlinks only when use_new_handler=True"

patterns-established:
  - "Service with optional LLM: accept llm_service=None, return empty on None"

requirements-completed: [ARCH-02]

duration: 2min
completed: 2026-02-23
---

# Phase 04 Plan 01: SubtitleService Extraction Summary

**SubtitleService extracted as independent service with filter/match methods, plus use_new_handler and hardlink_path config settings**

## Performance

- **Duration:** 2 min
- **Started:** 2026-02-22T23:31:08Z
- **Completed:** 2026-02-22T23:32:46Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- SubtitleService independently testable without qBittorrent or Sonarr dependencies
- Config ready for MediaHandlerService (use_new_handler toggle, hardlink_path with smart default)
- 10 unit tests covering all filter edge cases and LLM delegation
- Full test suite (77 tests) passes with no regressions

## Task Commits

Each task was committed atomically:

1. **Task 1: Create SubtitleService and add config settings** - `95f4e86` (feat)
2. **Task 2: Add unit tests for SubtitleService** - `34244bc` (test)

## Files Created/Modified
- `app/services/subtitle.py` - SubtitleService with filter_subtitle_files and match_subtitles_to_videos
- `app/config.py` - Added use_new_handler (bool) and hardlink_path (Path|None) settings
- `app/container.py` - Added subtitle_service Singleton provider
- `tests/test_subtitle.py` - 10 unit tests for SubtitleService

## Decisions Made
- Used frozenset for SUBTITLE_EXTENSIONS (consistent with HardlinkService pattern from Phase 03)
- hardlink_path only auto-derives when use_new_handler is True (avoids unnecessary path creation)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- SubtitleService ready for consumption by MediaHandlerService (Plan 02)
- Config settings (use_new_handler, hardlink_path) ready for new handler wiring

---
*Phase: 04-architecture-refactor*
*Completed: 2026-02-23*
