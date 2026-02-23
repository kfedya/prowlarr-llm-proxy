# Prowlarr LLM Proxy

## What This Is

A proxy service for NAS that sits between Sonarr/Radarr and Prowlarr. It normalizes torrent titles via LLM so the *arr stack can correctly match releases (especially Russian/non-standard naming). It also manages post-download files — creating hardlinks with proper names into Sonarr/Radarr library folders — preserving original torrent files for seeding. Fully automated, hands-off operation on NAS.

## Core Value

Fully automatic pipeline: torrent downloaded → properly named files appear in Sonarr/Radarr library via hardlinks → original files preserved for seeding → no manual intervention.

## Requirements

### Validated (v1.0)

- ✓ LLM normalization of torrent titles during Prowlarr search
- ✓ Proxy Sonarr/Radarr → Prowlarr requests with Torznab XML transformation
- ✓ Multi-tier LLM cache (memory → Redis → OpenAI API)
- ✓ Sonarr Grab webhook processing with hardlinks
- ✓ Radarr Grab webhook processing with hardlinks
- ✓ Radarr proxy with movie-context LLM prompts (port-based media type detection)
- ✓ HardlinkService — atomic os.link, same-device validation, originals preserved
- ✓ MediaHandlerService orchestrator — TV and movie flows unified
- ✓ Hardlinks staged in `{torrent.name}/` subfolder for Remote Path Mapping
- ✓ Subtitle pipeline — multi-group disambiguation via episode-number matching
- ✓ Sonarr/Radarr rescan triggered after torrent download completes
- ✓ Torrent lookup in qBittorrent with retry/polling loop
- ✓ Redis-backed torrent mapping cache (normalized_title → original_title)
- ✓ Docker deployment on NAS (Unraid) with host networking

### Active (v1.1+)

- [ ] Torrent pack update tracking (new episodes in packs)
- [ ] Update torrents in qBittorrent when new episodes detected
- [ ] Trigger Sonarr rescan after pack update
- [ ] Open source preparation — README, documentation, docker-compose example
- [ ] Code cleanup — remove hardcoded values, improve test coverage

### Out of Scope

- Mobile app / web UI — management through Sonarr/Radarr
- Support for other torrent clients — qBittorrent only

## Context

- **v1.0 shipped 2026-02-23** — all webhook flows validated E2E on NAS
- Runs on NAS (Unraid, 192.168.10.199), deployed via Docker (`prowlarr-llm-proxy` container)
- Ports: 8585→Sonarr, 8586→Prowlarr, 8587→Radarr
- Stack: FastAPI + dependency-injector + Redis + httpx + openai
- `USE_NEW_HANDLER=true` in production — MediaHandlerService active
- Hardlinks staged at `/data/downloads/hardlinks/{torrent.name}/` → Sonarr/Radarr import via Remote Path Mapping
- `deploy.sh <branch>` — git pull + docker build + run on NAS
- Working branch: `get-shit-done` (not merged to main yet)

## Constraints

- **Tech stack**: Python, FastAPI, Redis — no changes planned
- **Deployment**: Docker on NAS (Unraid) — must work with docker run
- **Filesystem**: Hardlinks require download dir and library to be on the same filesystem/partition
- **Dependencies**: Sonarr, Radarr, Prowlarr, qBittorrent — external services, we only control the proxy

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Hardlinks instead of qBit renaming | Preserves original files for seeding | ✓ Working — inode count verified |
| LLM for title normalization | Russian/non-standard names don't match without AI | ✓ Good |
| Redis for caching | Survives restarts, fast lookup | ✓ Good |
| Port-based media type detection | Radarr sends `t=search` not `t=movie` | ✓ Fixed Radarr prompt routing |
| torrent.name as hardlink subfolder | Remote Path Mapping needs content_path match | ✓ Required for *arr import |
| Episode-number subtitle matching | No LLM tokens wasted, handles multi-group | ✓ Group collision eliminated |

---
*Last updated: 2026-02-23 after v1.0 milestone completion*
