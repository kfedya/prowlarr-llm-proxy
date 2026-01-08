from openai import AsyncOpenAI
import structlog
from dataclasses import dataclass

logger = structlog.get_logger()

SYSTEM_PROMPT = """Parse torrent title into Sonarr-compatible format.

CRITICAL NAME RULE:
- Use EXACTLY the English name from the title - DO NOT modify, translate, or add words!
- "Тодзима хочет стать Камен Райдером / Tojima Wants to Be a Kamen Rider" → "Tojima Wants to Be a Kamen Rider"
- If multiple English names exist, use the SHORTEST common one
- If NO English name exists, transliterate the romanji/Japanese name as-is
- NEVER add character names, subtitles, or extra words not in the English title!

FORMAT:

1. TV SHOWS & ANIME (default - use seasons):
   {Name} S{ss}E{ee} {quality} {source} {video} {audio} {languages} {subs}-{group}

2. ABSOLUTE NUMBERING - ONLY when episode >= 100:
   {Name} - {episode} {quality} {source} {video} {audio} {languages}-{group}
   USE FOR: One Piece, Naruto, Bleach, Dragon Ball, Detective Conan, Fairy Tail, Gintama

3. SEASON PACK (full season, no specific episodes):
   {Name} S{ss} {quality} {source} {video} {audio} {languages}-{group}

4. MOVIES:
   {Name} ({year}) {quality} {source} {video} {audio} {languages}-{group}

FIELD RULES:
- Season: (ТВ-1)=S01, (ТВ-2)=S02, [TV]=S01, "Сезон 1"=S01
- Episodes: "[25 из 25]"=E01-E25, "[12 из 24]"=E01-E12, "Серии 1-25"=E01-E25
- Quality: 2160p/1080p/720p/480p
- Source: BluRay, WEB-DL, WEBRip, HDTV (BDRemux/BDRip→BluRay)
- Video: x264, x265, HEVC, AV1
- HDR: HDR, HDR10, HDR10+, DV
- Audio: AAC, AC3, DTS, DTS-HD, TrueHD
- Languages: JAP→Japanese, RUS→Russian, ENG→English
- Subs: "+Sub"/"RUS(ext)"→Russian Subs, "ENG Sub"→English Subs
- Group: at end after hyphen, or "NoGroup"

EXAMPLES:

"Тодзима хочет стать Камен Райдером / Toujima Tanzaburou wa Kamen Rider ni Naritai / Tojima Wants to Be a Kamen Rider [13 из 13] [WEB-DL 1080p] JAP+RUS"
→ Tojima Wants to Be a Kamen Rider S01E01-E13 1080p WEB-DL Japanese Russian-NoGroup

"Атака титанов (ТВ-1) / Shingeki no Kyojin / Attack on Titan [25 из 25] [BDRip 1080p] JAP+Sub"
→ Attack on Titan S01E01-E25 1080p BluRay Japanese Subs-NoGroup

"Ван-Пис / One Piece [1123-1155] WEB-DL 1080p HEVC JAP+SUB Erai-raws"
→ One Piece - 1123-1155 1080p WEB-DL HEVC Japanese Subs-Erai-raws

"Во все тяжкие / Breaking Bad / Сезон 5 [BDRemux 1080p DTS] ENG+RUS LostFilm"
→ Breaking Bad S05 1080p BluRay DTS English Russian-LostFilm

"Интерстеллар / Interstellar (2014) [2160p HDR10 x265 TrueHD] RUS"
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
        Parse multiple torrent items in parallel.
        """
        import asyncio
        tasks = [self.parse_item(item) for item in items]
        return await asyncio.gather(*tasks)

    def clear_cache(self) -> None:
        """Clear the title cache."""
        self._cache.clear()
        logger.info("LLM cache cleared")

