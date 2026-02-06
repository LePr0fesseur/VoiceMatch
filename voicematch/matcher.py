"""Voice matching engine with per-segment analysis and score fusion.

Key improvements over basic matching:
1. Per-segment matching: splits movie clips into individual speech turns,
   embeds each separately, and finds the best matching segment
2. Score fusion: combines d-vector similarity (70%) with MFCC similarity (30%)
3. Always returns at least the best match even below threshold
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
    """Match a single embedding against stored profiles.

    Uses score fusion when MFCC is available.
    """
    all_embeddings = database.get_all_embeddings()

    if not all_embeddings:
        logger.warning("No voice profiles in database")
        return []

    results = []
    for entry in all_embeddings:
        dvector_sim = audio.compute_similarity(voice_embedding, entry["embedding"])

        mfcc_sim = 0.0
        has_mfcc = False
        if mfcc_profile is not None and entry["mfcc_profile"] is not None:
            mfcc_sim = audio.compute_similarity(mfcc_profile, entry["mfcc_profile"])
            has_mfcc = True

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

    results.sort(key=lambda x: x["similarity"], reverse=True)

    # Deduplicate: best match per actor
    seen = set()
    unique = []
    for r in results:
        if r["actor_id"] not in seen:
            seen.add(r["actor_id"])
            unique.append(r)

    filtered = [r for r in unique if r["similarity"] >= threshold * 100]
    if not filtered and unique:
        filtered = [unique[0]]

    return filtered[:top_k]


def match_segments(
    segment_embeddings: list[np.ndarray],
    mfcc_profiles: list[np.ndarray | None] | None = None,
    top_k: int = TOP_K_RESULTS,
    threshold: float = SIMILARITY_THRESHOLD,
) -> list[dict]:
    """Match multiple speech segments and return the best results.

    For each segment, finds the best matching actor. Then aggregates
    across segments: for each actor, keeps the highest score from any segment.
    This is crucial for movie clips where different segments may match
    differently depending on background noise in that part.
    """
    if not segment_embeddings:
        return []

    all_embeddings = database.get_all_embeddings()
    if not all_embeddings:
        return []

    # For each actor, track the best score from any segment
    actor_best: dict[int, dict] = {}

    for seg_idx, seg_emb in enumerate(segment_embeddings):
        seg_mfcc = None
        if mfcc_profiles and seg_idx < len(mfcc_profiles):
            seg_mfcc = mfcc_profiles[seg_idx]

        for entry in all_embeddings:
            dvector_sim = audio.compute_similarity(seg_emb, entry["embedding"])

            mfcc_sim = 0.0
            has_mfcc = False
            if seg_mfcc is not None and entry["mfcc_profile"] is not None:
                mfcc_sim = audio.compute_similarity(seg_mfcc, entry["mfcc_profile"])
                has_mfcc = True

            if has_mfcc:
                fused = DVECTOR_WEIGHT * dvector_sim + MFCC_WEIGHT * mfcc_sim
            else:
                fused = dvector_sim

            aid = entry["actor_id"]
            if aid not in actor_best or fused > actor_best[aid]["_raw_score"]:
                actor_best[aid] = {
                    "name": entry["name"],
                    "original_actor": entry["original_actor"],
                    "similarity": round(fused * 100, 1),
                    "dvector_sim": round(dvector_sim * 100, 1),
                    "mfcc_sim": round(mfcc_sim * 100, 1) if has_mfcc else None,
                    "actor_id": aid,
                    "sample_id": entry["sample_id"],
                    "_raw_score": fused,
                    "_segment": seg_idx,
                }

    results = sorted(actor_best.values(), key=lambda x: x["_raw_score"], reverse=True)
    # Clean internal fields
    for r in results:
        r.pop("_raw_score", None)
        r.pop("_segment", None)

    filtered = [r for r in results if r["similarity"] >= threshold * 100]
    if not filtered and results:
        filtered = [results[0]]

    logger.info("Segment matching: %d segments × %d profiles → best: %s (%.1f%%)",
                len(segment_embeddings), len(all_embeddings),
                filtered[0]["name"] if filtered else "none",
                filtered[0]["similarity"] if filtered else 0)

    return filtered[:top_k]


def match_from_file(
    file_path: Path,
    top_k: int = TOP_K_RESULTS,
    threshold: float = SIMILARITY_THRESHOLD,
) -> list[dict]:
    """Match from audio file using per-segment analysis."""
    raw_audio = audio.load_audio(file_path)
    if raw_audio is None:
        return []

    # Extract per-segment embeddings (isolates speech from music/effects)
    segment_embeddings = audio.extract_segment_embeddings(raw_audio)

    if not segment_embeddings:
        return []

    # Extract MFCC for each segment
    preprocessed = audio.preprocess_audio(raw_audio)
    mfcc_profiles = [audio.extract_mfcc_profile(preprocessed)]

    # Use segment matching for best results
    return match_segments(segment_embeddings, mfcc_profiles,
                          top_k=top_k, threshold=threshold)


def match_from_bytes(
    audio_bytes: bytes,
    audio_format: str = "wav",
    top_k: int = TOP_K_RESULTS,
    threshold: float = SIMILARITY_THRESHOLD,
) -> list[dict]:
    """Match from audio bytes using per-segment analysis."""
    raw_audio = audio.load_audio_from_bytes(audio_bytes, format=audio_format)
    if raw_audio is None:
        return []

    # Extract per-segment embeddings
    segment_embeddings = audio.extract_segment_embeddings(raw_audio)

    if not segment_embeddings:
        return []

    # Extract MFCC per segment
    mfcc_profiles = []
    for seg_emb in segment_embeddings:
        # We don't have the raw segment audio here, use preprocessed full audio
        pass

    # Extract MFCC from full preprocessed audio as secondary signal
    preprocessed = audio.preprocess_audio(raw_audio)
    full_mfcc = audio.extract_mfcc_profile(preprocessed)
    mfcc_profiles = [full_mfcc] * len(segment_embeddings) if full_mfcc is not None else None

    return match_segments(segment_embeddings, mfcc_profiles,
                          top_k=top_k, threshold=threshold)
