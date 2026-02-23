---
phase: 05-radarr-webhook-and-movie-hardlinks
plan: 02
subsystem: hardlinks, subtitles
tags: [subtitle, language-detection, iso-639-2, hardlink, sonarr]

# Dependency graph
requires:
  - phase: 05-radarr-webhook-and-movie-hardlinks
    provides: MediaHandlerService with _process_subtitles, SubtitleService
provides:
  - Subtitle language detection from filenames (2-letter, 3-letter, full names)
  - TV subtitle renaming with ISO 639-2 codes in hardlink destinations
  - LANGUAGE_MAP constant for subtitle language resolution
affects: [deployment, docker-compose]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "LANGUAGE_MAP dict for ISO 639-1/2/full-name -> ISO 639-2 resolution"
    - "Static methods on SubtitleService for language detection (no instance state needed)"
    - "VIDEO_EXTENSIONS constant for identifying primary video file in torrent"

key-files:
  created:
    - tests/test_subtitle_language.py
  modified:
    - app/services/subtitle.py
    - app/services/media_handler.py

key-decisions:
  - "Language map as module-level dict constant (not instance attribute) for static method access"
  - "Unknown language subtitles keep original filename (no .und suffix or guessing)"
  - "Subtitle renaming uses first video file in torrent as base name"

patterns-established:
  - "SubtitleService.detect_language_from_filename for language extraction from any filename pattern"
  - "SubtitleService.rename_subtitle_with_language for building destination subtitle names"

requirements-completed: [HDLK-05]

# Metrics
duration: 2min
completed: 2026-02-23
---

# Phase 5 Plan 2: Subtitle Language Detection and Renaming Summary

**ISO 639-2 language detection from subtitle filenames with automatic renaming in TV hardlink flow (.en.srt -> .eng.srt)**

## Performance

- **Duration:** 2 min
- **Started:** 2026-02-23T00:27:00Z
- **Completed:** 2026-02-23T00:28:46Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- LANGUAGE_MAP with 59 entries covering 2-letter, 3-letter, and full language name mappings
- detect_language_from_filename extracts language from subtitle filenames (case-insensitive)
- rename_subtitle_with_language builds Sonarr-compatible subtitle names using video stem
- TV _process_subtitles now finds primary video file and renames subtitles with language codes
- Unknown language subtitles keep original filenames (no forced suffix)
- 128 tests all passing (19 new subtitle language tests)

## Task Commits

Each task was committed atomically:

1. **Task 1: Add language detection to SubtitleService** - `4f68ce1` (feat)
2. **Task 2: Integrate subtitle renaming in TV hardlink flow and add tests** - `ed8de96` (feat)

## Files Created/Modified
- `app/services/subtitle.py` - LANGUAGE_MAP constant, detect_language_from_filename, rename_subtitle_with_language
- `app/services/media_handler.py` - VIDEO_EXTENSIONS constant, updated _process_subtitles with language-aware renaming
- `tests/test_subtitle_language.py` - 19 tests covering detection (2-letter, 3-letter, full name, unknown, case) and renaming

## Decisions Made
- Language map as module-level dict constant for static method access without instance
- Unknown language subtitles keep original filename unchanged (per user decision)
- First video file in torrent file list used as base name for renamed subtitles

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Phase 5 fully complete: Radarr webhook, library-path hardlinks, subtitle language renaming
- All hardlink requirements (HDLK-02 through HDLK-05) and webhook requirements (WHOK-02 through WHOK-04) implemented
- Ready for deployment and integration testing

---
*Phase: 05-radarr-webhook-and-movie-hardlinks*
*Completed: 2026-02-23*
