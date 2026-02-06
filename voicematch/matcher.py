"""Voice matching engine - compares voice samples against the database."""

import logging
import numpy as np
from pathlib import Path

from . import audio, database
from .config import SIMILARITY_THRESHOLD, TOP_K_RESULTS

logger = logging.getLogger(__name__)


def match_voice(
    voice_embedding: np.ndarray,
    top_k: int = TOP_K_RESULTS,
    threshold: float = SIMILARITY_THRESHOLD,
) -> list[dict]:
    """Match a voice embedding against all stored voice profiles.

    Returns a list of matches sorted by similarity score (highest first).
    """
    all_embeddings = database.get_all_embeddings()

    if not all_embeddings:
        logger.warning("No voice profiles in database")
        return []

    results = []
    for entry in all_embeddings:
        similarity = audio.compute_similarity(voice_embedding, entry["embedding"])
        if similarity >= threshold:
            results.append({
                "name": entry["name"],
                "original_actor": entry["original_actor"],
                "similarity": round(similarity * 100, 1),
                "actor_id": entry["actor_id"],
                "sample_id": entry["sample_id"],
            })

    # Sort by similarity descending
    results.sort(key=lambda x: x["similarity"], reverse=True)

    # Deduplicate: keep best match per actor
    seen_actors = set()
    unique_results = []
    for r in results:
        if r["actor_id"] not in seen_actors:
            seen_actors.add(r["actor_id"])
            unique_results.append(r)

    return unique_results[:top_k]


def match_from_file(
    file_path: Path,
    top_k: int = TOP_K_RESULTS,
    threshold: float = SIMILARITY_THRESHOLD,
) -> list[dict]:
    """Match a voice from an audio file."""
    embedding = audio.extract_embedding_from_file(file_path)
    if embedding is None:
        return []
    return match_voice(embedding, top_k=top_k, threshold=threshold)


def match_from_bytes(
    audio_bytes: bytes,
    audio_format: str = "wav",
    top_k: int = TOP_K_RESULTS,
    threshold: float = SIMILARITY_THRESHOLD,
) -> list[dict]:
    """Match a voice from audio bytes (e.g., from microphone recording)."""
    audio_data = audio.load_audio_from_bytes(audio_bytes, format=audio_format)
    if audio_data is None:
        return []
    embedding = audio.extract_embedding(audio_data)
    if embedding is None:
        return []
    return match_voice(embedding, top_k=top_k, threshold=threshold)
