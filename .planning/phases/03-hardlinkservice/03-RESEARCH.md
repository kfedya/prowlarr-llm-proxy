# Phase 3: HardlinkService - Research

**Researched:** 2026-02-23
**Domain:** Filesystem hardlinks (Python pathlib/os), cross-device validation
**Confidence:** HIGH

## Summary

HardlinkService is a pure filesystem operation service with zero external dependencies. The entire implementation uses Python stdlib: `os.link()` for hardlink creation, `Path.stat().st_dev` for cross-device detection, `Path.stat().st_ino` for inode verification, and `Path.mkdir(parents=True, exist_ok=True)` for directory creation. No third-party libraries are needed.

The service receives `(src, dst)` path pairs from the caller (file filtering and renaming happen upstream). It returns a structured result object with `created[]`, `skipped[]`, `errors[]` lists. Cross-device validation at startup uses `st_dev` comparison between download and library directories.

**Primary recommendation:** Use `os.link(src, dst)` (not `pathlib.Path.hardlink_to`) for clarity, since `hardlink_to` has confusing reversed semantics (`dst.hardlink_to(src)` creates a link at `dst` pointing to `src`'s data). Catch `FileExistsError` for skip-silently, `OSError` with `errno.EXDEV` for cross-device failures.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- If a hardlink target already exists at the destination: **skip silently** (assume previous run)
- Auto-create missing destination directories (mkdir -p equivalent)
- Return a **structured result** object with `created[]`, `skipped[]`, `errors[]` for the caller to inspect
- **Two log levels**: DEBUG logs each individual file operation (created/skipped/failed), INFO logs a per-torrent summary ("5 linked, 2 skipped, 0 failed")
- Startup cross-device validation: **only log on failure** (silent on success)
- **Dry-run mode**: `dry_run=True` parameter shows what WOULD be hardlinked without executing
- Hardlink **video + subtitles + external audio** only (.mkv/.mp4/.avi, .srt/.ass/.sub, .mka/.ac3/.dts/.flac)
- Skip all other files (nfo, txt, sample, images, etc.)
- **Flatten to one level**: all files end up alongside each other in the destination dir
- **HardlinkService does NOT rename**: it receives (src, dst) pairs where the caller already computed destination filenames
- Flow: get torrent files -> LLM renames -> create hardlinks with LLM-provided names

### Claude's Discretion
- Partial failure strategy (some files in batch fail): continue+report vs roll back
- Cross-device validation timing (startup only, per-operation, or both)
- Cross-device fallback (fail hard vs copy fallback) -- likely fail hard given same-volume setup
- Inode verification after link creation (whether to stat and confirm)

### Deferred Ideas (OUT OF SCOPE)
- Movie file renaming logic for Radarr (DVD releases, multi-file movies) -- needs research during Phase 4/5
- File type filter configurability via config -- can add later if needed
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| HDLK-01 | HardlinkService creates hardlinks from download dir to library dir using pathlib | `os.link(src, dst)` creates hardlinks; `Path.mkdir(parents=True)` creates destination dirs. Verified with Python 3.12 testing. Service accepts `list[tuple[Path, Path]]` pairs. |
| HDLK-04 | Startup validation checks source and target dirs are on the same filesystem | `Path.stat().st_dev` returns block device ID. Compare download_path vs library paths at init time. Raise `CrossDeviceError` if different. |
| HDLK-06 | Original torrent files remain untouched in qBittorrent download dir for seeding | Hardlinks share the same inode -- `src.stat().st_ino == dst.stat().st_ino` after creation. The source file is never modified or moved. `st_nlink` increases from 1 to 2. |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `os` (stdlib) | Python 3.11+ | `os.link(src, dst)` for hardlink creation | Direct syscall wrapper, clearest semantics |
| `pathlib` (stdlib) | Python 3.11+ | Path manipulation, `stat()`, `mkdir()` | Already used throughout the project |
| `structlog` | 24.4.0 | Structured logging (DEBUG per-file, INFO summaries) | Already in project dependencies |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `dataclasses` (stdlib) | Python 3.11+ | `HardlinkResult` structured return type | Result object with created/skipped/errors |
| `errno` (stdlib) | Python 3.11+ | `errno.EXDEV` constant for cross-device detection | In error handling for `os.link` |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `os.link(src, dst)` | `dst.hardlink_to(src)` (pathlib) | pathlib method has confusing reversed semantics -- `dst.hardlink_to(src)` reads backwards. `os.link` is clearer. |
| `dataclass` for result | `pydantic.BaseModel` | Overkill -- result is internal, never serialized to JSON. Dataclass is lighter. |
| Fail hard on cross-device | Copy fallback | User said same-volume setup. Failing hard is simpler and avoids silent performance degradation. |

**Installation:** No new dependencies needed. Everything is Python stdlib + existing project deps.

## Architecture Patterns

### Recommended Project Structure
```
app/
  services/
    hardlink.py         # HardlinkService class + HardlinkResult dataclass
tests/
  test_hardlink.py      # Pure filesystem tests using tmp_path
```

### Pattern 1: Pure Filesystem Service (No External Dependencies)
**What:** A service class that only depends on `pathlib.Path` and `os` -- no qBittorrent, no Sonarr, no Redis.
**When to use:** When the operation is pure filesystem manipulation.
**Example:**
```python
import os
import structlog
from dataclasses import dataclass, field
from pathlib import Path

logger = structlog.get_logger(__name__)

@dataclass
class HardlinkResult:
    """Result of a batch hardlink operation."""
    created: list[tuple[Path, Path]] = field(default_factory=list)
    skipped: list[tuple[Path, Path]] = field(default_factory=list)
    errors: list[tuple[Path, Path, str]] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.created) + len(self.skipped) + len(self.errors)

    @property
    def success(self) -> bool:
        return len(self.errors) == 0


class HardlinkService:
    def __init__(
        self,
        download_path: Path,
        library_paths: list[Path],
        dry_run: bool = False,
    ):
        self._download_path = download_path
        self._library_paths = library_paths
        self._dry_run = dry_run
        self._validate_same_device()

    def _validate_same_device(self) -> None:
        """Check all paths are on the same filesystem."""
        src_dev = self._download_path.stat().st_dev
        for lib_path in self._library_paths:
            if lib_path.stat().st_dev != src_dev:
                raise CrossDeviceError(
                    f"Download path ({self._download_path}) and library path "
                    f"({lib_path}) are on different filesystems "
                    f"(devices {src_dev} vs {lib_path.stat().st_dev}). "
                    f"Hardlinks require same filesystem."
                )

    def create_hardlinks(
        self, file_pairs: list[tuple[Path, Path]]
    ) -> HardlinkResult:
        result = HardlinkResult()
        for src, dst in file_pairs:
            self._link_one(src, dst, result)
        logger.info(
            "Hardlink batch complete",
            created=len(result.created),
            skipped=len(result.skipped),
            errors=len(result.errors),
        )
        return result

    def _link_one(
        self, src: Path, dst: Path, result: HardlinkResult
    ) -> None:
        if self._dry_run:
            logger.debug("dry-run: would hardlink", src=str(src), dst=str(dst))
            result.created.append((src, dst))
            return
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            os.link(src, dst)
            result.created.append((src, dst))
            logger.debug("hardlink created", src=str(src), dst=str(dst))
        except FileExistsError:
            result.skipped.append((src, dst))
            logger.debug("hardlink skipped (exists)", src=str(src), dst=str(dst))
        except OSError as e:
            result.errors.append((src, dst, str(e)))
            logger.debug("hardlink failed", src=str(src), dst=str(dst), error=str(e))


class CrossDeviceError(Exception):
    """Raised when download and library paths are on different filesystems."""
    pass
```

### Pattern 2: Structured Result Object
**What:** Return a dataclass with created/skipped/errors rather than raising on first failure.
**When to use:** When batch operations should continue despite individual failures.
**Example:** See `HardlinkResult` above. Caller inspects `result.success` and `result.errors`.

### Pattern 3: Constructor Validation (Fail-Fast)
**What:** Validate cross-device constraint in `__init__`, not per-operation.
**When to use:** When an invariant must hold for the entire lifetime of the service.
**Example:** `_validate_same_device()` in constructor raises `CrossDeviceError` before any operations begin.

### Anti-Patterns to Avoid
- **Copy fallback on cross-device:** Silent performance degradation. Fail hard instead -- the user confirmed same-volume setup.
- **Renaming inside HardlinkService:** Service boundary is clear -- it receives pre-computed (src, dst) pairs. Renaming belongs to the LLM service.
- **Hardlinking everything in the torrent:** Only video + subtitles + external audio. The file filtering happens upstream (caller), but the service should still validate extensions as a safety net if desired.
- **Using `Path.hardlink_to()`:** Confusing semantics. `dst.hardlink_to(src)` creates a link AT `dst` pointing to `src`'s data. `os.link(src, dst)` is more intuitive.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Hardlink creation | Custom syscall wrapper | `os.link(src, dst)` | Stdlib handles all edge cases, correct error types |
| Cross-device detection | Try-catch on `os.link` | `Path.stat().st_dev` comparison | Proactive detection at startup vs reactive per-file |
| Directory creation | Recursive mkdir implementation | `Path.mkdir(parents=True, exist_ok=True)` | Handles race conditions, existing dirs |
| Inode verification | Custom stat comparison | `src.stat().st_ino == dst.stat().st_ino` | Stdlib `stat()` gives exact inode |

**Key insight:** This is entirely stdlib territory. No external libraries needed. The complexity is in the error handling semantics and the service boundary design, not in the filesystem operations themselves.

## Common Pitfalls

### Pitfall 1: pathlib.hardlink_to Reversed Semantics
**What goes wrong:** `dst.hardlink_to(src)` looks like "hardlink dst to src" but actually creates a new link AT `dst` pointing to `src`'s data. Easy to get backwards.
**Why it happens:** Python 3.10 deprecated `link_to` (which had the intuitive direction) and replaced it with `hardlink_to` (reversed).
**How to avoid:** Use `os.link(src, dst)` which has standard POSIX semantics.
**Warning signs:** Tests pass but files end up in wrong locations.

### Pitfall 2: FileExistsError vs OSError on Duplicate Link
**What goes wrong:** Not catching `FileExistsError` specifically when destination already exists.
**Why it happens:** `os.link()` raises `FileExistsError` (subclass of `OSError`) when target exists. If you catch `OSError` broadly, you lose the distinction.
**How to avoid:** Catch `FileExistsError` first (for skip-silently), then `OSError` for other failures.
**Warning signs:** Re-runs fail instead of being idempotent.

### Pitfall 3: Cross-Device Error is OSError, Not FileExistsError
**What goes wrong:** Cross-device hardlink attempt raises `OSError` with `errno.EXDEV` (errno 18), not a specific exception type.
**Why it happens:** Python wraps the POSIX `EXDEV` error in generic `OSError`.
**How to avoid:** Startup validation via `st_dev` comparison prevents this entirely. If per-operation check needed: `except OSError as e: if e.errno == errno.EXDEV: ...`
**Warning signs:** Cryptic "Invalid cross-device link" errors at runtime.

### Pitfall 4: Docker Volume Mount Boundaries
**What goes wrong:** Download dir and library dir appear as different devices inside Docker if mounted from different host paths/volumes.
**Why it happens:** Each `-v` mount can create a separate device boundary inside the container.
**How to avoid:** Mount a common parent directory, or ensure both paths are subdirectories of the same volume mount. The NAS uses a single Unraid share, so this should work if both are under `/mnt/user/`.
**Warning signs:** `st_dev` values differ between download and library paths at startup.

### Pitfall 5: Permissions on Hardlinked Files
**What goes wrong:** Hardlink inherits source file permissions. If torrent client sets restrictive permissions, Sonarr/Radarr/Jellyfin may not be able to read the linked files.
**Why it happens:** Hardlinks share the same inode, so permissions are shared. Changing permissions on either file changes both.
**How to avoid:** Not a concern for this phase (same user/container context), but worth noting for deployment.
**Warning signs:** Jellyfin reports "access denied" on files that exist.

## Code Examples

Verified patterns from Python 3.12 testing:

### Creating a Hardlink
```python
import os
from pathlib import Path

src = Path("/downloads/torrent-name/video.mkv")
dst = Path("/tv/Series Name/Season 01/Series.Name.S01E01.mkv")

# Create parent directories
dst.parent.mkdir(parents=True, exist_ok=True)

# Create hardlink
os.link(src, dst)

# Verify same inode
assert src.stat().st_ino == dst.stat().st_ino
assert src.stat().st_nlink >= 2
```

### Cross-Device Validation
```python
from pathlib import Path

def validate_same_device(download_path: Path, *library_paths: Path) -> None:
    src_dev = download_path.stat().st_dev
    for lib_path in library_paths:
        lib_dev = lib_path.stat().st_dev
        if src_dev != lib_dev:
            raise CrossDeviceError(
                f"{download_path} (dev={src_dev}) and {lib_path} (dev={lib_dev}) "
                f"are on different filesystems"
            )
```

### Idempotent Hardlink (Skip if Exists)
```python
import os
from pathlib import Path

def link_or_skip(src: Path, dst: Path) -> str:
    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        os.link(src, dst)
        return "created"
    except FileExistsError:
        # Destination exists -- assume previous run
        return "skipped"
    except OSError as e:
        return f"error: {e}"
```

### Testing with tmp_path (pytest)
```python
import os
from pathlib import Path
import pytest

def test_create_hardlink(tmp_path: Path):
    src = tmp_path / "downloads" / "file.mkv"
    dst = tmp_path / "library" / "Series" / "Season 01" / "file.mkv"

    src.parent.mkdir(parents=True)
    src.write_bytes(b"video content")

    # Service creates the link
    service = HardlinkService(
        download_path=tmp_path / "downloads",
        library_paths=[tmp_path / "library"],
    )
    result = service.create_hardlinks([(src, dst)])

    assert len(result.created) == 1
    assert dst.exists()
    assert src.stat().st_ino == dst.stat().st_ino
    # Original file untouched
    assert src.read_bytes() == b"video content"


def test_cross_device_validation_same_device(tmp_path: Path):
    """tmp_path is always on same device -- validation passes."""
    dl = tmp_path / "downloads"
    lib = tmp_path / "library"
    dl.mkdir()
    lib.mkdir()

    # Should not raise
    service = HardlinkService(download_path=dl, library_paths=[lib])


def test_skip_existing(tmp_path: Path):
    src = tmp_path / "src.mkv"
    dst = tmp_path / "dst.mkv"
    src.write_bytes(b"data")
    os.link(src, dst)  # Pre-create the link

    service = HardlinkService(
        download_path=tmp_path,
        library_paths=[tmp_path],
    )
    result = service.create_hardlinks([(src, dst)])

    assert len(result.skipped) == 1
    assert len(result.created) == 0
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `Path.link_to(target)` | `Path.hardlink_to(target)` | Python 3.10 | `link_to` deprecated, `hardlink_to` reversed the direction semantics |
| `os.makedirs(path, exist_ok=True)` | `Path.mkdir(parents=True, exist_ok=True)` | Python 3.5+ | pathlib is idiomatic |
| Copy files to library dir | Hardlink files | Project design decision | Saves disk space, preserves seeding |

**Deprecated/outdated:**
- `Path.link_to()`: Deprecated in Python 3.10, removed in 3.12. Do NOT use.

## Discretion Recommendations

Based on the research, here are recommendations for the areas left to Claude's discretion:

### Partial Failure Strategy: Continue + Report
**Recommendation:** Continue processing remaining files and report all errors in the result object. Do NOT roll back successfully created hardlinks.
**Rationale:** Hardlinks are cheap to recreate and expensive to track for rollback. If 4 of 5 files succeed, the user benefits more from having 4 links than 0. The structured result (`errors[]`) lets the caller decide what to do.

### Cross-Device Validation Timing: Startup Only
**Recommendation:** Validate at service construction time only. Do not re-check per operation.
**Rationale:** Device IDs don't change at runtime. Startup validation catches misconfigured Docker volumes before any work begins. Per-operation checks add overhead with zero benefit.

### Cross-Device Fallback: Fail Hard
**Recommendation:** Raise `CrossDeviceError` exception. No copy fallback.
**Rationale:** User confirmed same-volume NAS setup. A copy fallback would silently consume 2x disk space and mask a Docker configuration error. Better to fail explicitly with a clear error message pointing to the volume mount issue.

### Inode Verification: Skip by Default
**Recommendation:** Do NOT verify inode after every link creation. Trust `os.link()` -- if it doesn't raise, the link was created.
**Rationale:** `os.link()` is an atomic kernel operation. If it returns without error, the hardlink exists with the correct inode. Adding a `stat()` call per file doubles syscalls with no real safety gain. Tests can verify inodes for correctness assurance.

## Open Questions

1. **Docker volume mount configuration for deploy.sh**
   - What we know: `deploy.sh` currently has no `-v` volume mounts. The container needs access to both download and library directories.
   - What's unclear: Exact NAS paths for downloads and library dirs. The `.env` has `DOWNLOAD_PATH`, `SONARR_LIBRARY_PATH`, `RADARR_LIBRARY_PATH` but deploy.sh doesn't mount them.
   - Recommendation: This is a Phase 4/5 deployment concern, not Phase 3. Phase 3 tests use `tmp_path`. Document the volume mount requirement in the plan.

2. **File extension filtering location**
   - What we know: CONTEXT.md says HardlinkService receives (src, dst) pairs -- filtering is upstream. But it also lists specific extensions.
   - What's unclear: Should HardlinkService have a safety-net extension check, or trust the caller completely?
   - Recommendation: Trust the caller. The service boundary is clear: it receives pairs and links them. Extension filtering belongs in the orchestrator (Phase 4). Keep HardlinkService focused.

## Sources

### Primary (HIGH confidence)
- Python 3.12 interactive testing -- verified `os.link()`, `Path.hardlink_to()`, `stat().st_dev`, `stat().st_ino`, `FileExistsError`, `errno.EXDEV`
- Existing project codebase -- `app/config.py` (path settings), `app/container.py` (DI pattern), `tests/conftest.py` (tmp_path fixtures)

### Secondary (MEDIUM confidence)
- Python docs: `os.link()` creates a hard link. `Path.hardlink_to()` added in 3.10, `link_to` deprecated in 3.10.
- Existing `sonarr_handler.py` service pattern -- constructor with DI, structlog logging, async methods

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- pure Python stdlib, verified with interactive testing
- Architecture: HIGH -- follows existing project patterns (service class, DI container, structlog)
- Pitfalls: HIGH -- verified error types and edge cases with real Python execution

**Research date:** 2026-02-23
**Valid until:** 2026-06-23 (stable -- stdlib APIs don't change)
