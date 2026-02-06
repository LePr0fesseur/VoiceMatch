"""Indexer module - manages the voice database from uploaded audio files."""

import logging
import shutil
from pathlib import Path
from typing import Optional

from . import audio, database
from .config import VOICES_DIR

logger = logging.getLogger(__name__)


def index_audio_file(
    file_path: Path,
    dubber_name: str,
    original_filename: str = "",
) -> Optional[dict]:
    """Index an audio file: extract embedding and store in database.

    Args:
        file_path: Path to the audio file (WAV format, 16kHz mono).
        dubber_name: Name of the voice actor / dubber.
        original_filename: Original filename for reference.

    Returns:
        Dict with actor_id, sample_id, dubber name on success, None on failure.
    """
    # Extract embedding
    embedding = audio.extract_embedding_from_file(file_path)
    if embedding is None:
        logger.error("Failed to extract voice embedding from: %s", file_path)
        return None

    # Create or find actor
    actor_id = database.find_or_create_actor(name=dubber_name, language="fr")

    # Save audio permanently
    filename = original_filename or file_path.name
    permanent_path = VOICES_DIR / f"actor_{actor_id}" / filename
    permanent_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(file_path), str(permanent_path))

    # Get audio duration
    audio_data = audio.load_audio(file_path)
    duration = len(audio_data) / 16000 if audio_data is not None else 0.0

    # Store in database
    sample_id = database.add_voice_sample(
        actor_id=actor_id,
        embedding=embedding,
        audio_path=str(permanent_path),
        description=f"Upload: {filename}",
        duration=duration,
    )

    logger.info("Indexed voice sample for: %s (actor_id=%d)", dubber_name, actor_id)

    return {
        "actor_id": actor_id,
        "sample_id": sample_id,
        "dubber": dubber_name,
    }
