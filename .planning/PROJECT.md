# Prowlarr LLM Proxy

## What This Is

A proxy service for NAS that sits between Sonarr/Radarr and Prowlarr. It normalizes torrent titles via LLM so the *arr stack can correctly match releases (especially Russian/non-standard naming). It also manages post-download files — creating hardlinks with proper names into Sonarr/Radarr library folders — and tracks torrent pack updates for ongoing series. Fully automated, hands-off operation on NAS.

## Core Value

Fully automatic pipeline: torrent downloaded → properly named files appear in Sonarr/Radarr library via hardlinks → pack updates are pulled automatically with no manual intervention.

## Requirements

### Validated

- ✓ LLM normalization of torrent titles during Prowlarr search — existing
- ✓ Proxy Sonarr → Prowlarr requests with Torznab XML transformation — existing
- ✓ Multi-tier LLM cache (memory → Redis → OpenAI API) — existing
- ✓ Sonarr Grab webhook processing — existing
- ✓ Torrent lookup in qBittorrent with retry logic — existing
- ✓ File renaming in qBittorrent via API — existing
- ✓ Subtitle processing (matching to video, renaming) — existing
- ✓ Redis-backed torrent mapping cache (normalized_title → original_title) — existing
- ✓ Docker deployment on NAS (Unraid) — existing
- ✓ Health checks (Kubernetes probes) — existing

### Active

- [ ] Radarr support — proxy with LLM prompts for movies
- [ ] Distinguish Radarr vs Sonarr requests (needs research — by port/upstream)
- [ ] Hardlinks instead of direct renaming in qBittorrent
- [ ] qBittorrent downloads to a single folder, hardlinks created in Sonarr/Radarr library
- [ ] Hardlinks with proper folder structure (same as current file management)
- [ ] Hardlinks for Radarr (movies)
- [ ] Torrent pack update tracking (new episodes in packs)
- [ ] Update torrents in qBittorrent when new episodes detected
- [ ] Trigger Sonarr rescan after pack update
- [ ] Update check mechanism (needs research — cron vs release date based)
- [ ] Architecture refactoring — decouple tightly bound services
- [ ] Open source preparation — README, documentation, docker-compose
- [ ] Code cleanup — remove hardcoded values, secrets, test files
- [ ] Test coverage for contributor confidence

### Out of Scope

- Radarr webhook processing (grab event) — only proxy + hardlinks for Radarr at this stage
- Mobile app / web UI — management through Sonarr/Radarr
- Support for other torrent clients — qBittorrent only

## Context

- Runs on NAS (Unraid), deployed via Docker Compose
- Existing stack: FastAPI + dependency-injector + Redis + httpx + openai
- sonarr_handler.py is a monolithic orchestrator — handles webhooks, files, subtitles, bonus files all in one place
- Services are too tightly coupled to each other
- Stale test/utility files in project root (test_*.py, *.md docs)
- ROUTES config already supports port → upstream URL mapping
- Current file management directly renames files in qBittorrent — needs to be replaced with hardlinks
- Hardlinks preserve original torrent files for seeding while providing properly named files to *arr

## Constraints

- **Tech stack**: Python, FastAPI, Redis — no changes planned
- **Deployment**: Docker on NAS (Unraid) — must work with docker-compose up
- **Filesystem**: Hardlinks require download dir and library to be on the same filesystem/partition
- **Dependencies**: Sonarr, Radarr, Prowlarr, qBittorrent — external services, we only control the proxy

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Hardlinks instead of qBit renaming | Preserves original files for seeding, doesn't break torrent | — Pending |
| LLM for title normalization | Russian/non-standard torrent names don't match without AI | ✓ Good |
| Redis for caching | Survives restarts, fast lookup | ✓ Good |
| Radarr/Sonarr distinction | Needs research — by port via ROUTES or other mechanism | — Pending |
| Pack update check mechanism | Needs research — cron, release date based, or qBit API | — Pending |

---
*Last updated: 2026-02-20 after initialization*
