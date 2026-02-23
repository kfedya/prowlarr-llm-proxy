---
phase: 06-nas-deploy-and-e2e-validation
plan: 01
subsystem: infra
tags: [docker, deploy, volume-mount, hardlink, nas]

# Dependency graph
requires:
  - phase: 05-radarr-webhook-and-movie-hardlinks
    provides: "Radarr/Sonarr webhook endpoints and hardlink pipeline code"
provides:
  - "Running container on NAS with hardlink-capable volume mount (/mnt/user/data:/data)"
  - "USE_NEW_HANDLER=true active in production"
  - "All library paths configured (DOWNLOAD_PATH, SONARR_LIBRARY_PATH, RADARR_LIBRARY_PATH)"
  - "Rollback documentation (commit hash + .env backup)"
affects: [06-02-PLAN]

# Tech tracking
tech-stack:
  added: []
  patterns: ["Single volume mount for same-filesystem hardlinks"]

key-files:
  created: []
  modified: [deploy.sh]

key-decisions:
  - "Actual NAS paths: /data/downloads (not /data/torrents), /data/tv (not /data/media/tv), /data/movies (not /data/media/movies)"
  - "Single volume mount /mnt/user/data:/data covers all three paths on same device (st_dev=46)"

patterns-established:
  - "deploy.sh volume mount pattern: -v /mnt/user/data:/data for hardlink support"

requirements-completed: []

# Metrics
duration: 5min
completed: 2026-02-23
---

# Phase 06 Plan 01: NAS Deploy Summary

**Full v1.0 stack deployed on NAS with volume mount /mnt/user/data:/data, USE_NEW_HANDLER=true, and same-filesystem hardlink support verified (st_dev=46)**

## Performance

- **Duration:** 5 min
- **Started:** 2026-02-23T10:27:31Z
- **Completed:** 2026-02-23T10:33:00Z
- **Tasks:** 3
- **Files modified:** 1 (deploy.sh) + NAS .env

## Accomplishments
- deploy.sh updated with `-v /mnt/user/data:/data` volume mount for hardlink support
- Container deployed and running on NAS with all three ports (8585, 8586, 8587) healthy
- Same-filesystem verification passed: all paths share st_dev=46, hardlinks will work
- USE_NEW_HANDLER=true and all library paths configured in container environment
- Rollback info saved: previous commit 786360f, .env backup at .env.bak
- Both Radarr and Sonarr test webhooks return 200 OK

## Task Commits

Each task was committed atomically:

1. **Task 1: Discover NAS paths, update deploy.sh, prepare .env additions** - `2f93fb1` (feat)
2. **Task 2: Deploy container and verify infrastructure** - (no local changes, deployment-only)
3. **Task 3: Verify deployment and test webhooks** - (human-verify checkpoint, approved)

## Files Created/Modified
- `deploy.sh` - Added `-v /mnt/user/data:/data` volume mount to docker run command
- NAS `.env` - Appended USE_NEW_HANDLER=true, DOWNLOAD_PATH=/data/downloads, SONARR_LIBRARY_PATH=/data/tv, RADARR_LIBRARY_PATH=/data/movies
- NAS `.env.bak` - Backup of previous .env for rollback

## Decisions Made
- Actual NAS directory structure differs from plan assumptions: downloads at `/mnt/user/data/downloads` (not `/data/torrents`), TV at `/mnt/user/data/tv` (not `/data/media/tv`), movies at `/mnt/user/data/movies` (not `/data/media/movies`). Adjusted container paths accordingly.
- Single volume mount `/mnt/user/data:/data` confirmed to cover all three directories on same block device

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Container path correction**
- **Found during:** Task 1 (NAS path discovery)
- **Issue:** Plan assumed paths like `/data/torrents` and `/data/media/tv`, but actual NAS layout uses `/data/downloads` and `/data/tv`
- **Fix:** Used discovered paths: DOWNLOAD_PATH=/data/downloads, SONARR_LIBRARY_PATH=/data/tv, RADARR_LIBRARY_PATH=/data/movies
- **Files modified:** NAS .env
- **Verification:** Container starts successfully, paths exist inside container
- **Committed in:** 2f93fb1

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Path correction was essential for container startup. No scope creep.

## Issues Encountered
- First deploy attempt resulted in container restart loop because the volume mount from the previous running container was missing (stale container from before deploy.sh update). Resolved by re-running `docker rm -f` and re-deploying.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Container running with hardlink pipeline active, ready for E2E validation (06-02)
- Rollback path documented if issues found during E2E testing

## Rollback Information
- **Previous NAS commit:** 786360f5bbac217ba6dd9c9334ed656b7956e8b5
- **NAS .env backup:** /mnt/user/appdata/prowlarr-llm-proxy/.env.bak
- **Rollback procedure:** Restore .env.bak, checkout previous commit, re-deploy

---
*Phase: 06-nas-deploy-and-e2e-validation*
*Completed: 2026-02-23*
