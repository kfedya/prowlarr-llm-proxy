# Requirements: Prowlarr LLM Proxy

**Defined:** 2026-02-20
**Core Value:** Fully automatic pipeline — torrent downloaded → properly named files appear in Sonarr/Radarr library via hardlinks → no manual intervention.

## v1 Requirements

Requirements for this milestone. Each maps to roadmap phases.

### Radarr Proxy

- [x] **RADR-01**: Proxy distinguishes Radarr from Sonarr requests using Torznab `t=` parameter (movie vs tvsearch)
- [x] **RADR-02**: LLMService uses movie-context prompt when normalizing Radarr search results
- [x] **RADR-03**: LLM cache keys include media_type to prevent TV/movie collisions
- [x] **RADR-04**: TorrentMappingService stores media_type (tv or movie) per mapping

### Hardlink File Management

- [ ] **HDLK-01**: HardlinkService creates hardlinks from download dir to library dir using pathlib
- [ ] **HDLK-02**: Hardlinks follow Sonarr folder structure: {library}/{series}/Season {N}/{file}
- [ ] **HDLK-03**: Hardlinks follow Radarr folder structure: {library}/{movie} ({year})/{file}
- [ ] **HDLK-04**: Startup validation checks source and target dirs are on the same filesystem
- [ ] **HDLK-05**: Subtitle files are hardlinked alongside video files with correct naming
- [ ] **HDLK-06**: Original torrent files remain untouched in qBittorrent download dir for seeding
- [x] **HDLK-07**: Config provides DOWNLOAD_PATH, SONARR_LIBRARY_PATH, RADARR_LIBRARY_PATH settings

### Webhook Processing

- [ ] **WHOK-01**: Sonarr Grab webhook triggers hardlink creation instead of qBittorrent file renaming
- [ ] **WHOK-02**: Radarr Grab webhook endpoint exists at POST /webhook/radarr/grab
- [ ] **WHOK-03**: Radarr Grab webhook triggers hardlink creation for movie files
- [ ] **WHOK-04**: RadarrGrabWebhook Pydantic model validates Radarr webhook payloads
- [ ] **WHOK-05**: Hardlink creation triggers after torrent metadata resolves and files are created in qBittorrent (polling qBit API for file list)
- [ ] **WHOK-06**: Sonarr RescanSeries API called after torrent download completes to ensure Sonarr imports files
- [ ] **WHOK-07**: Radarr RescanMovie API called after torrent download completes to ensure Radarr imports files

### Architecture

- [ ] **ARCH-01**: SonarrHandlerService decomposed into MediaHandlerService (thin orchestrator)
- [ ] **ARCH-02**: SubtitleService extracted as focused service for subtitle matching and renaming
- [ ] **ARCH-03**: MediaHandlerService accepts media_type parameter to handle both Sonarr and Radarr
- [x] **ARCH-04**: Dead code removed (app/services/redis.py)
- [x] **ARCH-05**: TorrentMappingService schema extended with file_count field

## v2 Requirements

Deferred to future release. Tracked but not in current roadmap.

### Pack Update Tracking

- **PACK-01**: Service detects new files in tracked torrent packs via file count comparison
- **PACK-02**: Sonarr rescan triggered automatically after pack update detected
- **PACK-03**: Configurable check interval via APScheduler cron (default 6 hours)
- **PACK-04**: Manual trigger endpoint at POST /api/pack-update/check

### Open Source Preparation

- **OPEN-01**: README with installation and configuration instructions
- **OPEN-02**: Clean docker-compose.yml example for NAS deployment
- **OPEN-03**: Test files moved from root to tests/ directory
- **OPEN-04**: Hardcoded values and stale test files removed
- **OPEN-05**: Test coverage for core services (HardlinkService, MediaHandlerService, SubtitleService)

## Out of Scope

| Feature | Reason |
|---------|--------|
| Radarr-specific title heuristics (year/edition) | LLM handles this implicitly, no special code needed |
| Web UI / management dashboard | Hands-off operation is the value prop; structured logs sufficient |
| Other torrent clients (Deluge, Transmission) | Only qBittorrent; multiplies test matrix with no benefit |
| filemapper.py removal | Code cleanup milestone, separate from feature work |
| Real-time pack notifications | Polling is simpler and sufficient for the use case |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| ARCH-04 | Phase 1 | Complete |
| ARCH-05 | Phase 1 | Complete |
| HDLK-07 | Phase 1 | Complete |
| RADR-01 | Phase 2 | Complete |
| RADR-02 | Phase 2 | Complete |
| RADR-03 | Phase 2 | Complete |
| RADR-04 | Phase 2 | Complete |
| HDLK-01 | Phase 3 | Pending |
| HDLK-04 | Phase 3 | Pending |
| HDLK-06 | Phase 3 | Pending |
| ARCH-01 | Phase 4 | Pending |
| ARCH-02 | Phase 4 | Pending |
| ARCH-03 | Phase 4 | Pending |
| WHOK-01 | Phase 4 | Pending |
| HDLK-02 | Phase 5 | Pending |
| HDLK-03 | Phase 5 | Pending |
| HDLK-05 | Phase 5 | Pending |
| WHOK-02 | Phase 5 | Pending |
| WHOK-03 | Phase 5 | Pending |
| WHOK-04 | Phase 5 | Pending |
| WHOK-05 | Phase 4 | Pending |
| WHOK-06 | Phase 4 | Pending |
| WHOK-07 | Phase 5 | Pending |

**Coverage:**
- v1 requirements: 23 total
- Mapped to phases: 23
- Unmapped: 0 ✓

---
*Requirements defined: 2026-02-20*
*Last updated: 2026-02-20 after roadmap revision (added WHOK-05/06/07 for download completion + rescan)*
