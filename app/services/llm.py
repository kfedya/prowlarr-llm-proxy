import asyncio
from openai import AsyncOpenAI
import structlog
from dataclasses import dataclass

logger = structlog.get_logger()

# Rate limiting settings
BATCH_SIZE = 10  # Number of torrents per LLM request
MAX_CONCURRENT_BATCHES = 2  # Max parallel batch requests to OpenAI
MAX_RETRIES = 2  # Max retries on rate limit error
RETRY_BASE_DELAY = 1.5  # Base delay for exponential backoff

SYSTEM_PROMPT = """Parse torrent titles for Sonarr. You will receive multiple titles numbered [1], [2], etc.
Output ONLY normalized titles, one per line, in the same order: 1: result, 2: result, etc.

RULE #1 - NAME (CRITICAL - follow EXACTLY):
You MUST use the "Series:" field name as-is! DO NOT extract name from the torrent title!
- The Series field = exact name Sonarr expects
- Remove season from Series name: "Golden Kamuy 2nd Season" → "Golden Kamuy"
- NEVER use Russian names (Непутёвый ученик...)
- NEVER use Japanese romanji (Mahouka, Shingeki...)
- ONLY use the Series field!
Example: Series: "The Irregular at Magic High School" → output MUST start with "The Irregular at Magic High School"
Example: Series: "Attack on Titan" → output MUST start with "Attack on Titan"

RULE #2 - LANGUAGES (IMPORTANT - check carefully!):
On RuTracker, "+Sub" ALWAYS means Russian subtitles!
- "JAP+Sub" or "[JAP+Sub]" → [JA][RU] (Japanese audio + Russian subs)
- "JAP+RUS" → [JA][RU]
- "JAP" alone (no +Sub, no +RUS) → [JA]
- "RUS" or "RUS(ext)" → [RU]
- "ENG" → [EN]

RULE #3 - SEASON (extract from TITLE, not Series field!):
- "(S1)" or "(ТВ-1)" or "[TV]" or "1st Season" → S01
- "(S2)" or "(ТВ-2)" or "2nd Season" or "2" after title → S02
- "(S3)" or "(ТВ-3)" or "3rd Season" or "3" after title → S03
- "(S4)", "(S5)", etc. → S04, S05, etc.

RULE #4 - EPISODES (CRITICAL - read carefully!):
SEASON PACK detection: "[N of N]" or "[N из N]" where BOTH numbers are the SAME = FULL SEASON!
- "[12 of 12]" or "[12 из 12]" → E01-E12 (FULL season pack! Start from E01!)
- "[13 of 13]" or "[13 из 13]" → E01-E13 (FULL season pack! Start from E01!)
- "[E13 of 13]" → E01-E13 (FULL season! The "E13" just means total episodes = 13)
- "[24 из 24]" → E01-E24 (FULL season pack!)
- "[1-13 из 24]" → E01-E13 (partial season, explicit range)
- "[E1 of 13]" → E01 (single episode - first number is 1, second is total)
- "[1123-1155]" (absolute numbers for long anime, no "of/из") → 1123-1155 (no S/E prefix)

LONG ANIME (One Piece, Naruto, etc.) - ABSOLUTE EPISODE NUMBERS:
- "[1086-1122 из XXX]" → 1086-1122 (XXX means ongoing series, extract the range!)
- "[1086-1122 of XXX]" → 1086-1122
- "[TV] [1086-1122 из XXX]" → 1086-1122 (ignore [TV], extract episode range)
- For 3+ digit episode numbers, output WITHOUT S/E prefix: just "1086-1122"

Split-cour seasons (Re:Zero S2, Kaguya-sama S3, etc.):
• If two separate releases exist for the same season:
  - [13 из 13] (часть 1) → SxxE01-E13
  - [12 из 12] (часть 2) → SxxE14-E25
  (do NOT merge into E01-E25 unless it's a single full-season release)
• If single full release [25 из 25] → E01-E25
• Never add "Part 1"/"Cour 1" in title — Sonarr doesn't like it

WARNING: "[E13 of 13]" does NOT mean "only episode 13"! It means "complete season of 13 episodes" → E01-E13

RULE #5 - QUALITY (ALWAYS include resolution!):
- WEB-DL 1080p / WEBRip 1080p → [WEBDL-1080p]
- WEB-DL 720p / WEBRip 720p → [WEBDL-720p]
- WEB-DL 2160p / 4K → [WEBDL-2160p]
- BDRip 1080p / Blu-ray 1080p → [Bluray-1080p]
- BDRip 720p → [Bluray-720p]
- BDRemux / BD Remux 1080p → Bluray.1080p.Remux (NO brackets!)
- BDRemux 2160p / 4K Remux → Bluray.2160p.Remux (NO brackets!)
- HDTV 1080p → [HDTV-1080p]
- HDTV 720p → [HDTV-720p]
- DVDRip → [DVD]
- If resolution unknown, assume 1080p

FORMAT: {Series Title} - S{season}E{episode}-E{episode} - [Quality][Language]
For Remux: {Series Title} - S{season} - Bluray.1080p.Remux [Language]

EXAMPLE INPUT:
[1] Title: "Атака титанов (ТВ-1) / Shingeki no Kyojin [25 из 25] [JAP+Sub] [BDRip 1080p]"
Series: Attack on Titan
[2] Title: "Непутёвый ученик в школе магии (S3) / Mahouka Koukou no Rettousei 3rd Season [E13 of 13] [JAP+Sub] [WEBRip 1080p]"
Series: The Irregular at Magic High School
[3] Title: "Ван-Пис / One Piece [1123-1155] WEB-DL 1080p JAP+SUB"
Series: One Piece
[4] Title: "Ван Пис / One Piece [TV] [1086-1122 из XXX] [JAP+Sub] [WEB-DL] [720p]"
Series: One Piece

EXAMPLE OUTPUT:
1: Attack on Titan - S01E01-E25 - [Bluray-1080p][JA][RU]
2: The Irregular at Magic High School - S03E01-E13 - [WEBDL-1080p][JA][RU]
3: One Piece - 1123-1155 - [WEBDL-1080p][JA][RU]
4: One Piece - 1086-1122 - [WEBDL-720p][JA][RU]"""


@dataclass
class TorrentItem:
    """Data extracted from a Torznab item."""
    title: str
    category: str = ""
    series_name: str = ""  # Expected name from Sonarr search query
    
    def to_prompt(self) -> str:
        """Format item data for LLM prompt."""
        parts = [f"Title: {self.title}"]
        if self.series_name:
            parts.append(f"Series: {self.series_name}")
        if self.category:
            parts.append(f"Category: {self.category}")
        return "\n".join(parts)


class LLMService:
    """Service for parsing torrent titles using OpenAI with batching."""

    def __init__(self, api_key: str, model: str = "gpt-4o-mini"):
        self._client = AsyncOpenAI(api_key=api_key)
        self._model = model
        self._cache: dict[str, str] = {}
        self._semaphore = asyncio.Semaphore(MAX_CONCURRENT_BATCHES)
        logger.info("LLMService initialized", model=model, batch_size=BATCH_SIZE, max_concurrent_batches=MAX_CONCURRENT_BATCHES)

    async def _parse_batch(self, items: list[TorrentItem]) -> list[str]:
        """
        Parse a batch of torrent items in a single LLM request.
        Returns list of normalized titles in the same order.
        """
        if not items:
            return []
        
        # Build batch prompt
        prompt_parts = []
        for i, item in enumerate(items, 1):
            part = f"[{i}] Title: \"{item.title}\""
            if item.series_name:
                part += f"\nSeries: {item.series_name}"
            prompt_parts.append(part)
        
        user_prompt = "\n".join(prompt_parts)
        
        async with self._semaphore:
            for attempt in range(MAX_RETRIES):
                try:
                    response = await self._client.chat.completions.create(
                        model=self._model,
                        messages=[
                            {"role": "system", "content": SYSTEM_PROMPT},
                            {"role": "user", "content": user_prompt},
                        ],
                        max_tokens=100 * len(items),  # ~100 tokens per result
                        temperature=0.1,
                    )
                    
                    response_text = response.choices[0].message.content.strip()
                    
                    # Parse numbered responses
                    results = self._parse_batch_response(response_text, items)
                    
                    # Cache results (include series_name in cache key)
                    for item, result in zip(items, results):
                        if result != item.title:
                            cache_key = f"{item.title}|{item.series_name}"
                            self._cache[cache_key] = result
                            logger.debug("Title normalized", original=item.title[:50], normalized=result)
                    
                    logger.info(
                        "Batch parsed",
                        batch_size=len(items),
                        success_count=sum(1 for r, i in zip(results, items) if r != i.title),
                    )
                    
                    return results

                except Exception as e:
                    error_str = str(e)
                    if "429" in error_str or "rate_limit" in error_str.lower():
                        delay = RETRY_BASE_DELAY * (2 ** attempt)
                        logger.warning(
                            "Rate limit hit, retrying batch",
                            attempt=attempt + 1,
                            max_retries=MAX_RETRIES,
                            delay=delay,
                            batch_size=len(items),
                        )
                        await asyncio.sleep(delay)
                        continue
                    
                    logger.error("Failed to parse batch", error=error_str, batch_size=len(items))
                    return [item.title for item in items]
            
            logger.error("All retries exhausted for batch", batch_size=len(items))
            return [item.title for item in items]
    
    def _parse_batch_response(self, response_text: str, items: list[TorrentItem]) -> list[str]:
        """Parse LLM batch response into list of normalized titles."""
        results = [item.title for item in items]  # Default to original titles
        
        for line in response_text.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            
            # Parse "1: Title" or "1. Title" format
            if ":" in line[:5] or "." in line[:5]:
                sep_pos = min(
                    line.find(":") if ":" in line[:5] else 999,
                    line.find(".") if "." in line[:5] else 999
                )
                try:
                    num = int(line[:sep_pos].strip())
                    title = line[sep_pos + 1:].strip()
                    if 1 <= num <= len(items) and title:
                        # Add [RUS] suffix if original ends with RUS
                        if items[num - 1].title.rstrip().upper().endswith("RUS"):
                            title = f"{title}[RUS]"
                        results[num - 1] = title
                except (ValueError, IndexError):
                    continue
        
        return results

    async def parse_items_batch(self, items: list[TorrentItem]) -> list[str]:
        """
        Parse multiple torrent items using batching for efficiency.
        Groups items into batches of BATCH_SIZE and processes them in parallel.
        """
        if not items:
            return []
        
        # Separate cached and uncached items
        results = [None] * len(items)
        uncached_indices = []
        uncached_items = []
        
        for i, item in enumerate(items):
            cache_key = f"{item.title}|{item.series_name}"
            if cache_key in self._cache:
                results[i] = self._cache[cache_key]
                logger.debug("Cache hit", raw_title=item.title[:50])
            else:
                uncached_indices.append(i)
                uncached_items.append(item)
        
        if not uncached_items:
            logger.info("All items from cache", total=len(items))
            return results
        
        logger.info(
            "Starting batch parse",
            total_items=len(items),
            cached=len(items) - len(uncached_items),
            to_process=len(uncached_items),
            batch_size=BATCH_SIZE,
        )
        
        # Split into batches
        batches = [
            uncached_items[i:i + BATCH_SIZE]
            for i in range(0, len(uncached_items), BATCH_SIZE)
        ]
        
        # Process batches in parallel (limited by semaphore)
        batch_results = await asyncio.gather(*[self._parse_batch(batch) for batch in batches])
        
        # Flatten and map back to original indices
        flat_results = [title for batch in batch_results for title in batch]
        for idx, title in zip(uncached_indices, flat_results):
            results[idx] = title
        
        return results

    def clear_cache(self) -> None:
        """Clear the title cache."""
        self._cache.clear()
        logger.info("LLM cache cleared")

    async def normalize_file_names(
        self,
        file_names: list[str],
        series_name: str,
        season_number: int,
        episodes: list[int] | None = None,
    ) -> dict[str, str]:
        """Normalize torrent file names for Sonarr.
        
        Args:
            file_names: List of file names to normalize (from qBittorrent)
            series_name: Series name from Sonarr
            season_number: Season number
            episodes: Optional list of episode numbers expected (for validation)
            
        Returns:
            Dict mapping old file name to new file name.
            If a file should not be renamed, it won't be in the dict.
        """
        if not file_names:
            return {}
        
        logger.info(
            "Normalizing file names with LLM",
            series_name=series_name,
            season=season_number,
            file_count=len(file_names),
        )
        
        # Build prompt for file normalization
        system_prompt = """You are a file renamer for Sonarr. Given a series name, season number, and list of file names, 
output normalized file names in Sonarr format.

FORMAT: {Series Name} - S{Season}E{Episode}.{ext}
Example: "Attack on Titan - S01E12.mkv"

RULES:
1. Extract episode numbers from file names (look for patterns like E12, ep12, 12, etc.)
2. Preserve file extensions (.mkv, .mp4, etc.)
3. Use the EXACT series name provided (do not translate or modify)
4. If a file is not a video episode (e.g., subtitle, NFO, sample), output "SKIP"
5. For multi-episode files (E01-E02), use format: S01E01-E02
6. Output format: "old_filename.mkv -> new_filename.mkv" (one per line)

IMPORTANT: Extract episode numbers carefully! Common patterns:
- [Group] Series - 12 [1080p].mkv → E12
- Series S01E12.mkv → E12  
- Series 1x12.mkv → E12
- Series.2022.12.mkv → E12 (if it's episodic)
- [12].mkv → E12
"""
        
        # Build user prompt
        user_prompt_parts = [
            f"Series: {series_name}",
            f"Season: {season_number}",
        ]
        
        if episodes:
            user_prompt_parts.append(f"Expected episodes: {', '.join(f'E{e:02d}' for e in sorted(episodes)[:10])}")
        
        user_prompt_parts.append("\nFiles to rename:")
        for i, fname in enumerate(file_names, 1):
            user_prompt_parts.append(f"{i}. {fname}")
        
        user_prompt = "\n".join(user_prompt_parts)
        
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=150 * len(file_names),
                temperature=0.1,
            )
            
            response_text = response.choices[0].message.content.strip()
            
            logger.debug("LLM file normalization response", response=response_text[:500])
            
            # Parse response
            mappings = {}
            for line in response_text.split("\n"):
                line = line.strip()
                if not line or "SKIP" in line.upper():
                    continue
                
                # Parse "old -> new" format
                if "->" in line:
                    parts = line.split("->", 1)
                    if len(parts) == 2:
                        old_name = parts[0].strip()
                        new_name = parts[1].strip()
                        
                        # Remove leading numbers like "1. " from old_name
                        old_name = old_name.lstrip("0123456789. ")
                        
                        # Find matching file name
                        for fname in file_names:
                            if fname == old_name or fname.endswith(old_name):
                                mappings[fname] = new_name
                                break
            
            logger.info(
                "File names normalized",
                input_count=len(file_names),
                output_count=len(mappings),
                skipped=len(file_names) - len(mappings),
            )
            
            return mappings
            
        except Exception as e:
            logger.error("Failed to normalize file names", error=str(e))
            return {}

    async def normalize_subtitle_names(
        self,
        subtitle_files: list[str],
        video_mappings: dict[str, str],
    ) -> dict[str, str]:
        """Normalize subtitle file names to match renamed video files.
        
        Args:
            subtitle_files: List of subtitle file paths
            video_mappings: Dict of old video path -> new video name
            
        Returns:
            Dict mapping old subtitle path to new subtitle name
        """
        if not subtitle_files or not video_mappings:
            return {}
        
        logger.info(
            "Normalizing subtitle names with LLM",
            subtitle_count=len(subtitle_files),
            video_count=len(video_mappings),
        )
        
        system_prompt = """You are a subtitle file renamer for Sonarr. Given video file mappings and subtitle files, 
match subtitles to videos and output normalized subtitle names.

RULES:
1. Match each subtitle to its corresponding video file
2. Extract language code and provider from subtitle name (ru, eng, SovetRomantica, etc.)
3. Format: {Video Base Name}.{lang}.{provider}.{ext}
   - If only language: {Video Base Name}.{lang}.{ext}
   - If no language info: {Video Base Name}.{ext}
4. Move subtitles to root level (remove folder paths)
5. If subtitle doesn't match any video, output "SKIP"

EXAMPLES:
Video: "Attack on Titan - S01E01.mkv"
Subtitle: "folder/[SubsPlease] Shingeki - 01.ru.ass" → "Attack on Titan - S01E01.ru.ass"
Subtitle: "folder/[SubsPlease] Shingeki - 01.ru.SovetRomantica.ass" → "Attack on Titan - S01E01.ru.SovetRomantica.ass"
Subtitle: "folder/[SubsPlease] Shingeki - 01.eng.srt" → "Attack on Titan - S01E01.eng.srt"

OUTPUT FORMAT: "old_path -> new_name" (one per line)"""
        
        # Build user prompt
        user_prompt_parts = ["Video file mappings:"]
        for old_path, new_name in video_mappings.items():
            user_prompt_parts.append(f"  {old_path} → {new_name}")
        
        user_prompt_parts.append("\nSubtitle files to rename:")
        for i, sub_file in enumerate(subtitle_files, 1):
            user_prompt_parts.append(f"{i}. {sub_file}")
        
        user_prompt = "\n".join(user_prompt_parts)
        
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=100 * len(subtitle_files),
                temperature=0.1,
            )
            
            response_text = response.choices[0].message.content.strip()
            
            logger.debug("LLM subtitle normalization response", response=response_text[:500])
            
            # Parse response
            mappings = {}
            for line in response_text.split("\n"):
                line = line.strip()
                if not line or "SKIP" in line.upper():
                    continue
                
                # Parse "old -> new" format or "1. old -> new" format
                if "->" in line:
                    # Remove leading number if present
                    line = line.lstrip("0123456789. ")
                    
                    parts = line.split("->", 1)
                    if len(parts) == 2:
                        old_path = parts[0].strip()
                        new_name = parts[1].strip()
                        
                        # Find matching subtitle file
                        for sub_file in subtitle_files:
                            if sub_file.endswith(old_path) or old_path in sub_file:
                                mappings[sub_file] = new_name
                                break
            
            logger.info(
                "Subtitle names normalized",
                input_count=len(subtitle_files),
                output_count=len(mappings),
                skipped=len(subtitle_files) - len(mappings),
            )
            
            return mappings
            
        except Exception as e:
            logger.error("Failed to normalize subtitle names", error=str(e))
            return {}

