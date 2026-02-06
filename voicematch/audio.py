"""Audio processing and voice embedding extraction.

Enhanced pipeline using ECAPA-TDNN (SpeechBrain) for state-of-the-art
speaker embeddings, with fallback to resemblyzer if unavailable.

Key techniques:
- ECAPA-TDNN: EER 0.80% on VoxCeleb1 (vs ~5% for resemblyzer GE2E)
- Voice Activity Detection (WebRTC VAD) to isolate speech segments
- Pre-emphasis filter for speaker-discriminative high frequencies
- Spectral noise reduction via spectral gating
- MFCC extraction (39-D) with CMVN for score fusion
- Data augmentation + multi-segment averaging for robust enrollment
- Per-segment embedding for matching (crucial for movie clips)
"""

import logging
import io
import numpy as np
import soundfile as sf
from pathlib import Path
from typing import Optional

from .config import SAMPLE_RATE, MIN_AUDIO_DURATION, MAX_AUDIO_DURATION

logger = logging.getLogger(__name__)

# =====================================================================
#  ENCODER BACKEND: ECAPA-TDNN (primary) or resemblyzer (fallback)
# =====================================================================

_encoder = None
_encoder_type = None  # "ecapa" or "resemblyzer"


def _get_encoder():
    """Load the best available speaker encoder.

    Priority: ECAPA-TDNN (speechbrain) > resemblyzer (GE2E)
    """
    global _encoder, _encoder_type

    if _encoder is not None:
        return _encoder, _encoder_type

    # Try ECAPA-TDNN first (much more accurate)
    try:
        import torchaudio
        # Compatibility patch for torchaudio >= 2.10
        if not hasattr(torchaudio, 'list_audio_backends'):
            torchaudio.list_audio_backends = lambda: ['soundfile']

        from speechbrain.inference.speaker import EncoderClassifier
        _encoder = EncoderClassifier.from_hparams(
            source="speechbrain/spkrec-ecapa-voxceleb",
            savedir="data/models/ecapa",
        )
        _encoder_type = "ecapa"
        logger.info("ECAPA-TDNN speaker encoder loaded (state-of-the-art)")
        return _encoder, _encoder_type

    except Exception as e:
        logger.warning("ECAPA-TDNN unavailable (%s), falling back to resemblyzer", e)

    # Fallback to resemblyzer
    try:
        from resemblyzer import VoiceEncoder
        _encoder = VoiceEncoder()
        _encoder_type = "resemblyzer"
        logger.info("Resemblyzer voice encoder loaded (fallback)")
        return _encoder, _encoder_type

    except Exception as e:
        logger.error("No speaker encoder available: %s", e)
        raise RuntimeError("Install speechbrain or resemblyzer for speaker recognition")


def _encode_audio(audio: np.ndarray) -> Optional[np.ndarray]:
    """Extract speaker embedding using the available encoder."""
    encoder, etype = _get_encoder()

    try:
        if etype == "ecapa":
            import torch
            waveform = torch.tensor(audio, dtype=torch.float32).unsqueeze(0)
            embedding = encoder.encode_batch(waveform)
            return embedding.squeeze().cpu().numpy().astype(np.float32)

        else:  # resemblyzer
            from resemblyzer import preprocess_wav
            processed = preprocess_wav(audio, source_sr=SAMPLE_RATE)
            if len(processed) == 0:
                return None
            embedding = encoder.embed_utterance(processed)
            return embedding.astype(np.float32)

    except Exception as e:
        logger.error("Embedding extraction failed: %s", e)
        return None


# =====================================================================
#  AUDIO LOADING
# =====================================================================


def load_audio(file_path: Path) -> Optional[np.ndarray]:
    """Load an audio file as 16kHz mono float32 numpy array."""
    try:
        audio, sr = sf.read(str(file_path))
        if len(audio.shape) > 1:
            audio = np.mean(audio, axis=1)
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
    """Pre-emphasis filter: boost high frequencies (formants, fricatives)."""
    if audio is None or len(audio) < 2:
        return audio if audio is not None else np.array([], dtype=np.float32)
    return np.append(audio[0], audio[1:] - coeff * audio[:-1])


def apply_vad(audio: np.ndarray, sr: int = SAMPLE_RATE,
              aggressiveness: int = 2) -> np.ndarray:
    """WebRTC VAD: keep only voiced segments, strip silence/noise."""
    try:
        import webrtcvad
    except ImportError:
        return audio

    vad = webrtcvad.Vad(aggressiveness)
    frame_duration_ms = 30
    frame_size = int(sr * frame_duration_ms / 1000)

    audio_int16 = (audio * 32768).astype(np.int16)

    voiced_frames = []
    for i in range(0, len(audio_int16) - frame_size, frame_size):
        frame_bytes = audio_int16[i:i + frame_size].tobytes()
        if len(frame_bytes) == frame_size * 2:
            try:
                if vad.is_speech(frame_bytes, sr):
                    voiced_frames.append(audio[i:i + frame_size])
            except Exception:
                voiced_frames.append(audio[i:i + frame_size])

    if not voiced_frames:
        return audio

    return np.concatenate(voiced_frames)


def apply_vad_segments(audio: np.ndarray, sr: int = SAMPLE_RATE,
                       aggressiveness: int = 2,
                       min_segment_sec: float = 1.5) -> list[np.ndarray]:
    """VAD that returns individual speech segments instead of concatenating.

    Crucial for movie clips: each speech segment may be a different speaker.
    Returns list of numpy arrays, each being a continuous speech segment.
    """
    try:
        import webrtcvad
    except ImportError:
        return [audio]

    vad = webrtcvad.Vad(aggressiveness)
    frame_duration_ms = 30
    frame_size = int(sr * frame_duration_ms / 1000)
    min_frames = int(min_segment_sec * sr / frame_size)

    audio_int16 = (audio * 32768).astype(np.int16)

    # Classify each frame
    is_speech = []
    for i in range(0, len(audio_int16) - frame_size, frame_size):
        frame_bytes = audio_int16[i:i + frame_size].tobytes()
        if len(frame_bytes) == frame_size * 2:
            try:
                is_speech.append(vad.is_speech(frame_bytes, sr))
            except Exception:
                is_speech.append(True)

    # Group consecutive speech frames into segments
    segments = []
    current_segment_start = None

    for idx, speech in enumerate(is_speech):
        if speech:
            if current_segment_start is None:
                current_segment_start = idx
        else:
            if current_segment_start is not None:
                length = idx - current_segment_start
                if length >= min_frames:
                    start_sample = current_segment_start * frame_size
                    end_sample = idx * frame_size
                    segments.append(audio[start_sample:end_sample])
                current_segment_start = None

    # Don't forget the last segment
    if current_segment_start is not None:
        length = len(is_speech) - current_segment_start
        if length >= min_frames:
            start_sample = current_segment_start * frame_size
            segments.append(audio[start_sample:])

    if not segments:
        return [audio]

    return segments


def reduce_noise(audio: np.ndarray, sr: int = SAMPLE_RATE) -> np.ndarray:
    """Spectral noise reduction via spectral gating."""
    if audio is None or len(audio) == 0:
        return audio if audio is not None else np.array([], dtype=np.float32)

    n_fft = min(2048, len(audio))
    if n_fft < 64:
        return audio
    hop_length = min(512, n_fft // 4)

    try:
        stft = np.fft.rfft(
            np.lib.stride_tricks.sliding_window_view(
                np.pad(audio, (n_fft // 2, n_fft // 2)),
                n_fft
            )[::hop_length] * np.hanning(n_fft)
        )
        magnitude = np.abs(stft)
        phase = np.angle(stft)

        frame_energies = np.sum(magnitude ** 2, axis=1)
        noise_threshold = np.percentile(frame_energies, 15)
        noise_frames = magnitude[frame_energies <= noise_threshold]

        if len(noise_frames) > 0:
            noise_profile = np.mean(noise_frames, axis=0)
            clean_magnitude = np.maximum(magnitude - 1.5 * noise_profile, 0.01 * magnitude)
            clean_stft = clean_magnitude * np.exp(1j * phase)
            frames = np.fft.irfft(clean_stft)

            output_length = len(audio)
            output = np.zeros(output_length + n_fft)
            for i, frame in enumerate(frames):
                start = i * hop_length
                end = start + n_fft
                if end <= len(output):
                    output[start:end] += frame

            output = output[n_fft // 2:n_fft // 2 + output_length]
            max_val = np.max(np.abs(output))
            if max_val > 0:
                output = output * (np.max(np.abs(audio)) / max_val)

            return output.astype(np.float32)

    except Exception as e:
        logger.warning("Noise reduction failed: %s", e)

    return audio


def preprocess_audio(audio: np.ndarray, sr: int = SAMPLE_RATE) -> np.ndarray:
    """Full preprocessing: pre-emphasis → noise reduction → VAD."""
    audio = apply_pre_emphasis(audio)
    audio = reduce_noise(audio, sr)
    audio = apply_vad(audio, sr)
    return audio


# =====================================================================
#  MFCC FEATURE EXTRACTION (secondary speaker signature)
# =====================================================================


def extract_mfcc_profile(audio: np.ndarray, sr: int = SAMPLE_RATE) -> Optional[np.ndarray]:
    """Extract 39-D MFCC speaker profile (13 MFCC + 13 delta + 13 ddelta) with CMVN."""
    try:
        if audio is None or len(audio) == 0:
            logger.warning("MFCC: empty audio")
            return None

        # Minimum 0.5 seconds of audio required
        if len(audio) / sr < 0.5:
            logger.warning("MFCC: audio too short (%.2fs < 0.5s)", len(audio) / sr)
            return None

        # Pad short audio to at least 16000 samples (1 second) to avoid
        # librosa delta width errors (needs >= 9 frames)
        if len(audio) < 16000:
            audio = np.pad(audio, (0, 16000 - len(audio)), mode='constant')

        import librosa

        # Adapt n_fft to audio length to prevent errors
        n_fft = min(2048, len(audio))
        # n_fft must be even for rfft
        if n_fft % 2 != 0:
            n_fft -= 1
        hop_length = min(512, n_fft // 4)

        mfccs = librosa.feature.mfcc(y=audio, sr=sr, n_mfcc=13, n_fft=n_fft,
                                      hop_length=hop_length, n_mels=40)

        # Delta needs at least width*2+1 frames (default width=9 → 19 frames)
        # Use smaller width if not enough frames
        n_frames = mfccs.shape[1]
        if n_frames < 3:
            logger.warning("MFCC: too few frames (%d) for delta", n_frames)
            return None

        delta_width = min(9, (n_frames - 1) // 2)
        if delta_width < 1:
            delta_width = 1

        delta = librosa.feature.delta(mfccs, order=1, width=2 * delta_width + 1)
        ddelta = librosa.feature.delta(mfccs, order=2, width=2 * delta_width + 1)
        full_mfcc = np.vstack([mfccs, delta, ddelta])

        # CMVN normalization
        mean = np.mean(full_mfcc, axis=1, keepdims=True)
        std = np.std(full_mfcc, axis=1, keepdims=True)
        std[std < 1e-10] = 1e-10
        normalized = (full_mfcc - mean) / std

        return np.mean(normalized, axis=1).astype(np.float32)

    except Exception as e:
        logger.error("MFCC extraction failed: %s", e)
        return None


# =====================================================================
#  EMBEDDING EXTRACTION
# =====================================================================


def extract_embedding(audio: np.ndarray,
                      apply_preprocessing: bool = True) -> Optional[np.ndarray]:
    """Extract a speaker embedding from audio."""
    try:
        if audio is None or len(audio) == 0:
            logger.warning("Empty audio provided for embedding extraction")
            return None

        if apply_preprocessing:
            audio = preprocess_audio(audio)

        if audio is None or len(audio) == 0:
            logger.warning("Audio empty after preprocessing")
            return None

        duration = len(audio) / SAMPLE_RATE
        if duration < MIN_AUDIO_DURATION:
            logger.warning("Audio too short: %.1fs", duration)
            return None

        if duration > MAX_AUDIO_DURATION:
            audio = audio[:int(MAX_AUDIO_DURATION * SAMPLE_RATE)]

        return _encode_audio(audio)

    except Exception as e:
        logger.error("Failed to extract embedding: %s", e)
        return None


def extract_embedding_from_file(file_path: Path) -> Optional[np.ndarray]:
    """Extract embedding from audio file."""
    audio = load_audio(file_path)
    if audio is None:
        return None
    return extract_embedding(audio)


# =====================================================================
#  ROBUST ENROLLMENT: multi-segment + augmentation
# =====================================================================


def extract_robust_embedding(audio: np.ndarray,
                             sr: int = SAMPLE_RATE) -> Optional[np.ndarray]:
    """Extract robust speaker embedding from single sample.

    1. Preprocess (pre-emphasis, noise reduction, VAD)
    2. Split into 3s overlapping segments, embed each
    3. Generate speed-augmented variants (0.9x, 1.1x), embed each
    4. Average all → L2-normalized centroid
    """
    if audio is None or len(audio) == 0:
        logger.warning("Empty audio for robust embedding")
        return None

    clean_audio = preprocess_audio(audio, sr)

    if clean_audio is None or len(clean_audio) == 0:
        logger.warning("Audio empty after preprocessing")
        return None

    duration = len(clean_audio) / sr
    if duration < MIN_AUDIO_DURATION:
        logger.warning("Audio too short after preprocessing: %.1fs", duration)
        return None

    all_embeddings = []

    # Multi-segment embedding
    segment_length = int(3.0 * sr)
    hop = int(1.5 * sr)

    if len(clean_audio) <= segment_length:
        emb = _encode_audio(clean_audio)
        if emb is not None:
            all_embeddings.append(emb)
    else:
        for start in range(0, len(clean_audio) - segment_length + 1, hop):
            segment = clean_audio[start:start + segment_length]
            emb = _encode_audio(segment)
            if emb is not None:
                all_embeddings.append(emb)

    # Full audio embedding
    emb_full = _encode_audio(clean_audio)
    if emb_full is not None:
        all_embeddings.append(emb_full)

    # Speed augmentation
    for speed_factor in [0.9, 1.1]:
        try:
            augmented = _speed_augment(clean_audio, speed_factor)
            if len(augmented) / sr >= MIN_AUDIO_DURATION:
                emb = _encode_audio(augmented)
                if emb is not None:
                    all_embeddings.append(emb)
        except Exception:
            pass

    if not all_embeddings:
        return None

    # Centroid + L2-normalize
    centroid = np.mean(all_embeddings, axis=0)
    norm = np.linalg.norm(centroid)
    if norm > 0:
        centroid = centroid / norm

    logger.info("Robust embedding: %d sub-embeddings averaged", len(all_embeddings))
    return centroid.astype(np.float32)


def extract_robust_embedding_from_file(file_path: Path) -> Optional[np.ndarray]:
    """Extract robust embedding from audio file."""
    audio = load_audio(file_path)
    if audio is None:
        return None
    return extract_robust_embedding(audio)


# =====================================================================
#  PER-SEGMENT MATCHING (crucial for movie clips)
# =====================================================================


def extract_segment_embeddings(audio: np.ndarray,
                               sr: int = SAMPLE_RATE) -> list[np.ndarray]:
    """Extract one embedding per speech segment in the audio.

    For movie clips with music/effects, this isolates individual
    speech turns and embeds each separately, dramatically improving
    matching accuracy vs embedding the entire noisy clip at once.
    """
    if audio is None or len(audio) == 0:
        logger.warning("Empty audio for segment embeddings")
        return []

    # Pre-emphasis + noise reduction first (but NOT VAD, we want segments)
    audio = apply_pre_emphasis(audio)
    audio = reduce_noise(audio, sr)

    # Get individual speech segments via VAD
    segments = apply_vad_segments(audio, sr, aggressiveness=2, min_segment_sec=1.5)

    embeddings = []
    for seg in segments:
        if len(seg) / sr >= MIN_AUDIO_DURATION:
            emb = _encode_audio(seg)
            if emb is not None:
                embeddings.append(emb)

    # If no segments found, try the full audio
    if not embeddings:
        vad_audio = apply_vad(audio, sr)
        if len(vad_audio) / sr >= MIN_AUDIO_DURATION:
            emb = _encode_audio(vad_audio)
            if emb is not None:
                embeddings.append(emb)

    return embeddings


# =====================================================================
#  HELPERS
# =====================================================================


def _speed_augment(audio: np.ndarray, speed_factor: float) -> np.ndarray:
    """Change audio speed for data augmentation."""
    import librosa
    return librosa.effects.time_stretch(audio, rate=speed_factor)


def compute_similarity(embedding1: np.ndarray, embedding2: np.ndarray) -> float:
    """Cosine similarity between two embeddings."""
    norm1 = np.linalg.norm(embedding1)
    norm2 = np.linalg.norm(embedding2)
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return float(np.dot(embedding1, embedding2) / (norm1 * norm2))
