---
status: complete
phase: 06-nas-deploy-and-e2e-validation
source: 06-01-SUMMARY.md, 06-02-SUMMARY.md
started: 2026-02-23T12:30:00Z
updated: 2026-02-23T20:00:00Z
---

## Current Test

[testing complete]

## Tests

### 1. Container health — all ports responding
expected: SSH to NAS and verify container is running with all 3 ports healthy. `docker ps` shows prowlarr-llm-proxy "Up" with ports 8585, 8586, 8587 mapped.
result: pass

### 2. Sonarr webhook endpoint responds 200
expected: Sonarr webhook at http://192.168.10.199:8585/sonarr/webhook returns HTTP 200 on a test POST (or the webhook test from Sonarr settings shows "Test successful").
result: pass

### 3. Radarr webhook endpoint responds 200
expected: Radarr webhook at http://192.168.10.199:8587/radarr/webhook returns HTTP 200 on a test POST (or the webhook test from Radarr settings shows "Test successful").
result: pass

### 4. TV grab — hardlinks created at staging path
expected: Trigger a Sonarr grab for a TV episode. Watch logs: `ssh root@192.168.10.199 "docker logs prowlarr-llm-proxy --follow --tail 0"`. After grab completes, hardlinked files appear at /data/downloads/hardlinks/{Series Name}/ with LLM-normalized filenames (e.g. "Show.Name.S01E01.mkv").
result: pass
note: "Initial run created only 2/26 because fix commit 8ed6e72 was not deployed. After deploy, all 26/26 hardlinks created for Cowboy Bebop (confirmed via docker exec)."

### 5. TV hardlinks share inode with original
expected: After TV hardlinks are created, verify `stat` on both the original download file and the hardlink shows the same inode number. Link count should be >= 2. E.g.: `stat /data/downloads/{torrent_folder}/episode.mkv` and `stat /data/downloads/hardlinks/{Series}/episode.mkv` show same Inode field.
result: pass
note: "Inode 11258999068426376, Links: 2 — confirmed same inode on both paths. Device 0,46 confirms same filesystem."

### 6. Movie grab — hardlinks created with torrent-relative structure
expected: Trigger a Radarr grab for a movie. After grab completes, hardlinked files appear at /data/downloads/hardlinks/{Movie (Year)}/ preserving the torrent's folder structure (e.g. if torrent has Movie.2024/Movie.2024.mkv, hardlink appears at hardlinks/Movie (2024)/Movie.2024/Movie.2024.mkv).
result: issue
reported: "Sonarr says 'No files found are eligible for import in /data/downloads/hardlinks/Cowboy Bebop TV BDRip 1080p [3df_voice]'. Sonarr/Radarr gets the series/movie title from the torrent downloader — we need to keep the original torrent folder name (and file names for single-file torrents) unchanged instead of LLM-renaming them."
severity: major

### 7. Sonarr can import from hardlinks path
expected: In Sonarr, trigger "Manual Import" pointing at /data/downloads/hardlinks. The series folder appears and episodes can be imported (matched to correct series/season/episode). Import completes without error.
result: issue
reported: "Subtitle hardlinks (.ass) not created for Kaguya series even though source torrent has 3 subtitle groups (Cqur Far, SovetRomantica, Wakanim). Two root causes: (1) _process_subtitles only runs after torrent reaches 'uploading' state — when torrent is 69.5% downloaded, videos are hardlinked but subtitles not yet; (2) multiple subtitle groups with identical filenames all resolve to same sub_basename, causing last-write-wins collision when hardlinking."
severity: major

### 8. Radarr can import from hardlinks path
expected: In Radarr, trigger "Manual Import" pointing at /data/downloads/hardlinks. The movie folder appears and can be imported. Import completes without error.
result: pass

## Summary

total: 8
passed: 6
issues: 2
pending: 0
skipped: 0

## Gaps

- truth: "Subtitle hardlinks (.ass etc.) are created alongside video hardlinks when a TV grab includes external subtitles"
  status: failed
  reason: "User reported: No subtitle hardlinks for Kaguya (Beatrice-Raws BDRip with Cqur Far/SovetRomantica/Wakanim subtitle groups). Two bugs: (1) _process_subtitles only runs after full torrent completion — at 69.5% progress videos are hardlinked but subtitles pending; (2) multiple subtitle groups with identical filenames (all 3 groups have same .ass filenames) collide at destination — only last one written."
  severity: major
  test: 7
  root_cause: ""
  artifacts: []
  missing: []
  debug_session: ""

- truth: "Hardlinks are created with correct folder/file names that Sonarr/Radarr can match for import"
  status: failed
  reason: "User reported: Sonarr says 'No files found are eligible for import in /data/downloads/hardlinks/Cowboy Bebop TV BDRip 1080p [3df_voice]'. Sonarr/Radarr gets the series/movie title from the torrent downloader — we need to keep the original torrent folder name (and file names for single-file torrents) unchanged instead of LLM-renaming them."
  severity: major
  test: 6
  root_cause: ""
  artifacts: []
  missing: []
  debug_session: ""
