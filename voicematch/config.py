"""Configuration for VoiceMatch."""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
VOICES_DIR = DATA_DIR / "voices"
DB_PATH = DATA_DIR / "voicematch.db"
TEMP_DIR = DATA_DIR / "temp"

# Audio settings
SAMPLE_RATE = 16000
MIN_AUDIO_DURATION = 1.0  # seconds
MAX_AUDIO_DURATION = 30.0  # seconds

# Voice embedding settings
EMBEDDING_DIM = 256  # resemblyzer output dimension

# Matching settings
SIMILARITY_THRESHOLD = 0.75  # cosine similarity threshold for a match
TOP_K_RESULTS = 5

# YouTube search settings
YT_SEARCH_TERMS = [
    "doubleur français",
    "doubleur voix française",
    "voix française acteur",
    "doublage français",
]
YT_MAX_RESULTS = 20

# Ensure directories exist
for d in [DATA_DIR, VOICES_DIR, TEMP_DIR]:
    d.mkdir(parents=True, exist_ok=True)
