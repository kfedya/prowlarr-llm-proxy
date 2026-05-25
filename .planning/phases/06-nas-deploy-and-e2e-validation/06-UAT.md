---
status: complete
phase: 06-nas-deploy-and-e2e-validation
source: 06-01-SUMMARY.md, 06-02-SUMMARY.md
started: 2026-02-23T12:30:00Z
updated: 2026-02-23T20:30:00Z
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
  root_cause: "Two defects: (1) _process_subtitles is called after the polling loop exits (media_handler.py line 244), so it only runs when torrent reaches COMPLETED_STATES — never incrementally. (2) Path(sub_name).name strips the group folder prefix collapsing all groups to the same bare filename; plus subtitle_mappings.get(sub_basename) uses bare filename as key but the dict is keyed by full torrent-relative paths — LLM-assigned unique names are silently discarded and all groups collide at the same dst."
  artifacts:
    - path: "app/services/media_handler.py"
      issue: "Lines 244-252: _process_subtitles called after polling loop — never runs until torrent 100% complete"
    - path: "app/services/media_handler.py"
      issue: "Line 473: Path(sub_name).name strips group folder, collapsing all subtitle groups to same basename"
    - path: "app/services/media_handler.py"
      issue: "Line 474: subtitle_mappings.get(sub_basename, ...) uses bare filename as key but dict is keyed by full torrent-relative paths — LLM output always discarded"
    - path: "app/services/llm.py"
      issue: "Line 628: mappings[sub_file] stores full path as key — mismatched with lookup side"
    - path: "app/services/hardlink.py"
      issue: "Lines 138-140: FileExistsError silently skipped, collision not surfaced as warning"
  missing:
    - "Move subtitle processing inside the incremental polling loop (parallel to _handle_tv_grab video logic)"
    - "Preserve group identity: use full sub_name (not .name) to derive destination path, incorporating parent directory as disambiguator"
    - "Fix LLM output lookup: change subtitle_mappings.get(sub_basename, ...) to subtitle_mappings.get(sub_name, sub_basename) to use full path key"
  debug_session: ""

- truth: "Hardlinks are created with correct folder/file names that Sonarr/Radarr can match for import"
  status: failed
  reason: "User reported: Sonarr says 'No files found are eligible for import in /data/downloads/hardlinks/Cowboy Bebop TV BDRip 1080p [3df_voice]'. Sonarr/Radarr gets the series/movie title from the torrent downloader — we need to keep the original torrent folder name (and file names for single-file torrents) unchanged instead of LLM-renaming them."
  severity: major
  test: 6
  root_cause: "Sonarr's auto-import asks qBittorrent for content_path (original torrent folder name e.g. 'Cowboy Bebop TV BDRip 1080p [3df_voice]'), applies Remote Path Mapping, and looks for that exact folder under hardlinks/. But the proxy creates hardlinks under hardlinks/{sanitized-series-title}/ (e.g. hardlinks/Cowboy Bebop/) — different path. Fix: name the hardlink subfolder after torrent.name (original torrent name) not the Sonarr series title. LLM-renamed individual video filenames inside the folder are correct and must be preserved."
  artifacts:
    - path: "app/services/media_handler.py"
      issue: "Lines 360-365 (_compute_tv_hardlink_pairs): uses safe_series = _sanitize_title(series_title) as subfolder; should use sanitized torrent_name instead"
    - path: "app/services/media_handler.py"
      issue: "Lines 368-398 (_compute_movie_hardlink_pairs): uses f'{safe_title} ({year})' as subfolder; should use sanitized torrent_name"
    - path: "app/services/media_handler.py"
      issue: "torrent.name available at line 151 but never passed to _handle_tv_grab or _handle_movie_grab"
  missing:
    - "Add torrent_name parameter to _handle_tv_grab, _handle_movie_grab, _compute_tv_hardlink_pairs, _compute_movie_hardlink_pairs"
    - "Pass torrent.name from polling loop call sites to the handlers"
    - "Replace series_title/movie_title-based subfolder with sanitized torrent_name in both compute functions"
    - "Update _process_subtitles destination to use same torrent_name-derived folder"
  debug_session: ""
