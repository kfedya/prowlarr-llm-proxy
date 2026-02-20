# Codebase Concerns

**Analysis Date:** 2026-02-20

## Tech Debt

**Bare exception handling in webhook parsing:**
- Issue: Line 65 in `app/controllers/webhook.py` uses bare `except:` clause which catches all exceptions including system-level errors
- Files: `app/controllers/webhook.py:65`
- Impact: May silently swallow critical errors (SystemExit, KeyboardInterrupt), making debugging difficult. Silent failures in webhook processing.
- Fix approach: Catch specific exceptions (`json.JSONDecodeError`, `Exception`) instead. The bare except should only catch `Exception` at minimum.

**Missing fallback for torrent lookup by download_id:**
- Issue: Line 95 in `app/services/sonarr_handler.py` has TODO comment: "Implement fallback search by download_id"
- Files: `app/services/sonarr_handler.py:95`
- Impact: When Redis mapping is missing, the service returns early without attempting alternative lookups. If the mapping expires or is deleted, the webhook will fail to process the grab event.
- Fix approach: Implement fallback search using `download_id` from Sonarr webhook as a secondary lookup method. Query qBittorrent by hash directly or implement GUID-based search pattern.

**Duplicate Redis service implementations:**
- Issue: Both `app/services/redis.py` and `app/services/torrent_mapping.py` manage Redis connections
- Files: `app/services/redis.py`, `app/services/torrent_mapping.py`
- Impact: Confusing codebase with two different Redis abstraction layers. `RedisService` is defined but not used in container; `TorrentMappingService` directly manages Redis. Potential for inconsistency.
- Fix approach: Remove `app/services/redis.py` entirely. All Redis operations should go through `TorrentMappingService`. If generic Redis operations are needed, add methods to `TorrentMappingService` instead.

**No test directory structure:**
- Issue: Test files (`test_*.py`) are at root level, not in organized `tests/` directory
- Files: `test_manual.py`, `test_move_subs.py`, `test_qbittorrent.py`, `test_rename.py`, `test_subtitles.py`, `test_subtitles_simple.py` at root
- Impact: Mixing test files with project root makes codebase hard to navigate. Python cannot auto-discover these tests. Docker builds may unintentionally include test files.
- Fix approach: Move all test files to `tests/` directory with proper `__init__.py`. Update `.dockerignore` to exclude tests/.

## Known Bugs

**Potential race condition in subtitle matching:**
- Symptoms: Subtitle file names may not be matched correctly if multiple subtitles exist for same episode from different providers
- Files: `app/services/llm.py:491-530` (normalize_subtitle_names method)
- Trigger: When torrent contains multiple subtitle variants (e.g., "01.ru.ass", "01.ru.SovetRomantica.ass" for same episode)
- Workaround: LLM usually gets this right but relies on filename patterns. Complex subtitle structures may cause mismatches. Current implementation: `if sub_file.endswith(old_path) or old_path in sub_file` is fragile.

**File path normalization issues with special characters:**
- Symptoms: Files with special characters (ampersands, quotes, non-ASCII) may fail during renaming
- Files: `app/services/proxy.py:160-165` (XML escaping), `app/services/sonarr_handler.py:419`
- Trigger: When torrent titles or file names contain `&`, `<`, `>` or other special characters
- Workaround: XML escaping only happens in proxy response, not validated in file rename. If LLM outputs unescaped XML special chars, qBittorrent API may reject rename.

**No validation that renamed torrent folder exists before moving remaining files:**
- Symptoms: Files might not move if torrent folder rename fails silently
- Files: `app/services/sonarr_handler.py:543-645` (_move_remaining_files method)
- Trigger: When `_rename_torrent_for_sonarr` fails and returns fallback series name, subsequent file moves may put files in wrong location
- Workaround: Current code catches and logs errors but doesn't validate folder structure. Files could end up scattered.

## Security Considerations

**Passwords stored in plaintext in logs:**
- Risk: While `.env` files are excluded from git, if logs are captured or streamed, qBittorrent username is logged
- Files: `app/services/qbittorrent.py:78` (logs base_url which includes no credentials, but username is in init config)
- Current mitigation: qBittorrent password is never logged, only used in memory. But `username` could be considered sensitive.
- Recommendations: Avoid logging any authentication-related configuration. Mask or omit credentials from all log messages.

**Redis password in connection string:**
- Risk: Redis connection parameters passed through DI container without masking
- Files: `app/container.py:28-35`
- Current mitigation: Password is from environment variable, not hardcoded. Connection only used internally.
- Recommendations: Never log Redis password. Validate that redis_password env var is not logged by structlog.

**OpenAI API key exposure risk:**
- Risk: API key passed to LLMService in plain form
- Files: `app/container.py:45-49`, `app/config.py:28`
- Current mitigation: Only stored in memory and passed to OpenAI client. Not logged.
- Recommendations: Add validation that OPENAI_API_KEY is never logged. Consider using mask pattern in logs if needed.

**No rate limit protection on webhook endpoint:**
- Risk: `/webhook/sonarr/grab` endpoint has no authentication or rate limiting
- Files: `app/controllers/webhook.py:38-111`
- Current mitigation: Webhook processing is async but unbounded.
- Recommendations: Add authentication (verify webhook token from Sonarr), implement rate limiting, or require network isolation.

## Performance Bottlenecks

**Synchronous regex operations on large XML responses:**
- Problem: `ITEM_PATTERN.finditer()` in proxy service iterates through entire XML response
- Files: `app/services/proxy.py:124`
- Cause: For large search results (100+ items), regex parsing may be slow. String manipulation with offset tracking is O(n²) worst case.
- Improvement path: Consider streaming XML parser or batching regex operations. For 100 items, current approach is acceptable but will degrade at 1000+.

**Redis scan operation for search_by_original_title is inefficient:**
- Problem: `_redis.scan()` in torrent_mapping service scans all keys
- Files: `app/services/torrent_mapping.py:175-230`
- Cause: Fallback lookup that scans entire keyspace when mapping not found. Could lock Redis with large datasets.
- Improvement path: This is used as fallback only. Mark as slow operation in logs. Consider adding separate index or searching by GUID instead (already implemented).

**LLM batch processing with exponential backoff on rate limits:**
- Problem: Rate limit retry uses exponential backoff (1.5^attempt multiplier) up to MAX_RETRIES=2
- Files: `app/services/llm.py:204-213`
- Cause: With BATCH_SIZE=10 and 100 results, multiple batches could hit rate limits. Backoff may delay processing 3+ seconds.
- Improvement path: Implement adaptive rate limiting or token bucket algorithm. Consider reducing BATCH_SIZE when hitting rate limits. Monitor OpenAI usage.

**Torrent metadata retry with hardcoded delays:**
- Problem: `_get_video_files_with_retry` waits 2 seconds per retry with 1.5x backoff for up to 10 retries
- Files: `app/services/sonarr_handler.py:291-347`
- Cause: Max wait time could be 2 * (1.5^9) ≈ 430 seconds if all retries fail. Webhook timeout could occur.
- Improvement path: Reduce initial retry_delay or max_retries based on empirical testing. Current defaults may be too conservative.

## Fragile Areas

**File path string manipulation for torrent folder structure:**
- Files: `app/services/sonarr_handler.py:419`, `app/services/sonarr_handler.py:605`
- Why fragile: Uses string concatenation `f"{torrent_folder}/{relative_path}"` without validation. If torrent_folder is empty or contains trailing slashes, paths become invalid.
- Safe modification: Validate that torrent_folder is non-empty before use. Use pathlib.Path for path operations or implement path validation helper.
- Test coverage: Line 574, 578, 605, 610 have path concatenation but no tests for edge cases (empty folder, duplicate slashes, special chars).

**LLM response parsing relies on numbered format:**
- Files: `app/services/llm.py:221-247` (_parse_batch_response), `app/services/llm.py:440-543` (normalize_subtitle_names)
- Why fragile: Expects numbered responses "1: Title" or "1. Title". If LLM deviates format (extra spaces, missing numbers), parsing fails silently, reverting to original titles.
- Safe modification: Add fallback logic for unnumbered responses. Validate response count matches input count. Log warnings when parsing fails to help debug.
- Test coverage: No unit tests for edge cases like malformed LLM output, missing line breaks, or Unicode characters.

**qBittorrent rename operations without verification:**
- Files: `app/services/sonarr_handler.py:421-425`, `app/services/sonarr_handler.py:517-521`, `app/services/sonarr_handler.py:607-611`
- Why fragile: Rename calls to qBittorrent API are fire-and-forget. No verification that rename actually succeeded. If qBittorrent API fails silently, files remain incorrectly named.
- Safe modification: Implement retry logic for failed renames. Query file list after rename to verify. Add timeout for rename completion.
- Test coverage: No integration tests verifying actual file state after rename operations.

**Torrent mapping lookup by exact title match:**
- Files: `app/services/sonarr_handler.py:87`, `app/services/torrent_mapping.py:118-149`
- Why fragile: Exact title match `get_by_title(payload.release.releaseTitle)` fails if Sonarr's title differs slightly from normalized title stored in Redis. Common causes: trailing spaces, encoding issues, LLM variations.
- Safe modification: Implement fuzzy matching or prefix matching. Store multiple variations. Add GUID-based lookup as primary key.
- Test coverage: No tests for title mismatch scenarios.

## Scaling Limits

**In-memory LLM cache in single-instance deployment:**
- Current capacity: Unbounded dict in `LLMService._cache`
- Limit: Memory grows without bound. No eviction policy. With 1000s of unique titles, could consume significant memory.
- Scaling path: Implement LRU cache with max size. Consider time-based expiration. Monitor memory usage. For multi-instance setups, rely on Redis cache only (already implemented).

**Redis key design without namespacing:**
- Current capacity: All mappings in single Redis db, key pattern `torrent:mapping:*`
- Limit: With multiple Prowlarr instances, keys could collide if using same Redis. Title-based keys don't account for multiple indexers having same title.
- Scaling path: Add instance identifier to key prefix. Use GUID as primary key instead of title. Partition data by indexer.

**Webhook background task queue unbounded:**
- Current capacity: FastAPI BackgroundTasks has no size limit
- Limit: If Sonarr sends many grab events faster than processing, all tasks queue in memory until processed
- Scaling path: Replace with task queue (Celery, RQ) for distributed processing. Add monitoring for queue depth. Implement backpressure.

**LLM API rate limits without global throttling:**
- Current capacity: MAX_CONCURRENT_BATCHES=2 with BATCH_SIZE=10 means max 20 concurrent items per OpenAI call
- Limit: Multiple webhook events could trigger parallel LLM calls simultaneously. No global token bucket or rate limiter.
- Scaling path: Implement request throttling. Add metrics collection for API usage. Set up OpenAI rate limit alerts.

## Dependencies at Risk

**OpenAI library version ^1.59.5 with tight coupling:**
- Risk: Code tightly coupled to OpenAI SDK API. Breaking changes in v2.x would require rewrite.
- Impact: When OpenAI releases v2.0, all LLM service code would break. Current version constraint allows up to ^1.x only.
- Migration plan: Keep version constraint locked to ^1 for now. Plan migration to v2.0 (if released) by abstracting LLM service behind interface. Add integration tests for API.

**Redis 5.2.1 with async-only API:**
- Risk: Library provides only async interface. Blocking operations not possible without asyncio.
- Impact: Cannot use blocking operations or synchronous fallback. All code must be async-compatible.
- Migration plan: Current design is async-native, so this is not a problem. But if sync code needed in future, would require complete rewrite.

**dependency-injector 4.45.0 with learning curve:**
- Risk: DI framework may have limited community support or maintenance.
- Impact: If framework stops being maintained, refactoring to manual DI would be large effort. Current container setup in `app/container.py` would need to be rewritten.
- Migration plan: Framework is stable and actively maintained. Risk is low. If needed, manual DI factory functions can be created.

## Missing Critical Features

**No authentication on webhook endpoint:**
- Problem: `/webhook/sonarr/grab` accepts requests from anyone
- Blocks: In production, this is security risk. Any attacker can trigger file renaming operations.
- Solution: Add webhook token validation. Sonarr supports passing custom headers. Implement token comparison or HMAC validation.

**No transaction support for multi-step operations:**
- Problem: If webhook handler fails mid-processing, state is inconsistent. Example: renamed torrent but files not renamed, files moved to wrong folder.
- Blocks: Cannot reliably handle failures. No rollback mechanism.
- Solution: Add logging of operation state. Implement idempotency (retry same operation safely). Consider transaction-like pattern with state tracking.

**No monitoring or observability for webhook processing:**
- Problem: Cannot tell if webhooks are being processed, how long they take, or failure rates
- Blocks: Debugging production issues is difficult. No metrics on success/failure.
- Solution: Add Prometheus metrics (processing time, error counts). Implement structured logging with correlation IDs. Add health check endpoint showing last webhook timestamp.

**No validation of qBittorrent responses:**
- Problem: Responses from qBittorrent API are not validated against expected schema
- Blocks: If qBittorrent version changes API, silent failures occur.
- Solution: Add response validation with Pydantic models. Add API version check on startup.

## Test Coverage Gaps

**No unit tests for LLM response parsing:**
- What's not tested: Edge cases in `_parse_batch_response()` - malformed responses, missing numbers, extra whitespace, Unicode handling
- Files: `app/services/llm.py:221-247`
- Risk: LLM returning unexpected format (extra spaces, different separator, missing items) could silently fail and use original titles. No visibility.
- Priority: High - this is critical path for search result normalization

**No integration tests for torrent rename workflow:**
- What's not tested: Full end-to-end rename of real torrent files with qBittorrent
- Files: `app/services/sonarr_handler.py` full flow
- Risk: Rename logic could be completely broken in production and not caught until manual testing.
- Priority: High - this is entire purpose of webhook handler

**No tests for Redis failure scenarios:**
- What's not tested: Redis connection loss, timeout, full database, failed setex/get operations
- Files: `app/services/torrent_mapping.py`
- Risk: If Redis is down, silent failures occur or service crashes without graceful fallback.
- Priority: Medium - should degrade gracefully but may not

**No tests for concurrent webhook processing:**
- What's not tested: Multiple webhooks arriving simultaneously for same torrent
- Files: `app/controllers/webhook.py`, `app/services/sonarr_handler.py`
- Risk: Race conditions in file renaming, duplicate renames, state inconsistency.
- Priority: Medium - unlikely in typical usage but should be safe

**No tests for qBittorrent API errors:**
- What's not tested: 404 (torrent not found), 403 (auth failed), 500 (server error), timeout scenarios
- Files: `app/services/qbittorrent.py`
- Risk: Error handling may not work correctly. Service might crash on unexpected responses.
- Priority: Medium - error handling exists but untested

**No tests for file path special characters:**
- What's not tested: File names with `&`, `<`, `>`, quotes, unicode, very long paths
- Files: `app/services/sonarr_handler.py:419`, `app/services/proxy.py:160-165`
- Risk: Special character handling could fail for certain torrents.
- Priority: Low - XML escaping exists but edge cases unknown

---

*Concerns audit: 2026-02-20*
