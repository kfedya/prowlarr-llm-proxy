from openai import AsyncOpenAI
import structlog
from dataclasses import dataclass

logger = structlog.get_logger()

SYSTEM_PROMPT = """Parse torrent title into Sonarr-compatible format. Keep all technical info!

FORMAT:

1. TV SHOWS & ANIME (default - use seasons):
   {Name} S{ss}E{ee} {quality} {source} {video} {audio} {languages} {subs}-{group}
   Example: "Attack on Titan S01E01 1080p WEB-DL x264 AAC Japanese Russian Subs-SubsPlease"

2. ABSOLUTE NUMBERING - ONLY when episode number >= 100:
   {Name} - {episode} {quality} {source} {video} {audio} {languages}-{group}
   Example: "One Piece - 1123 1080p WEB-DL x264 AAC Japanese-Erai-raws"
   
   USE FOR: episodes 100+, or One Piece, Naruto, Bleach, Dragon Ball, Detective Conan, Fairy Tail

3. SEASON PACK (no specific episodes):
   {Name} S{ss} {quality} {source} {video} {audio} {languages}-{group}
   Example: "Breaking Bad S05 1080p BluRay x264 DTS English Russian-SPARKS"

4. MOVIES:
   {Name} ({year}) {quality} {source} {video} {audio} {languages}-{group}
   Example: "Interstellar (2014) 2160p BluRay x265 DTS-HD English-SPARKS"

FIELD RULES:
- Name: English title (extract from Russian, e.g. "Атака титанов / Attack on Titan" → "Attack on Titan")
- Quality: 2160p, 1080p, 720p, 480p
- Source: BluRay, WEB-DL, WEBRip, HDTV, DVDRip (BDRemux/BDRip→BluRay)
- Video: x264, x265, HEVC, AV1, XviD (if present)
- HDR: HDR, HDR10, HDR10+, DV (Dolby Vision) - add if present
- Audio: AAC, AC3, DTS, DTS-HD, TrueHD, FLAC (if present)
- Languages: Japanese, English, Russian, etc. (JAP→Japanese, RUS→Russian, ENG→English)
- Subs: "Subs" or "Russian Subs", "English Subs" if subtitle info present
- Group: Release group at the end after hyphen (SubsPlease, Erai-raws, LostFilm, etc.)

Category 5070 = Anime, 5000 = TV

EXAMPLES:

Title: "Атака титанов / Shingeki no Kyojin / Сезон 1 / Серии 1-25 [JAP+RUS] [WEB-DL 1080p x264 AAC] SubsPlease"
Category: 5070
→ Attack on Titan S01E01-E25 1080p WEB-DL x264 AAC Japanese Russian-SubsPlease

Title: "Ван-Пис / One Piece [1123-1155] WEB-DL 1080p HEVC JAP+SUB Erai-raws"
Category: 5070
→ One Piece - 1123-1155 1080p WEB-DL HEVC Japanese Subs-Erai-raws

Title: "Клинок, рассекающий демонов / Kimetsu no Yaiba / S03E05 [WEBRip 1080p x264] JAP DUB RUS"
Category: 5070
→ Demon Slayer S03E05 1080p WEBRip x264 Japanese Russian-NoGroup

Title: "Во все тяжкие / Breaking Bad / Сезон 5 [BDRemux 1080p x264 DTS] ENG+RUS LostFilm"
Category: 5000
→ Breaking Bad S05 1080p BluRay x264 DTS English Russian-LostFilm

Title: "Интерстеллар / Interstellar (2014) [UHD BDRemux 2160p HDR10 x265 TrueHD] RUS"
Category: 2000
→ Interstellar (2014) 2160p BluRay HDR10 x265 TrueHD Russian-NoGroup

Output ONLY the normalized title, nothing else."""


@dataclass
class TorrentItem:
    """Data extracted from a Torznab item."""
    title: str
    category: str = ""
    
    def to_prompt(self) -> str:
        """Format item data for LLM prompt."""
        if self.category:
            return f"Title: {self.title}\nCategory: {self.category}"
        return self.title


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

