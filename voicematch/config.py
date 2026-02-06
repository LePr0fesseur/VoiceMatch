"""Configuration for VoiceMatch."""

import os
import secrets
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

# Admin settings
ADMIN_SECRET_KEY = os.environ.get(
    "VOICEMATCH_SECRET_KEY", secrets.token_hex(32)
)
ADMIN_SESSION_COOKIE = "voicematch_session"
ADMIN_SESSION_MAX_AGE = 86400  # 24 hours
ADMIN_DEFAULT_PASSWORD = "admin"

# Allowed upload extensions for admin indexing
ALLOWED_EXTENSIONS = {".mp3"}

# Ensure directories exist
for d in [DATA_DIR, VOICES_DIR, TEMP_DIR]:
    d.mkdir(parents=True, exist_ok=True)
