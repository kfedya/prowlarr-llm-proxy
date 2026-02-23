# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-20)

**Core value:** Fully automatic pipeline — torrent downloaded → properly named files appear in Sonarr/Radarr library via hardlinks → no manual intervention.
**Current focus:** Phase 6 - NAS Deploy and E2E Validation

## Current Position

Phase: 6 of 6 (NAS Deploy and E2E Validation)
Plan: 2 of 2 in current phase (Tasks 1-7 done, Task 8 awaiting human-verify)
Status: 06-02 at checkpoint — hardlink pipeline refactored, NAS deployed, awaiting E2E validation
Last activity: 2026-02-23 — Completed 06-02 tasks 1-7, stopped at Task 8 (E2E human-verify checkpoint)

Progress: [█████████░] 95%

## Performance Metrics

**Velocity:**
- Total plans completed: 9
- Average duration: 2.6 min
- Total execution time: 0.4 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01-foundation | 2 | 3 min | 1.5 min |
| 02-radarr-proxy | 2 | 5 min | 2.5 min |

**Recent Trend:**
- Last 5 plans: —
- Trend: —

*Updated after each plan completion*
| Phase 01-foundation P02 | 2min | 2 tasks | 6 files |
| Phase 02-radarr-proxy P01 | 3min | 3 tasks | 4 files |
| Phase 02-radarr-proxy P02 | 2min | 2 tasks | 2 files |
| Phase 03-hardlinkservice P01 | 2min | 2 tasks | 2 files |
| Phase 04 P01 | 2min | 2 tasks | 4 files |
| Phase 04 P02 | 4min | 3 tasks | 4 files |
| Phase 05 P01 | 5min | 3 tasks | 7 files |
| Phase 05 P02 | 2min | 2 tasks | 3 files |
| Phase 06 P01 | 5min | 3 tasks | 1 files |
| Phase 06 P02 | 7min | 7 tasks | 8 files |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- 01-01: Used rm (not git rm) for untracked stale files; added root-anchored .gitignore patterns for scratch files
- Hardlinks instead of qBit renaming: preserves original files for seeding, chosen over copy fallback
- Radarr/Sonarr distinction: use `t=` Torznab parameter (not port) as primary discriminator
- Pack update tracking deferred to v2 (APScheduler dependency, state machine complexity)
- [Phase 01-02]: Used str,Enum mixin for MediaType so Pydantic v2 serializes to tv/movie strings
- [Phase 01-02]: Path validation lenient for default /downloads path to avoid failures in dev/CI
- [Phase 02-01]: Independent movie prompt (not shared base with TV) per user constraint
- [Phase 02-01]: media_type param is str in TorrentMappingService for simple interface
- [Phase 02-02]: Route purely on t= parameter; t=search defaults to TV preserving existing behavior
- [Phase 02.1-01]: PORT_MEDIA_TYPES env var overrides media type for ambiguous t=search by listen port
- [Phase 02.1-01]: NAS repo path is /mnt/user/appdata/prowlarr-llm-proxy/ (not /root/)
- [Phase 02.1-01]: ROUTES port 8587 points to Prowlarr (9696) not Radarr (7878) — proxy intercepts Torznab
- [Phase 03-01]: Used os.link(src, dst) over Path.hardlink_to; frozenset ALLOWED_EXTENSIONS; continue+report partial failure; constructor-time cross-device validation
- [Phase 04-01]: SubtitleService uses frozenset for SUBTITLE_EXTENSIONS; hardlink_path defaults only when use_new_handler=True
- [Phase 04-02]: HardlinkService wrapped in factory function for dev/CI compatibility; subtitle hardlinks in same subfolder as video; polling returns empty list on timeout
- [Phase 05-01]: No feature flag for Radarr endpoint -- direct to MediaHandlerService; no rescan API call (hardlinks fill in-place)
- [Phase 05-01]: TV nested subfolder format {Title}/Season {NN}; movies hardlink ALL files (filter_extensions=False); _sanitize_title for filesystem-safe paths
- [Phase 05-02]: LANGUAGE_MAP as module-level dict; unknown language subtitles keep original filename; first video file used as rename base
- [Phase 06-01]: NAS paths: /data/downloads (not /data/torrents), /data/tv and /data/movies (not /data/media/*); single mount /mnt/user/data:/data
- [Phase 06-02]: Hardlinks go to staging hardlink_path not directly in library -- Sonarr/Radarr import via Remote Path Mapping
- [Phase 06-02]: TV hardlinks flat in {series}/ with LLM-normalized names; movies preserve torrent-relative structure under {Movie (Year)}/
- [Phase 06-02]: HardlinkService: single hardlinks_path vs download_path device check (not list of library paths)

### Pending Todos

None yet.

### Roadmap Evolution

- Phase 02.1 inserted after Phase 2: Deploy and test Radarr proxy on NAS (URGENT)

### Blockers/Concerns

- Phase 5: `RadarrGrabWebhook` Pydantic model field names derived from Radarr source, not verified against a live instance — must validate before implementation
- Phase 3: Hardlink same-filesystem constraint requires specific Docker Compose volume config — document in docker-compose.yml before phase ships

## Session Continuity

Last session: 2026-02-23
Stopped at: 06-02-PLAN.md Task 8 (checkpoint:human-verify — E2E validation requires triggering real Sonarr/Radarr grab)
Resume file: None
