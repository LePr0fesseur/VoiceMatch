"""Audio processing and voice embedding extraction."""

import logging
import io
import numpy as np
import soundfile as sf
from pathlib import Path
from typing import Optional

from .config import SAMPLE_RATE, MIN_AUDIO_DURATION, MAX_AUDIO_DURATION

logger = logging.getLogger(__name__)

# Lazy-loaded encoder
_encoder = None


def _get_encoder():
    """Lazy-load the resemblyzer voice encoder."""
    global _encoder
    if _encoder is None:
        from resemblyzer import VoiceEncoder
        _encoder = VoiceEncoder()
        logger.info("Voice encoder loaded successfully")
    return _encoder


def load_audio(file_path: Path) -> Optional[np.ndarray]:
    """Load an audio file and return it as a numpy array at 16kHz mono."""
    try:
        audio, sr = sf.read(str(file_path))

        # Convert stereo to mono
        if len(audio.shape) > 1:
            audio = np.mean(audio, axis=1)

        # Resample if necessary
        if sr != SAMPLE_RATE:
            import librosa
            audio = librosa.resample(audio, orig_sr=sr, target_sr=SAMPLE_RATE)

        return audio.astype(np.float32)

    except Exception as e:
        logger.error("Failed to load audio from %s: %s", file_path, e)
        return None


def load_audio_from_bytes(audio_bytes: bytes, format: str = "wav") -> Optional[np.ndarray]:
    """Load audio from bytes (e.g., from an upload)."""
    try:
        audio, sr = sf.read(io.BytesIO(audio_bytes))

        # Convert stereo to mono
        if len(audio.shape) > 1:
            audio = np.mean(audio, axis=1)

        # Resample if necessary
        if sr != SAMPLE_RATE:
            import librosa
            audio = librosa.resample(audio, orig_sr=sr, target_sr=SAMPLE_RATE)

        return audio.astype(np.float32)

    except Exception as e:
        logger.error("Failed to load audio from bytes: %s", e)
        return None


def extract_embedding(audio: np.ndarray) -> Optional[np.ndarray]:
    """Extract a voice embedding from an audio numpy array."""
    try:
        duration = len(audio) / SAMPLE_RATE

        if duration < MIN_AUDIO_DURATION:
            logger.warning(
                "Audio too short (%.1fs < %.1fs)", duration, MIN_AUDIO_DURATION
            )
            return None

        # Trim to max duration
        if duration > MAX_AUDIO_DURATION:
            audio = audio[: int(MAX_AUDIO_DURATION * SAMPLE_RATE)]

        encoder = _get_encoder()
        from resemblyzer import preprocess_wav
        processed = preprocess_wav(audio, source_sr=SAMPLE_RATE)

        if len(processed) == 0:
            logger.warning("Audio preprocessing resulted in empty signal")
            return None

        embedding = encoder.embed_utterance(processed)
        return embedding.astype(np.float32)

    except Exception as e:
        logger.error("Failed to extract embedding: %s", e)
        return None


def extract_embedding_from_file(file_path: Path) -> Optional[np.ndarray]:
    """Extract a voice embedding directly from an audio file."""
    audio = load_audio(file_path)
    if audio is None:
        return None
    return extract_embedding(audio)


def compute_similarity(embedding1: np.ndarray, embedding2: np.ndarray) -> float:
    """Compute cosine similarity between two embeddings."""
    norm1 = np.linalg.norm(embedding1)
    norm2 = np.linalg.norm(embedding2)
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return float(np.dot(embedding1, embedding2) / (norm1 * norm2))
