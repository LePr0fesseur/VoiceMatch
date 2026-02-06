"""Indexer module - manages the voice database from uploaded audio files.

Uses the enhanced pipeline for robust single-sample enrollment:
- Multi-segment embedding extraction with averaging
- Data augmentation (speed variants)
- MFCC profile extraction for score fusion during matching
"""

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
    """Index an audio file: extract robust embedding + MFCC profile and store.

    Uses the enhanced pipeline:
    1. Load audio
    2. Extract robust embedding (preprocessing + multi-segment + augmentation)
    3. Extract MFCC profile (13 MFCC + 13 delta + 13 ddelta with CMVN)
    4. Store both in database for dual-scoring during matching

    Args:
        file_path: Path to the audio file (WAV format, 16kHz mono).
        dubber_name: Name of the voice actor / dubber.
        original_filename: Original filename for reference.

    Returns:
        Dict with actor_id, sample_id, dubber name on success, None on failure.
    """
    # Load raw audio
    raw_audio = audio.load_audio(file_path)
    if raw_audio is None:
        logger.error("Failed to load audio from: %s", file_path)
        return None

    # Extract robust embedding (preprocessed, multi-segment, augmented)
    embedding = audio.extract_robust_embedding(raw_audio)
    if embedding is None:
        logger.error("Failed to extract robust embedding from: %s", file_path)
        return None

    # Extract MFCC profile from preprocessed audio
    preprocessed = audio.preprocess_audio(raw_audio)
    mfcc_profile = audio.extract_mfcc_profile(preprocessed)
    if mfcc_profile is None:
        logger.warning("MFCC extraction failed for %s, continuing without it", file_path)

    # Create or find actor
    actor_id = database.find_or_create_actor(name=dubber_name, language="fr")

    # Save audio permanently
    filename = original_filename or file_path.name
    permanent_path = VOICES_DIR / f"actor_{actor_id}" / filename
    permanent_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(file_path), str(permanent_path))

    # Get audio duration
    duration = len(raw_audio) / 16000

    # Store in database (embedding + MFCC profile)
    sample_id = database.add_voice_sample(
        actor_id=actor_id,
        embedding=embedding,
        audio_path=str(permanent_path),
        description=f"Upload: {filename}",
        duration=duration,
        mfcc_profile=mfcc_profile,
    )

    logger.info(
        "Indexed voice sample for: %s (actor_id=%d, mfcc=%s)",
        dubber_name, actor_id, "yes" if mfcc_profile is not None else "no"
    )

    return {
        "actor_id": actor_id,
        "sample_id": sample_id,
        "dubber": dubber_name,
    }
