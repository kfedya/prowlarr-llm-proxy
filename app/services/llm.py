import json
import re
from openai import AsyncOpenAI
import structlog

logger = structlog.get_logger()

SYSTEM_PROMPT = """You are a media title parser. Your task is to parse torrent titles (often in Russian or mixed languages) and convert them to a standardized format that Sonarr/Radarr can understand.

For TV shows, output format: {Series Name} S{season:02d}E{episode:02d} {quality}
For movies, output format: {Movie Name} ({year}) {quality}

Rules:
1. Extract the English title if available, otherwise transliterate Russian to English
2. Season format: S01, S02, etc.
3. Episode format: E01, E02, or E01-E16 for ranges
4. Quality: 2160p, 1080p, 720p, etc. Include source if clear (BluRay, WEB-DL, HDTV)
5. Keep it simple - Sonarr needs: Title, Season, Episode, Quality
6. If multiple episodes, use E01-E16 format
7. Remove all extra info like audio tracks, subtitles, release group names

Examples:
Input: "Во все тяжкие / Breaking Bad / Сезон: 5 / Серии: 1-16 из 16 [2012-2013, драма, BDRemux 1080p]"
Output: "Breaking Bad S05E01-E16 1080p BluRay"

Input: "Игра престолов / Game of Thrones (Сезон 1, Серия 5) [WEB-DL 720p]"
Output: "Game of Thrones S01E05 720p WEB-DL"

Input: "Интерстеллар / Interstellar (2014) [BDRip 2160p 4K]"
Output: "Interstellar (2014) 2160p BluRay"

Input: "Аватар: Путь воды / Avatar: The Way of Water (2022) UHD BDRemux 2160p"
Output: "Avatar The Way of Water (2022) 2160p BluRay"

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

    async def parse_titles_batch(self, titles: list[str]) -> list[str]:
        """
        Parse multiple titles. Uses individual requests for now,
        could be optimized with batch API later.
        """
        results = []
        for title in titles:
            normalized = await self.parse_title(title)
            results.append(normalized)
        return results

    def clear_cache(self) -> None:
        """Clear the title cache."""
        self._cache.clear()
        logger.info("LLM cache cleared")

