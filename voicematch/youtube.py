"""YouTube search and audio extraction module."""

import logging
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from .config import TEMP_DIR, YT_MAX_RESULTS, YT_SEARCH_TERMS

logger = logging.getLogger(__name__)


def search_youtube(query: str, max_results: int = YT_MAX_RESULTS) -> list[dict]:
    """Search YouTube for voice dubbing videos using yt-dlp."""
    try:
        cmd = [
            "yt-dlp",
            f"ytsearch{max_results}:{query}",
            "--dump-json",
            "--flat-playlist",
            "--no-download",
            "--quiet",
        ]
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=60
        )
        if result.returncode != 0:
            logger.error("yt-dlp search failed: %s", result.stderr)
            return []

        import json

        videos = []
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            try:
                data = json.loads(line)
                videos.append({
                    "id": data.get("id", ""),
                    "url": data.get("url", f"https://www.youtube.com/watch?v={data.get('id', '')}"),
                    "title": data.get("title", ""),
                    "duration": data.get("duration"),
                    "channel": data.get("channel", data.get("uploader", "")),
                })
            except json.JSONDecodeError:
                continue
        return videos
    except subprocess.TimeoutExpired:
        logger.error("YouTube search timed out for query: %s", query)
        return []
    except FileNotFoundError:
        logger.error("yt-dlp not found. Install it: pip install yt-dlp")
        return []


def search_dubbing_videos(actor_name: str = "") -> list[dict]:
    """Search for French dubbing videos, optionally filtering by actor name."""
    all_videos = []
    seen_ids = set()

    for term in YT_SEARCH_TERMS:
        query = f"{term} {actor_name}".strip()
        videos = search_youtube(query, max_results=YT_MAX_RESULTS)
        for v in videos:
            if v["id"] not in seen_ids:
                seen_ids.add(v["id"])
                all_videos.append(v)

    return all_videos


def download_audio(url: str, output_dir: Optional[Path] = None) -> Optional[Path]:
    """Download audio from a YouTube video and return the path to the WAV file."""
    if output_dir is None:
        output_dir = TEMP_DIR

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "%(id)s.%(ext)s"

    try:
        cmd = [
            "yt-dlp",
            "-x",
            "--audio-format", "wav",
            "--audio-quality", "0",
            "--postprocessor-args", "-ar 16000 -ac 1",
            "-o", str(output_path),
            "--no-playlist",
            "--quiet",
            url,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            logger.error("Audio download failed: %s", result.stderr)
            return None

        # Find the downloaded file
        wav_files = list(output_dir.glob("*.wav"))
        if wav_files:
            # Return the most recently modified wav file
            return max(wav_files, key=lambda f: f.stat().st_mtime)

        logger.error("No WAV file found after download")
        return None

    except subprocess.TimeoutExpired:
        logger.error("Download timed out for: %s", url)
        return None
    except FileNotFoundError:
        logger.error("yt-dlp not found. Install it: pip install yt-dlp")
        return None


def parse_actor_from_title(title: str) -> dict:
    """Extract actor/dubber information from a YouTube video title.

    Common patterns:
    - "La voix française de Jim Carrey - Emmanuel Curtil"
    - "Doubleur : Emmanuel Curtil (Jim Carrey, Adam Sandler)"
    - "Emmanuel Curtil - doubleur de Jim Carrey"
    - "Voix FR de [acteur] par [doubleur]"
    """
    info = {"dubber": "", "original_actor": "", "raw_title": title}

    # Clean title
    title_clean = title.strip()

    # Pattern: "voix française de [ORIGINAL] - [DOUBLEUR]"
    m = re.search(
        r"voix\s+fran[çc]aise\s+de\s+([^-–]+)[-–]\s*(.+)",
        title_clean,
        re.IGNORECASE,
    )
    if m:
        info["original_actor"] = m.group(1).strip()
        info["dubber"] = m.group(2).strip()
        return info

    # Pattern: "doubleur de [ORIGINAL] : [DOUBLEUR]" or "[DOUBLEUR] doubleur de [ORIGINAL]"
    m = re.search(
        r"doubleu[rs]e?\s*(?:de|:)\s*([^-–:(]+?)(?:\s*[-–:]\s*(.+))?$",
        title_clean,
        re.IGNORECASE,
    )
    if m:
        info["original_actor"] = m.group(1).strip()
        if m.group(2):
            info["dubber"] = m.group(2).strip()
        return info

    # Pattern: "[DOUBLEUR] - doubleur/voix de [ORIGINAL]"
    m = re.search(
        r"(.+?)\s*[-–]\s*(?:doubleu[rs]e?|voix)\s+(?:de\s+)?(.+)",
        title_clean,
        re.IGNORECASE,
    )
    if m:
        info["dubber"] = m.group(1).strip()
        info["original_actor"] = m.group(2).strip()
        return info

    # Pattern: "[DOUBLEUR] double [ORIGINAL]"
    m = re.search(
        r"(.+?)\s+double\s+(.+)",
        title_clean,
        re.IGNORECASE,
    )
    if m:
        info["dubber"] = m.group(1).strip()
        info["original_actor"] = m.group(2).strip()
        return info

    # Pattern: "voix FR : [DOUBLEUR] ([ORIGINAL])"
    m = re.search(
        r"voix\s+(?:fr|française?)\s*:\s*(.+?)\s*\(([^)]+)\)",
        title_clean,
        re.IGNORECASE,
    )
    if m:
        info["dubber"] = m.group(1).strip()
        info["original_actor"] = m.group(2).strip()
        return info

    # Fallback: if "doubleur" is in title, try to split on common delimiters
    if re.search(r"doubleu[rs]e?|doublage", title_clean, re.IGNORECASE):
        # Try splitting on dash/colon
        parts = re.split(r"\s*[-–:|]\s*", title_clean)
        if len(parts) >= 2:
            # Heuristic: the part with "doubleur" likely contains the dubber
            for i, part in enumerate(parts):
                if re.search(r"doubleu[rs]e?", part, re.IGNORECASE):
                    cleaned = re.sub(
                        r"doubleu[rs]e?\s*(?:français[e]?)?\s*(?:de\s+)?",
                        "",
                        part,
                        flags=re.IGNORECASE,
                    ).strip()
                    if cleaned:
                        info["original_actor"] = cleaned
                    # The other part is likely the dubber name
                    other_parts = [p for j, p in enumerate(parts) if j != i]
                    if other_parts:
                        info["dubber"] = other_parts[0].strip()
                    break

    # Clean up parenthetical content from names
    for key in ["dubber", "original_actor"]:
        if info[key]:
            # Remove common noise words
            info[key] = re.sub(r"\s*#\w+", "", info[key])  # hashtags
            info[key] = re.sub(r"\s*\(.*?\)", "", info[key]).strip()  # parenthetical
            info[key] = info[key].strip(" -–:|")

    return info
