from openai import AsyncOpenAI
import structlog
from dataclasses import dataclass

logger = structlog.get_logger()

SYSTEM_PROMPT = """Parse torrent title for Sonarr. Output ONLY the normalized title.

RULE #1 - NAME (MOST IMPORTANT):
The "Series:" field contains the base name Sonarr expects. Use it BUT:
- REMOVE season indicators from the name: "S2", "2nd Season", "Season 2", "Part 2", etc.
- Put the season number in the S{season} field instead
Example: Series: "Golden Kamuy 2nd Season" → "Golden Kamuy - S02"
Example: Series: "Attack on Titan" → "Attack on Titan"
IGNORE all other names in the title (Russian, Japanese, romanji) - use ONLY Series field!

RULE #2 - LANGUAGES (short codes at the end):
- JAP/JAP+Sub → [JA]
- RUS/RUS(ext) → [RU]
- JAP+RUS or RUS(ext), JAP+Sub → [JA][RU]
- ENG → [EN]

RULE #3 - EPISODES:
- "[13 из 13]" or "[1-13 из 24]" → S01E01-E13 (range from 1 to first number)
- "[TV]" or "(ТВ-1)" → S01
- "(ТВ-2)" → S02
- "[1123-1155]" (absolute numbers, no "из") → 1123-1155 (no S/E prefix)

RULE #4 - QUALITY (ALWAYS include resolution!):
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

EXAMPLES:

Title: "Тодзима / Toujima Tanzaburou wa Kamen Rider ni Naritai [1-13 из 24] [RUS(ext), JAP+Sub] [WEB-DL 1080p]"
Series: Tojima Wants to Be a Kamen Rider
→ Tojima Wants to Be a Kamen Rider - S01E01-E13 - [WEBDL-1080p][JA][RU]

Title: "Атака титанов (ТВ-1) / Shingeki no Kyojin [25 из 25] [JAP+Sub] [BDRip 1080p]"
Series: Attack on Titan
→ Attack on Titan - S01E01-E25 - [Bluray-1080p][JA]

Title: "Ван-Пис / One Piece [1123-1155] WEB-DL 1080p JAP+SUB"
Series: One Piece
→ One Piece - 1123-1155 - [WEBDL-1080p][JA]

Title: "Наруто / Naruto [TV] [720p] [JAP+RUS]"
Series: Naruto
→ Naruto - S01 - [HDTV-720p][JA][RU]

Title: "Атака титанов / Shingeki no Kyojin [25 из 25] [BDRemux] [JAP+RUS]"
Series: Attack on Titan
→ Attack on Titan - S01E01-E25 - Bluray.1080p.Remux [JA][RU]

Title: "Золотое божество 2 / Golden Kamuy 2nd Season [12 из 12] [WEB-DL 1080p] [JAP+Sub]"
Series: Golden Kamuy 2nd Season
→ Golden Kamuy - S02E01-E12 - [WEBDL-1080p][JA]"""


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
    """Service for parsing torrent titles using OpenAI."""

    def __init__(self, api_key: str, model: str = "gpt-4o-mini"):
        self._client = AsyncOpenAI(api_key=api_key)
        self._model = model
        self._cache: dict[str, str] = {}
        logger.info("LLMService initialized", model=model)

    async def parse_item(self, item: TorrentItem) -> str:
        """
        Parse a torrent item into Sonarr-compatible format.
        Returns the normalized title.
        """
        # Check cache first (key is just the title)
        if item.title in self._cache:
            logger.debug("Cache hit for title", raw_title=item.title[:50])
            return self._cache[item.title]

        try:
            # Build prompt with all available info
            user_prompt = item.to_prompt()
            
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=150,
                temperature=0.1,  # Low temperature for consistent output
            )

            normalized = response.choices[0].message.content.strip()
            
            # Basic validation - should not be empty
            if not normalized:
                logger.warning("LLM returned empty title", raw_title=item.title[:50])
                return item.title

            # Add [RUS] suffix if original title ends with RUS (from Prowlarr)
            if item.title.rstrip().upper().endswith("RUS"):
                normalized = f"{normalized}[RUS]"

            # Cache the result
            self._cache[item.title] = normalized
            
            logger.info(
                "Title parsed",
                raw=item.title[:80],
                normalized=normalized,
            )
            
            return normalized

        except Exception as e:
            logger.error("Failed to parse title with LLM", error=str(e), raw_title=item.title[:50])
            return item.title

    async def parse_items_batch(self, items: list[TorrentItem]) -> list[str]:
        """
        Parse multiple torrent items in parallel.
        """
        import asyncio
        tasks = [self.parse_item(item) for item in items]
        return await asyncio.gather(*tasks)

    def clear_cache(self) -> None:
        """Clear the title cache."""
        self._cache.clear()
        logger.info("LLM cache cleared")

