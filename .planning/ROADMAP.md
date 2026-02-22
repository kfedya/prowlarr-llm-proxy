# Roadmap: Prowlarr LLM Proxy

## Overview

Starting from a working Sonarr proxy with LLM normalization, this milestone extends the system in three directions: Radarr proxy support (movie-context LLM normalization), hardlink-based file management (replacing destructive qBittorrent renaming to preserve seeding), and a decoupled architecture that makes both usable together. The path is additive and surgical — the existing webhook interface stays stable while internals are decomposed and extended.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: Foundation** - Dead code removed and schema/config primitives extended to support media types and hardlinks
- [ ] **Phase 2: Radarr Proxy** - Movie searches return LLM-normalized titles using movie-context prompts
- [ ] **Phase 3: HardlinkService** - Isolated filesystem service creates hardlinks with startup validation and no side effects on torrent files
- [ ] **Phase 4: Architecture Refactor** - Monolith decomposed into focused services; Sonarr webhook creates hardlinks after metadata, triggers rescan after download
- [ ] **Phase 5: Radarr Webhook and Movie Hardlinks** - Radarr grab webhook creates hardlinks after metadata, triggers Radarr rescan after download

## Phase Details

### Phase 1: Foundation
**Goal**: Schema, config, and dead code are in the state required for all subsequent phases — no collision between TV and movie data, no stale files, correct config keys present
**Depends on**: Nothing (first phase)
**Requirements**: ARCH-04, ARCH-05, HDLK-07
**Success Criteria** (what must be TRUE):
  1. `app/services/redis.py` dead file no longer exists in the codebase
  2. TorrentMappingService Redis schema includes `media_type` and `file_count` fields with backward-compatible defaults
  3. Config exposes `DOWNLOAD_PATH`, `SONARR_LIBRARY_PATH`, and `RADARR_LIBRARY_PATH` settings that the application reads on startup
  4. Existing Sonarr webhook processing continues to work after schema changes (no regressions)
**Plans:** 2 plans
Plans:
- [ ] 01-01-PLAN.md -- Dead code removal and .gitignore cleanup
- [ ] 01-02-PLAN.md -- Schema extension (media_type, file_count) + path config + tests

### Phase 2: Radarr Proxy
**Goal**: Radarr movie searches are normalized by the LLM using a movie-context prompt; TV and movie cache entries cannot collide
**Depends on**: Phase 1
**Requirements**: RADR-01, RADR-02, RADR-03, RADR-04
**Success Criteria** (what must be TRUE):
  1. A Torznab request with `t=movie` is routed through the movie-context LLM prompt, not the TV prompt
  2. A Torznab request with `t=tvsearch` continues to use the TV-context prompt unchanged
  3. LLM cache keys for the same title differ between `media_type=tv` and `media_type=movie` (no cross-contamination)
  4. TorrentMappingService stores `media_type` alongside each mapping entry
**Plans:** 2 plans
Plans:
- [ ] 02-01-PLAN.md -- Movie prompt, prompt selection, cache key isolation (LLM + mapping services)
- [ ] 02-02-PLAN.md -- Proxy media type detection and integration wiring

### Phase 02.1: Deploy and test Radarr proxy on NAS (INSERTED)

**Goal:** Phase 2 Radarr proxy code is deployed on the NAS with zero downtime, movie and TV searches validated via curl, and Radarr configured to use the proxy
**Depends on:** Phase 2
**Plans:** 1 plan

Plans:
- [x] 02.1-01-PLAN.md -- Zero-downtime deploy, search validation, and Radarr indexer config (2026-02-23)

### Phase 3: HardlinkService
**Goal**: A standalone, fully testable service creates hardlinks from download dir to library dir with explicit failure on cross-device setups
**Depends on**: Phase 1
**Requirements**: HDLK-01, HDLK-04, HDLK-06
**Success Criteria** (what must be TRUE):
  1. `HardlinkService.create_hardlink(src, dst)` creates a hardlink at `dst` pointing to the same inode as `src`
  2. Original torrent files in the download directory are untouched after hardlink creation (confirmed via inode check)
  3. Startup validation raises a clear error if `DOWNLOAD_PATH` and library paths are on different block devices, and the service does not accept traffic
  4. `HardlinkService` has no dependency on qBittorrent, Sonarr, or any external API — it can be unit-tested with `tmp_path` alone
**Plans:** 1 plan

Plans:
- [ ] 03-01-PLAN.md -- HardlinkService TDD: service implementation + comprehensive tests

### Phase 4: Architecture Refactor
**Goal**: `SonarrHandlerService` monolith is replaced by a thin `MediaHandlerService` orchestrator and focused collaborators; Sonarr webhook flow polls for metadata, creates hardlinks early, waits for download, triggers rescan
**Depends on**: Phase 3
**Requirements**: ARCH-01, ARCH-02, ARCH-03, WHOK-01, WHOK-05, WHOK-06
**Success Criteria** (what must be TRUE):
  1. `SonarrHandlerService` no longer exists; `MediaHandlerService` handles the Sonarr grab webhook at the same endpoint (`POST /webhook/sonarr/grab`) with no change to callers
  2. `SubtitleService` is an independent, injectable service that can be tested without a qBittorrent or Sonarr connection
  3. After a Sonarr grab event, the service polls qBittorrent until torrent metadata resolves and files are created, then creates hardlinks in the Sonarr library path — qBittorrent file rename API is no longer called
  4. After torrent download completes, `MediaHandlerService` calls the Sonarr `RescanSeries` API so Sonarr imports the now-complete files
  5. `MediaHandlerService` accepts a `media_type` parameter so the same orchestration logic handles both TV and movie workflows
**Plans:** 2 plans
Plans:
- [ ] 04-01-PLAN.md -- SubtitleService extraction + config settings (USE_NEW_HANDLER, HARDLINK_PATH)
- [ ] 04-02-PLAN.md -- MediaHandlerService orchestrator + webhook feature flag wiring

### Phase 5: Radarr Webhook and Movie Hardlinks
**Goal**: A Radarr grab webhook polls for metadata, creates hardlinks into the Radarr library with correct movie folder structure, waits for download, triggers Radarr rescan; subtitles follow alongside video files
**Depends on**: Phase 2, Phase 4
**Requirements**: WHOK-02, WHOK-03, WHOK-04, WHOK-07, HDLK-02, HDLK-03, HDLK-05
**Success Criteria** (what must be TRUE):
  1. `POST /webhook/radarr/grab` endpoint exists and accepts Radarr grab webhook payloads validated by a `RadarrGrabWebhook` Pydantic model
  2. After a Radarr grab event, the service polls qBittorrent until metadata resolves and files are created, then hardlinks appear in the Radarr library at `{RADARR_LIBRARY_PATH}/{Movie Title} ({Year})/`
  3. After torrent download completes, `MediaHandlerService` calls the Radarr `RescanMovie` API so Radarr imports the now-complete files
  4. After a Sonarr grab event, a hardlink appears in the Sonarr library at `{SONARR_LIBRARY_PATH}/{Series}/Season {N}/`
  5. Subtitle files are hardlinked alongside their video files with correct language suffix naming
  6. Sonarr and Radarr webhook flows are independent — a failure in one does not affect processing of the other
**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Foundation | 0/2 | Planned | - |
| 2. Radarr Proxy | 0/2 | Planned | - |
| 3. HardlinkService | 0/? | Not started | - |
| 4. Architecture Refactor | 0/? | Not started | - |
| 5. Radarr Webhook and Movie Hardlinks | 0/? | Not started | - |
