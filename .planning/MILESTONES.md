# Milestones

## v1.0 MVP (Shipped: 2026-02-23)

**Phases completed:** 7 phases (1–6 + 2.1 inserted), 13 plans
**Timeline:** 2026-01-07 → 2026-02-23
**Codebase:** ~6,341 lines Python (app/ + tests/)

**Key accomplishments:**
1. Radarr movie search proxy — movie-context LLM prompts, cache-key isolation preventing TV/movie collisions
2. HardlinkService — atomic filesystem hardlinks via `os.link`, same-device validation at startup, original torrents preserved for seeding
3. MediaHandlerService — decomposed SonarrHandlerService monolith into thin orchestrator + SubtitleService; qBittorrent rename API replaced with hardlinks
4. Radarr grab webhook — polls qBit for metadata, hardlinks into staging path, movie/TV layout both handled by one orchestrator
5. Subtitle pipeline — ISO 639-2 language detection, multi-group disambiguation without LLM (episode-number matching), incremental creation during download
6. Full NAS E2E — container on Unraid, Remote Path Mapping wired in Sonarr/Radarr, torrent.name subfolder for correct import path resolution

**Known gaps (WHOK-06, WHOK-07):**
- Sonarr/Radarr rescan API calls intentionally not implemented — in-place hardlinks + *arr filesystem polling makes explicit rescans unnecessary (decided Phase 5)

**Archive:**
- `.planning/milestones/v1.0-ROADMAP.md`
- `.planning/milestones/v1.0-REQUIREMENTS.md`

---
