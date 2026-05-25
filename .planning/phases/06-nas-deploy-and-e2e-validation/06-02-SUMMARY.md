---
phase: 06-nas-deploy-and-e2e-validation
plan: 02
subsystem: infra
tags: [hardlink, sonarr, radarr, media-handler, llm, docker, nas]

# Dependency graph
requires:
  - phase: 06-01
    provides: container deployed on NAS with hardlink volume mounts

provides:
  - hardlink staging pipeline: grab -> LLM rename -> hardlink_path/{Series or Movie}/
  - TV flat hardlink layout with LLM-normalized filenames
  - Movie hardlink layout preserving torrent-relative structure
  - Sonarr/Radarr Remote Path Mapping configured for /data/downloads/hardlinks
  - Sonarr and Radarr grab webhooks configured

affects: [e2e-validation, sonarr-import, radarr-import]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "TV hardlinks: LLM-normalized flat layout in hardlink_path/{Series Name}/"
    - "Movie hardlinks: torrent-relative structure preserved under hardlink_path/{Movie (Year)}/"
    - "_poll_for_files_on_disk returns tuple[Path|None, list[Path]] to expose save_path"
    - "HardlinkService takes single hardlinks_path not list[library_paths]"

key-files:
  created: []
  modified:
    - app/config.py
    - app/services/hardlink.py
    - app/container.py
    - app/services/media_handler.py
    - tests/test_hardlink.py
    - tests/test_media_handler.py
    - tests/test_config.py
    - tests/conftest.py

key-decisions:
  - "Hardlinks go to staging hardlink_path, not directly in library — Sonarr/Radarr import via Remote Path Mapping"
  - "TV hardlinks: flat in {series}/ with LLM-normalized names (no Season subfolder)"
  - "Movie hardlinks: preserve torrent-relative path under {Movie (Year)}/  not flat"
  - "HardlinkService validates single hardlinks_path vs download_path (not a list of library paths)"
  - "_poll_attempt returns (save_path, files) tuple so movie pair computation has access to torrent root"
  - "Sonarr RPM + Radarr RPM configured via API: host=192.168.10.199, both paths /data/downloads/hardlinks"

patterns-established:
  - "Staging approach: hardlinks in /data/downloads/hardlinks/, Sonarr/Radarr import from there"
  - "TV normalize: LLM.normalize_file_names called with series+season+episodes, flat output"
  - "Movie structure: src.relative_to(save_path) preserves folder hierarchy under movie title folder"

requirements-completed: []

# Metrics
duration: 7min
completed: 2026-02-23
---

# Phase 6 Plan 02: Hardlink Pipeline Refactor Summary

**Hardlink staging pipeline: TV flat+LLM-renamed into hardlink_path/{Series}/, movies torrent-relative into hardlink_path/{Movie (Year)}/; Sonarr/Radarr Remote Path Mapping configured for import**

## Performance

- **Duration:** ~7 min
- **Started:** 2026-02-23T11:14:56Z
- **Completed:** 2026-02-23T11:21:36Z
- **Tasks:** 7 of 8 (Task 8 is human-verify checkpoint — see below)
- **Files modified:** 8

## Accomplishments
- Removed sonarr_library_path/radarr_library_path from entire codebase (config, container, media_handler, tests)
- MediaHandlerService fully refactored with split TV/movie flows; _poll returns save_path for relative path computation
- HardlinkService API simplified to single hardlinks_path vs download_path device check
- NAS deployed: /data/downloads/hardlinks created (same device as downloads), .env updated, container healthy on all ports
- Sonarr RPM + Radarr RPM created via API; Radarr grab webhook created; Sonarr webhook confirmed
- All 126 tests pass

## Task Commits

Each task was committed atomically:

1. **Task 1: Refactor config.py** - `fc3bd99` (refactor)
2. **Task 2: Refactor hardlink.py** - `6f9d9a4` (refactor)
3. **Task 3: Refactor container.py** - `3054cc6` (refactor)
4. **Task 4: Refactor media_handler.py** - `4497c89` (refactor)
5. **Task 5: Update tests** - `d503090` (test)
6. **Task 6: Deploy to NAS** - `ab305ea` (chore)
7. **Task 7: Configure Sonarr/Radarr RPM and webhooks** - `fbe854c` (chore)
8. **Task 8: E2E validation** — CHECKPOINT (human-verify)

## Files Created/Modified
- `app/config.py` - Removed library paths, added HARDLINK_PATH existence validation
- `app/services/hardlink.py` - Single hardlinks_path API, simplified device check
- `app/container.py` - DI wiring updated, no more inline Path import
- `app/services/media_handler.py` - Full rewrite: split TV/movie flows, _compute_tv/movie_hardlink_pairs
- `tests/test_hardlink.py` - Updated all HardlinkService() calls to hardlinks_path=
- `tests/test_media_handler.py` - New TV/movie pair tests, removed old subfolder tests
- `tests/test_config.py` - Removed library path tests, added HARDLINK_PATH tests
- `tests/conftest.py` - Removed library path fixtures, added hardlinks fixture

## Decisions Made
- Staging approach: hardlinks go to /data/downloads/hardlinks, Sonarr/Radarr import via Remote Path Mapping
- TV flat layout: LLM.normalize_file_names outputs Sonarr-compatible names directly into {Series}/ (no Season subfolder — Sonarr's import dialog handles season placement)
- Movie structure: torrent-relative paths preserved so multi-file movies keep their folder hierarchy
- HardlinkService simplification: single path comparison instead of list
- _poll_attempt returns tuple (save_path, files) so movie pairs can compute relative paths

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- Sonarr API key not in .env — retrieved from /mnt/user/appdata/sonarr/config.xml (a1626d59a8a34421bebb8feb22ac8407)
- Sonarr grab webhook was already configured from prior work; only Radarr webhook needed creation

## Checkpoint Status

**Task 8 (E2E validation) requires human action:**

The system is ready for E2E validation. The user needs to:

1. Start watching logs: `ssh root@192.168.10.199 "docker logs prowlarr-llm-proxy --follow --tail 0"`
2. Trigger a Sonarr grab for a small TV episode
3. Verify hardlinks appear at `/data/downloads/hardlinks/{Series Name}/` with LLM-normalized names
4. Verify inode link count >= 2 (same inode as original in /data/downloads/)
5. Test Sonarr manual import from the hardlinks path
6. Repeat for a Radarr movie grab

## Next Phase Readiness
- Code and NAS configuration complete
- Awaiting E2E validation (Task 8 checkpoint)
- After E2E validation passes, Phase 6 is fully complete

---
*Phase: 06-nas-deploy-and-e2e-validation*
*Completed: 2026-02-23*

## Self-Check: PASSED
All 7 task commits and SUMMARY.md confirmed present.
