"""Indexer module - builds the voice database from YouTube videos."""

import logging
import os
from pathlib import Path
from typing import Optional

from . import audio, database, youtube
from .config import VOICES_DIR, TEMP_DIR

logger = logging.getLogger(__name__)


def index_youtube_video(url: str, title: str = "") -> Optional[dict]:
    """Download a YouTube video, extract voice embedding, and store in database.

    Returns actor info dict on success, None on failure.
    """
    # Download audio
    audio_path = youtube.download_audio(url, output_dir=TEMP_DIR)
    if audio_path is None:
        logger.error("Failed to download audio from: %s", url)
        return None

    try:
        # Extract embedding
        embedding = audio.extract_embedding_from_file(audio_path)
        if embedding is None:
            logger.error("Failed to extract voice embedding from: %s", url)
            return None

        # Parse actor info from title
        if not title:
            title = _get_video_title(url)

        actor_info = youtube.parse_actor_from_title(title)
        dubber_name = actor_info["dubber"] or "Inconnu"
        original_actor = actor_info["original_actor"] or ""

        # Store in database
        actor_id = database.find_or_create_actor(
            name=dubber_name,
            original_actor=original_actor,
            language="fr",
        )

        # Save audio to permanent storage
        permanent_path = VOICES_DIR / f"actor_{actor_id}" / audio_path.name
        permanent_path.parent.mkdir(parents=True, exist_ok=True)

        import shutil
        shutil.copy2(str(audio_path), str(permanent_path))

        # Store embedding
        sample_id = database.add_voice_sample(
            actor_id=actor_id,
            embedding=embedding,
            youtube_url=url,
            youtube_title=title,
            audio_path=str(permanent_path),
            duration=len(audio.load_audio(audio_path)) / 16000,
        )

        logger.info(
            "Indexed: %s (dubber: %s, original: %s)",
            title,
            dubber_name,
            original_actor,
        )

        return {
            "actor_id": actor_id,
            "sample_id": sample_id,
            "dubber": dubber_name,
            "original_actor": original_actor,
            "youtube_url": url,
            "title": title,
        }

    finally:
        # Clean up temp file
        try:
            audio_path.unlink()
        except OSError:
            pass


def index_from_search(
    query: str = "",
    max_videos: int = 10,
    progress_callback=None,
) -> list[dict]:
    """Search YouTube for dubbing videos and index them.

    Args:
        query: Search query (actor name, etc.). Empty = general dubbing search.
        max_videos: Maximum number of videos to index.
        progress_callback: Optional callback(current, total, info_dict) for progress.

    Returns:
        List of successfully indexed video info dicts.
    """
    # Search YouTube
    videos = youtube.search_dubbing_videos(query)
    if not videos:
        logger.warning("No videos found for query: %s", query)
        return []

    # Limit
    videos = videos[:max_videos]
    indexed = []

    for i, video in enumerate(videos):
        url = video["url"]
        if not url.startswith("http"):
            url = f"https://www.youtube.com/watch?v={video['id']}"

        if progress_callback:
            progress_callback(i + 1, len(videos), video)

        logger.info("Indexing %d/%d: %s", i + 1, len(videos), video["title"])

        result = index_youtube_video(url, title=video["title"])
        if result:
            indexed.append(result)

    logger.info("Indexed %d/%d videos successfully", len(indexed), len(videos))
    return indexed


def index_single_url(url: str) -> Optional[dict]:
    """Index a single YouTube URL (user-provided)."""
    # First get the title
    title = _get_video_title(url)
    return index_youtube_video(url, title=title)


def _get_video_title(url: str) -> str:
    """Get the title of a YouTube video."""
    import subprocess
    import json

    try:
        cmd = [
            "yt-dlp",
            "--dump-json",
            "--no-download",
            "--quiet",
            url,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            data = json.loads(result.stdout)
            return data.get("title", "")
    except Exception as e:
        logger.error("Failed to get video title: %s", e)

    return ""
