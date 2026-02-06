"""Voice matching engine with score fusion.

Uses two complementary speaker signatures:
1. d-vector embedding (256-D, from resemblyzer) - captures deep speaker identity
2. MFCC profile (39-D, from librosa) - captures vocal tract + speaking dynamics

Final score = weighted fusion of both similarities, giving more robust
matching especially in degraded conditions (phone mic, room noise).
"""

import logging
import numpy as np
from pathlib import Path

from . import audio, database
from .config import SIMILARITY_THRESHOLD, TOP_K_RESULTS

logger = logging.getLogger(__name__)

# Score fusion weights
DVECTOR_WEIGHT = 0.7
MFCC_WEIGHT = 0.3


def match_voice(
    voice_embedding: np.ndarray,
    mfcc_profile: np.ndarray | None = None,
    top_k: int = TOP_K_RESULTS,
    threshold: float = SIMILARITY_THRESHOLD,
) -> list[dict]:
    """Match a voice embedding (+ optional MFCC) against stored profiles.

    Uses score fusion when both d-vector and MFCC are available:
      score = 0.7 * dvector_similarity + 0.3 * mfcc_similarity

    Returns a list of matches sorted by fused score (highest first).
    Always returns at least the best match.
    """
    all_embeddings = database.get_all_embeddings()

    if not all_embeddings:
        logger.warning("No voice profiles in database")
        return []

    results = []
    for entry in all_embeddings:
        # Primary score: d-vector cosine similarity
        dvector_sim = audio.compute_similarity(voice_embedding, entry["embedding"])

        # Secondary score: MFCC cosine similarity (if both sides available)
        mfcc_sim = 0.0
        has_mfcc = False
        if mfcc_profile is not None and entry["mfcc_profile"] is not None:
            mfcc_sim = audio.compute_similarity(mfcc_profile, entry["mfcc_profile"])
            has_mfcc = True

        # Score fusion
        if has_mfcc:
            fused_score = DVECTOR_WEIGHT * dvector_sim + MFCC_WEIGHT * mfcc_sim
        else:
            fused_score = dvector_sim

        results.append({
            "name": entry["name"],
            "original_actor": entry["original_actor"],
            "similarity": round(fused_score * 100, 1),
            "dvector_sim": round(dvector_sim * 100, 1),
            "mfcc_sim": round(mfcc_sim * 100, 1) if has_mfcc else None,
            "actor_id": entry["actor_id"],
            "sample_id": entry["sample_id"],
        })

    # Sort by fused similarity descending
    results.sort(key=lambda x: x["similarity"], reverse=True)

    # Deduplicate: keep best match per actor
    seen_actors = set()
    unique_results = []
    for r in results:
        if r["actor_id"] not in seen_actors:
            seen_actors.add(r["actor_id"])
            unique_results.append(r)

    # Filter by threshold but always keep at least the best match
    filtered = [r for r in unique_results if r["similarity"] >= threshold * 100]
    if not filtered and unique_results:
        filtered = [unique_results[0]]

    return filtered[:top_k]


def match_from_file(
    file_path: Path,
    top_k: int = TOP_K_RESULTS,
    threshold: float = SIMILARITY_THRESHOLD,
) -> list[dict]:
    """Match a voice from an audio file using the enhanced pipeline."""
    raw_audio = audio.load_audio(file_path)
    if raw_audio is None:
        return []

    # Preprocess
    preprocessed = audio.preprocess_audio(raw_audio)

    # Extract d-vector embedding (from preprocessed audio, skip double preprocessing)
    embedding = audio.extract_embedding(preprocessed, apply_preprocessing=False)
    if embedding is None:
        return []

    # Extract MFCC profile
    mfcc_profile = audio.extract_mfcc_profile(preprocessed)

    return match_voice(embedding, mfcc_profile=mfcc_profile,
                       top_k=top_k, threshold=threshold)


def match_from_bytes(
    audio_bytes: bytes,
    audio_format: str = "wav",
    top_k: int = TOP_K_RESULTS,
    threshold: float = SIMILARITY_THRESHOLD,
) -> list[dict]:
    """Match a voice from audio bytes."""
    raw_audio = audio.load_audio_from_bytes(audio_bytes, format=audio_format)
    if raw_audio is None:
        return []

    # Preprocess
    preprocessed = audio.preprocess_audio(raw_audio)

    # Extract d-vector embedding
    embedding = audio.extract_embedding(preprocessed, apply_preprocessing=False)
    if embedding is None:
        return []

    # Extract MFCC profile
    mfcc_profile = audio.extract_mfcc_profile(preprocessed)

    return match_voice(embedding, mfcc_profile=mfcc_profile,
                       top_k=top_k, threshold=threshold)
