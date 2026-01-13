"""File mapper endpoint for Sonarr integration."""
import structlog
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from openai import AsyncOpenAI
import os
import json

logger = structlog.get_logger()

router = APIRouter(prefix="/api", tags=["filemapper"])

FILEMAPPER_PROMPT = """You are a file-to-episode mapper for Sonarr. 

Given:
- Series name and TVDB ID
- Expected season and episode numbers
- List of files in a folder

Your task: Map each video file to the correct episode number.

RULES:
1. Extract episode number from filename patterns:
   - "ep.01", "ep01", "EP01" → episode 1
   - "- 01 -", "- 01.", " 01 " → episode 1
   - "E01", "e01" → episode 1
   - "S01E01", "S1E1" → episode 1 (ignore season in filename, use provided season)
   - "Part 2 - 01" → episode 1 of Part 2

2. For split-cour (Part 2):
   - If expected episodes start from 13+, this is Part 2
   - Map file episode 01 → first expected episode (e.g., 13)
   - Map file episode 02 → second expected episode (e.g., 14)
   - etc.

3. Subtitle files (.ass, .srt, .sub):
   - Map them the same way as video files
   - Include language code if present: [Group]_rus.ass → S03E13.rus.ass

4. Skip non-media files (nfo, txt, jpg, etc.)

5. Output format - JSON object:
{
  "mappings": [
    {"file": "original_filename.mkv", "episode": "S03E13", "type": "video"},
    {"file": "original_filename.ass", "episode": "S03E13", "lang": "rus", "type": "subtitle"}
  ],
  "unmapped": ["file_that_could_not_be_mapped.mkv"]
}

IMPORTANT:
- Use the PROVIDED season number, not the one from filename
- Episode format must be S00E00 (e.g., S03E13)
- Map ALL video files (.mkv, .mp4, .avi)
- Map ALL subtitle files (.ass, .srt, .sub, .ssa)
"""


class FileMapRequest(BaseModel):
    """Request to map files to episodes."""
    series_name: str
    tvdb_id: int | None = None
    season: int
    expected_episodes: list[int]  # e.g., [13, 14, 15, 16...] for Part 2
    files: list[str]  # List of filenames in the folder


class FileMapping(BaseModel):
    """Single file mapping."""
    file: str
    episode: str  # S03E13 format
    type: str  # "video" or "subtitle"
    lang: str | None = None  # For subtitles


class FileMapResponse(BaseModel):
    """Response with file mappings."""
    mappings: list[FileMapping]
    unmapped: list[str]


@router.post("/map-files", response_model=FileMapResponse)
async def map_files(request: FileMapRequest) -> FileMapResponse:
    """
    Map files in a folder to Sonarr episode numbers using LLM.
    
    Used when Sonarr can't automatically import files due to naming issues.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY not configured")
    
    client = AsyncOpenAI(api_key=api_key)
    
    # Build user prompt
    user_prompt = f"""Series: {request.series_name}
TVDB ID: {request.tvdb_id or 'unknown'}
Season: {request.season}
Expected episodes: {request.expected_episodes}

Files in folder:
{chr(10).join(f'- {f}' for f in request.files)}

Map each file to the correct episode. Remember:
- Season is {request.season}
- First expected episode is {request.expected_episodes[0] if request.expected_episodes else 1}
- If files are numbered 01, 02, 03... and expected episodes are {request.expected_episodes[:3] if len(request.expected_episodes) >= 3 else request.expected_episodes}..., map accordingly.
"""
    
    logger.info(
        "Mapping files to episodes",
        series=request.series_name,
        season=request.season,
        expected_episodes=request.expected_episodes[:5],
        file_count=len(request.files),
    )
    
    try:
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": FILEMAPPER_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=2000,
            temperature=0.1,
            response_format={"type": "json_object"},
        )
        
        result_text = response.choices[0].message.content.strip()
        logger.debug("LLM response", response=result_text[:500])
        
        # Parse JSON response
        result = json.loads(result_text)
        
        mappings = []
        for m in result.get("mappings", []):
            mappings.append(FileMapping(
                file=m["file"],
                episode=m["episode"],
                type=m.get("type", "video"),
                lang=m.get("lang"),
            ))
        
        unmapped = result.get("unmapped", [])
        
        logger.info(
            "Files mapped successfully",
            mapped_count=len(mappings),
            unmapped_count=len(unmapped),
        )
        
        return FileMapResponse(mappings=mappings, unmapped=unmapped)
        
    except json.JSONDecodeError as e:
        logger.error("Failed to parse LLM response as JSON", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to parse LLM response")
    except Exception as e:
        logger.error("Failed to map files", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))

