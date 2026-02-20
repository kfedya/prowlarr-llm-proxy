# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-20)

**Core value:** Fully automatic pipeline — torrent downloaded → properly named files appear in Sonarr/Radarr library via hardlinks → no manual intervention.
**Current focus:** Phase 2 - Radarr Proxy

## Current Position

Phase: 2 of 5 (Radarr Proxy)
Plan: 1 of 2 in current phase
Status: In progress
Last activity: 2026-02-20 — Completed 02-01 (movie prompt and cache key isolation)

Progress: [███░░░░░░░] 30%

## Performance Metrics

**Velocity:**
- Total plans completed: 3
- Average duration: 2.0 min
- Total execution time: 0.1 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01-foundation | 2 | 3 min | 1.5 min |
| 02-radarr-proxy | 1 | 3 min | 3.0 min |

**Recent Trend:**
- Last 5 plans: —
- Trend: —

*Updated after each plan completion*
| Phase 01-foundation P02 | 2min | 2 tasks | 6 files |
| Phase 02-radarr-proxy P01 | 3min | 3 tasks | 4 files |

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

### Pending Todos

None yet.

### Blockers/Concerns

- Phase 5: `RadarrGrabWebhook` Pydantic model field names derived from Radarr source, not verified against a live instance — must validate before implementation
- Phase 3: Hardlink same-filesystem constraint requires specific Docker Compose volume config — document in docker-compose.yml before phase ships

## Session Continuity

Last session: 2026-02-20
Stopped at: Completed 02-01-PLAN.md (movie prompt and cache key isolation)
Resume file: None
