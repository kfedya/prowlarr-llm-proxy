---
phase: 02-radarr-proxy
plan: 01
subsystem: api
tags: [openai, llm, radarr, torznab, cache, redis]

# Dependency graph
requires:
  - phase: 01-foundation
    provides: "MediaType enum, TorrentMapping with media_type field"
provides:
  - "MOVIE_SYSTEM_PROMPT constant for Radarr title parsing"
  - "PROMPTS dict mapping MediaType to system prompt"
  - "media_type-aware cache keys in LLMService and TorrentMappingService"
affects: [02-radarr-proxy, 03-hardlink]

# Tech tracking
tech-stack:
  added: []
  patterns: ["media_type threading through LLM and cache layers"]

key-files:
  created:
    - tests/test_llm.py
  modified:
    - app/services/llm.py
    - app/services/torrent_mapping.py
    - tests/test_torrent_mapping.py

key-decisions:
  - "Independent movie prompt, not shared base with TV -- cleaner separation per user constraint"
  - "media_type param is str in TorrentMappingService (callers pass enum.value) for simple interface"

patterns-established:
  - "PROMPTS dict for media-type prompt selection"
  - "Cache key format: {media_type}|{title}|{series_name} for both in-memory and Redis"

requirements-completed: [RADR-02, RADR-03]

# Metrics
duration: 3min
completed: 2026-02-20
---

# Phase 2 Plan 1: Movie Prompt and Cache Key Isolation Summary

**MOVIE_SYSTEM_PROMPT with Radarr-specific rules (year, edition, collection packs) and media_type-prefixed cache keys preventing TV/movie collisions**

## Performance

- **Duration:** 3 min
- **Started:** 2026-02-20T20:57:59Z
- **Completed:** 2026-02-20T21:01:00Z
- **Tasks:** 3
- **Files modified:** 4

## Accomplishments
- Added MOVIE_SYSTEM_PROMPT with Radarr-specific parsing rules (year extraction, edition handling, collection packs)
- Threaded media_type through LLMService._parse_batch() and parse_items_batch() for prompt selection and cache isolation
- Updated TorrentMappingService normalized cache keys with media_type prefix
- 24 tests passing covering prompt selection, label formatting, and cache key isolation

## Task Commits

Each task was committed atomically:

1. **Task 1: Add MOVIE_SYSTEM_PROMPT and media_type-aware prompt selection** - `5c28e46` (feat)
2. **Task 2: Add media_type to TorrentMappingService cache keys** - `810e929` (feat)
3. **Task 3: Write tests for prompt selection and cache key isolation** - `7b7e262` (test)

## Files Created/Modified
- `app/services/llm.py` - Added MOVIE_SYSTEM_PROMPT, PROMPTS dict, media_type threading through _parse_batch and parse_items_batch, updated TorrentItem.to_prompt() with Movie:/Series: labels
- `app/services/torrent_mapping.py` - Updated _make_normalized_cache_key, store_normalized_cache, get_normalized_cache with media_type parameter
- `tests/test_llm.py` - New test file with prompt selection, label format, and cache key isolation tests
- `tests/test_torrent_mapping.py` - Added TestNormalizedCacheKey class with Redis mock tests

## Decisions Made
- Independent movie prompt (not shared base with TV) per user locked decision
- media_type parameter is str in TorrentMappingService to keep interface simple; callers pass enum.value
- TorrentItem.series_name dual-purpose (holds movie name for movies) with comment explaining this

## Deviations from Plan

None - plan executed exactly as written.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- MOVIE_SYSTEM_PROMPT and cache key isolation ready for proxy routing (02-02)
- ProxyService needs _get_media_type() and media_type threading through _process_torznab_response() (02-02 scope)

---
*Phase: 02-radarr-proxy*
*Completed: 2026-02-20*
