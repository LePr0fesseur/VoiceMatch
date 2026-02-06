"""Audio processing and voice embedding extraction.

Enhanced pipeline based on speaker recognition research:
- Voice Activity Detection (WebRTC VAD) to strip silence/noise
- Pre-emphasis filter to boost speaker-discriminative high frequencies
- Spectral noise reduction via spectral gating
- MFCC extraction (13 + 13 delta + 13 double-delta = 39 features) with CMVN
- Data augmentation (speed/pitch variants) for robust single-sample enrollment
- Multi-segment embedding averaging for robust speaker profiles
"""

import logging
import io
import struct
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


# =====================================================================
#  AUDIO LOADING
# =====================================================================


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
    """Load audio from bytes."""
    try:
        audio, sr = sf.read(io.BytesIO(audio_bytes))

        if len(audio.shape) > 1:
            audio = np.mean(audio, axis=1)

        if sr != SAMPLE_RATE:
            import librosa
            audio = librosa.resample(audio, orig_sr=sr, target_sr=SAMPLE_RATE)

        return audio.astype(np.float32)

    except Exception as e:
        logger.error("Failed to load audio from bytes: %s", e)
        return None


# =====================================================================
#  PREPROCESSING: VAD, Pre-emphasis, Noise Reduction
# =====================================================================


def apply_pre_emphasis(audio: np.ndarray, coeff: float = 0.97) -> np.ndarray:
    """Apply pre-emphasis filter to boost high frequencies.

    High frequencies carry more speaker-discriminative information
    (formant structure, fricatives). Pre-emphasis balances the spectrum.
    Reference: standard speech processing technique.
    """
    return np.append(audio[0], audio[1:] - coeff * audio[:-1])


def apply_vad(audio: np.ndarray, sr: int = SAMPLE_RATE,
              aggressiveness: int = 2) -> np.ndarray:
    """Apply Voice Activity Detection to keep only voiced segments.

    Uses WebRTC VAD which classifies 10/20/30ms frames as speech or not.
    This removes silence, noise, and non-speech segments that would
    degrade embedding quality.
    """
    try:
        import webrtcvad
    except ImportError:
        logger.warning("webrtcvad not installed, skipping VAD")
        return audio

    vad = webrtcvad.Vad(aggressiveness)
    frame_duration_ms = 30  # 30ms frames
    frame_size = int(sr * frame_duration_ms / 1000)

    # Convert to 16-bit PCM for webrtcvad
    audio_int16 = (audio * 32768).astype(np.int16)
    raw_bytes = audio_int16.tobytes()

    voiced_frames = []
    for i in range(0, len(audio_int16) - frame_size, frame_size):
        frame_bytes = audio_int16[i:i + frame_size].tobytes()
        if len(frame_bytes) == frame_size * 2:  # 2 bytes per int16 sample
            try:
                if vad.is_speech(frame_bytes, sr):
                    voiced_frames.append(audio[i:i + frame_size])
            except Exception:
                voiced_frames.append(audio[i:i + frame_size])

    if not voiced_frames:
        logger.warning("VAD found no speech, returning original audio")
        return audio

    result = np.concatenate(voiced_frames)
    logger.debug("VAD: kept %.1fs of %.1fs audio",
                 len(result) / sr, len(audio) / sr)
    return result


def reduce_noise(audio: np.ndarray, sr: int = SAMPLE_RATE) -> np.ndarray:
    """Apply spectral noise reduction via spectral gating.

    Estimates noise profile from low-energy frames, then subtracts it
    from the magnitude spectrum. This improves embedding quality when
    recordings have background noise (phone mic, room noise).
    """
    n_fft = 2048
    hop_length = 512

    # STFT
    stft = np.fft.rfft(
        np.lib.stride_tricks.sliding_window_view(
            np.pad(audio, (n_fft // 2, n_fft // 2)),
            n_fft
        )[::hop_length] * np.hanning(n_fft)
    )
    magnitude = np.abs(stft)
    phase = np.angle(stft)

    # Estimate noise floor from lowest-energy 15% of frames
    frame_energies = np.sum(magnitude ** 2, axis=1)
    noise_threshold = np.percentile(frame_energies, 15)
    noise_frames = magnitude[frame_energies <= noise_threshold]

    if len(noise_frames) > 0:
        noise_profile = np.mean(noise_frames, axis=0)

        # Spectral subtraction with flooring to avoid musical noise
        clean_magnitude = np.maximum(magnitude - 1.5 * noise_profile, 0.01 * magnitude)

        # Reconstruct via iSTFT (overlap-add)
        clean_stft = clean_magnitude * np.exp(1j * phase)
        frames = np.fft.irfft(clean_stft)

        # Overlap-add reconstruction
        output_length = len(audio)
        output = np.zeros(output_length + n_fft)
        for i, frame in enumerate(frames):
            start = i * hop_length
            end = start + n_fft
            if end <= len(output):
                output[start:end] += frame

        # Normalize
        output = output[n_fft // 2:n_fft // 2 + output_length]
        max_val = np.max(np.abs(output))
        if max_val > 0:
            output = output * (np.max(np.abs(audio)) / max_val)

        return output.astype(np.float32)

    return audio


def preprocess_audio(audio: np.ndarray, sr: int = SAMPLE_RATE) -> np.ndarray:
    """Full preprocessing pipeline for speaker recognition.

    1. Pre-emphasis filter (boost high frequencies)
    2. Noise reduction (spectral gating)
    3. VAD (keep only voiced segments)
    """
    audio = apply_pre_emphasis(audio)
    audio = reduce_noise(audio, sr)
    audio = apply_vad(audio, sr)
    return audio


# =====================================================================
#  MFCC FEATURE EXTRACTION (secondary speaker signature)
# =====================================================================


def extract_mfcc_profile(audio: np.ndarray, sr: int = SAMPLE_RATE) -> Optional[np.ndarray]:
    """Extract MFCC-based speaker profile (39 dimensions).

    Computes 13 MFCCs + 13 delta + 13 double-delta per frame,
    then takes the mean across all frames and applies CMVN
    (Cepstral Mean and Variance Normalization).

    MFCCs capture the spectral envelope shape (vocal tract characteristics)
    while delta/double-delta capture temporal dynamics (speaking style).
    Together they provide a complementary speaker signature to d-vectors.
    """
    try:
        import librosa

        # 13 MFCCs (standard for speaker recognition)
        mfccs = librosa.feature.mfcc(y=audio, sr=sr, n_mfcc=13, n_fft=2048,
                                      hop_length=512, n_mels=40)

        # Delta (velocity) and double-delta (acceleration) coefficients
        delta = librosa.feature.delta(mfccs, order=1)
        ddelta = librosa.feature.delta(mfccs, order=2)

        # Stack: 13 + 13 + 13 = 39 features per frame
        full_mfcc = np.vstack([mfccs, delta, ddelta])

        # CMVN: Cepstral Mean and Variance Normalization
        # Removes channel effects and session variability
        mean = np.mean(full_mfcc, axis=1, keepdims=True)
        std = np.std(full_mfcc, axis=1, keepdims=True)
        std[std < 1e-10] = 1e-10
        normalized = (full_mfcc - mean) / std

        # Mean across time → 39-D speaker profile vector
        profile = np.mean(normalized, axis=1).astype(np.float32)

        return profile

    except Exception as e:
        logger.error("Failed to extract MFCC profile: %s", e)
        return None


# =====================================================================
#  EMBEDDING EXTRACTION
# =====================================================================


def extract_embedding(audio: np.ndarray,
                      apply_preprocessing: bool = True) -> Optional[np.ndarray]:
    """Extract a voice embedding from an audio numpy array.

    When apply_preprocessing=True, applies the full pipeline
    (pre-emphasis, noise reduction, VAD) before extracting the embedding.
    """
    try:
        if apply_preprocessing:
            audio = preprocess_audio(audio)

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


# =====================================================================
#  ROBUST ENROLLMENT: multi-segment + augmentation
# =====================================================================


def extract_robust_embedding(audio: np.ndarray,
                             sr: int = SAMPLE_RATE) -> Optional[np.ndarray]:
    """Extract a robust speaker embedding using multi-segment averaging
    and data augmentation from a single audio sample.

    Strategy (based on speaker recognition literature):
    1. Preprocess the audio (pre-emphasis, noise reduction, VAD)
    2. Split into overlapping segments (3s windows, 1.5s hop)
    3. Extract embedding from each segment
    4. Generate speed-augmented variants (0.9x and 1.1x)
    5. Extract embeddings from augmented versions
    6. Average all embeddings → centroid
    7. L2-normalize the centroid

    This produces a much more robust speaker model from a single sample
    than a single embedding would.
    """
    # Step 1: Full preprocessing
    clean_audio = preprocess_audio(audio, sr)

    duration = len(clean_audio) / sr
    if duration < MIN_AUDIO_DURATION:
        logger.warning("Audio too short after preprocessing: %.1fs", duration)
        return None

    encoder = _get_encoder()
    from resemblyzer import preprocess_wav

    all_embeddings = []

    # Step 2: Multi-segment embedding extraction
    segment_length = int(3.0 * sr)  # 3 second windows
    hop = int(1.5 * sr)  # 1.5 second hop (50% overlap)

    if len(clean_audio) <= segment_length:
        # Audio shorter than 3s: use as single segment
        processed = preprocess_wav(clean_audio, source_sr=sr)
        if len(processed) > 0:
            emb = encoder.embed_utterance(processed)
            all_embeddings.append(emb)
    else:
        # Extract overlapping segments
        for start in range(0, len(clean_audio) - segment_length + 1, hop):
            segment = clean_audio[start:start + segment_length]
            processed = preprocess_wav(segment, source_sr=sr)
            if len(processed) > 0:
                emb = encoder.embed_utterance(processed)
                all_embeddings.append(emb)

    # Also extract from the full clean audio
    processed_full = preprocess_wav(clean_audio, source_sr=sr)
    if len(processed_full) > 0:
        emb_full = encoder.embed_utterance(processed_full)
        all_embeddings.append(emb_full)

    # Step 3: Data augmentation - speed variants
    for speed_factor in [0.9, 1.1]:
        augmented = _speed_augment(clean_audio, speed_factor)
        if len(augmented) / sr >= MIN_AUDIO_DURATION:
            processed = preprocess_wav(augmented, source_sr=sr)
            if len(processed) > 0:
                emb = encoder.embed_utterance(processed)
                all_embeddings.append(emb)

    if not all_embeddings:
        logger.error("No embeddings could be extracted")
        return None

    # Step 4: Compute centroid (average) and L2-normalize
    centroid = np.mean(all_embeddings, axis=0)
    norm = np.linalg.norm(centroid)
    if norm > 0:
        centroid = centroid / norm

    logger.info("Robust embedding: averaged %d sub-embeddings", len(all_embeddings))
    return centroid.astype(np.float32)


def extract_robust_embedding_from_file(file_path: Path) -> Optional[np.ndarray]:
    """Extract a robust speaker embedding from an audio file."""
    audio = load_audio(file_path)
    if audio is None:
        return None
    return extract_robust_embedding(audio)


def _speed_augment(audio: np.ndarray, speed_factor: float) -> np.ndarray:
    """Change audio speed without changing pitch perception significantly.

    Used for data augmentation during enrollment to capture speaker
    characteristics across slight speaking rate variations.
    """
    import librosa
    return librosa.effects.time_stretch(audio, rate=speed_factor)


# =====================================================================
#  SIMILARITY COMPUTATION
# =====================================================================


def compute_similarity(embedding1: np.ndarray, embedding2: np.ndarray) -> float:
    """Compute cosine similarity between two embeddings."""
    norm1 = np.linalg.norm(embedding1)
    norm2 = np.linalg.norm(embedding2)
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return float(np.dot(embedding1, embedding2) / (norm1 * norm2))
