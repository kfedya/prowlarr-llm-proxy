from openai import AsyncOpenAI
import structlog
from dataclasses import dataclass

logger = structlog.get_logger()

SYSTEM_PROMPT = """You are a media title parser for Sonarr/Radarr. Parse torrent info and output a clean title that Sonarr can understand.

OUTPUT FORMAT (choose based on content type):

1. REGULAR TV SHOWS (with seasons):
   {Series Name} S{season:02d}E{episode:02d} {quality} {source}
   Example: "Breaking Bad S05E01 1080p BluRay"
   For ranges: "Breaking Bad S05E01-E16 1080p BluRay"

2. ANIME (use absolute episode numbering - NO seasons!):
   {Series Name} - {episode:03d} {quality} {source}
   Example: "Attack on Titan - 001 1080p WEB-DL"
   For ranges: "One Piece - 1123-1155 1080p WEB-DL"
   
   IMPORTANT: Anime like One Piece, Naruto, Bleach, Dragon Ball, Attack on Titan, 
   Demon Slayer, Jujutsu Kaisen, etc. MUST use absolute numbering, NOT S01E01 format!

3. SEASON PACKS (multiple episodes, no specific episode numbers):
   {Series Name} S{season:02d} {quality} {source}
   Example: "Breaking Bad S05 1080p BluRay"

4. MOVIES:
   {Movie Name} ({year}) {quality} {source}
   Example: "Interstellar (2014) 2160p BluRay"

RULES:
- Use English title (extract from Russian if needed, e.g. "Атака титанов / Attack on Titan" → "Attack on Titan")
- Quality: 2160p, 1080p, 720p, 480p
- Source: BluRay, WEB-DL, WEBRip, HDTV, DVDRip
- Remove: audio info, subtitles, release groups, file sizes, years for TV shows
- For anime season packs without episode numbers, still use absolute format if possible

EXAMPLES:

Input title: "Во все тяжкие / Breaking Bad / Сезон: 5 / Серии: 1-16 из 16"
Input description: "BDRemux 1080p, Eng+Rus audio"
Output: "Breaking Bad S05E01-E16 1080p BluRay"

Input title: "Ван-Пис / One Piece [1123-1155 из 1xxx]"
Input description: "WEB-DL 1080p"
Output: "One Piece - 1123-1155 1080p WEB-DL"

Input title: "Атака титанов / Shingeki no Kyojin / Сезон 4"
Input description: "WEB-DL 1080p, полный сезон"
Output: "Attack on Titan S04 1080p WEB-DL"

Input title: "Наруто: Ураганные хроники [серия 450]"
Input description: "720p"
Output: "Naruto Shippuden - 450 720p"

Respond with ONLY the normalized title, nothing else."""


@dataclass
class TorrentItem:
    """Data extracted from a Torznab item."""
    title: str
    description: str = ""
    category: str = ""
    size: int = 0
    
    def to_prompt(self) -> str:
        """Format item data for LLM prompt."""
        parts = [f"Title: {self.title}"]
        if self.description:
            parts.append(f"Description: {self.description}")
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
        Uses title, description, and other metadata for better parsing.
        Returns the normalized title.
        """
        # Create cache key from all relevant data
        cache_key = f"{item.title}|{item.description}|{item.category}"
        
        # Check cache first
        if cache_key in self._cache:
            logger.debug("Cache hit for title", raw_title=item.title[:50])
            return self._cache[cache_key]

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

            # Cache the result
            self._cache[cache_key] = normalized
            
            logger.info(
                "Title parsed",
                raw=item.title[:80],
                description=item.description[:50] if item.description else None,
                normalized=normalized,
            )
            
            return normalized

        except Exception as e:
            logger.error("Failed to parse title with LLM", error=str(e), raw_title=item.title[:50])
            return item.title

    async def parse_items_batch(self, items: list[TorrentItem]) -> list[str]:
        """
        Parse multiple torrent items sequentially.
        """
        results = []
        for item in items:
            normalized = await self.parse_item(item)
            results.append(normalized)
        return results

    def clear_cache(self) -> None:
        """Clear the title cache."""
        self._cache.clear()
        logger.info("LLM cache cleared")

