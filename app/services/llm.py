import json
import re
from openai import AsyncOpenAI
import structlog

logger = structlog.get_logger()

SYSTEM_PROMPT = """You are a media title parser. Your task is to parse torrent titles (often in Russian or mixed languages) and convert them to a standardized format that Sonarr/Radarr can understand.

FORMAT RULES:

1. For REGULAR TV SHOWS with seasons:
   Format: {Series Name} S{season:02d}E{episode:02d} {quality}
   Example: "Breaking Bad S05E01-E16 1080p BluRay"

2. For ANIME with high episode numbers (100+) or no clear season - USE ABSOLUTE NUMBERING:
   Format: {Series Name} - {episode} {quality}
   Example: "One Piece - 1123-1155 1080p WEB-DL"
   Example: "Naruto Shippuden - 450 720p WEB-DL"

3. For MOVIES:
   Format: {Movie Name} ({year}) {quality}
   Example: "Interstellar (2014) 2160p BluRay"

GENERAL RULES:
- Extract the English title if available, otherwise transliterate Russian to English
- Quality: 2160p, 1080p, 720p, etc. Include source if clear (BluRay, WEB-DL, HDTV)
- Remove all extra info like audio tracks, subtitles, release group names
- For episode ranges use hyphen: E01-E16 or 1123-1155

ANIME DETECTION:
- One Piece, Naruto, Bleach, Dragon Ball, Attack on Titan, etc. = absolute numbering
- Episode numbers > 100 with no season = absolute numbering
- If title has "серия 1123" or similar high numbers = absolute numbering

Examples:
Input: "Во все тяжкие / Breaking Bad / Сезон: 5 / Серии: 1-16 из 16 [2012-2013, драма, BDRemux 1080p]"
Output: "Breaking Bad S05E01-E16 1080p BluRay"

Input: "Ван-Пис / One Piece [1123-1155 из 1xxx] WEB-DL 1080p"
Output: "One Piece - 1123-1155 1080p WEB-DL"

Input: "Наруто: Ураганные хроники / Naruto Shippuuden [серия 450] 720p"
Output: "Naruto Shippuden - 450 720p"

Input: "Игра престолов / Game of Thrones (Сезон 1, Серия 5) [WEB-DL 720p]"
Output: "Game of Thrones S01E05 720p WEB-DL"

Input: "Интерстеллар / Interstellar (2014) [BDRip 2160p 4K]"
Output: "Interstellar (2014) 2160p BluRay"

Respond with ONLY the normalized title, nothing else."""


class LLMService:
    """Service for parsing torrent titles using OpenAI."""

    def __init__(self, api_key: str, model: str = "gpt-4o-mini"):
        self._client = AsyncOpenAI(api_key=api_key)
        self._model = model
        self._cache: dict[str, str] = {}
        logger.info("LLMService initialized", model=model)

    async def parse_title(self, raw_title: str) -> str:
        """
        Parse a raw torrent title into Sonarr-compatible format.
        Returns the normalized title.
        """
        # Check cache first
        if raw_title in self._cache:
            logger.debug("Cache hit for title", raw_title=raw_title[:50])
            return self._cache[raw_title]

        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": raw_title},
                ],
                max_tokens=150,
                temperature=0.1,  # Low temperature for consistent output
            )

            normalized = response.choices[0].message.content.strip()
            
            # Basic validation - should not be empty
            if not normalized:
                logger.warning("LLM returned empty title", raw_title=raw_title[:50])
                return raw_title

            # Cache the result
            self._cache[raw_title] = normalized
            
            logger.info(
                "Title parsed",
                raw=raw_title[:80],
                normalized=normalized,
            )
            
            return normalized

        except Exception as e:
            logger.error("Failed to parse title with LLM", error=str(e), raw_title=raw_title[:50])
            return raw_title

    async def parse_titles_batch(self, titles: list[str], concurrency: int = 10) -> list[str]:
        """
        Parse multiple titles in parallel for better performance.
        """
        import asyncio
        
        semaphore = asyncio.Semaphore(concurrency)
        
        async def parse_with_semaphore(title: str) -> str:
            async with semaphore:
                return await self.parse_title(title)
        
        tasks = [parse_with_semaphore(title) for title in titles]
        return await asyncio.gather(*tasks)

    def clear_cache(self) -> None:
        """Clear the title cache."""
        self._cache.clear()
        logger.info("LLM cache cleared")

