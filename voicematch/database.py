"""Database layer for storing voice profiles."""

import json
import sqlite3
import numpy as np
from pathlib import Path
from typing import Optional

from .config import DB_PATH


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    """Create tables if they don't exist."""
    conn = get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS actors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            original_actor TEXT,
            language TEXT DEFAULT 'fr',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS voice_samples (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            actor_id INTEGER NOT NULL,
            youtube_url TEXT,
            youtube_title TEXT,
            audio_path TEXT,
            embedding BLOB NOT NULL,
            duration_seconds REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (actor_id) REFERENCES actors(id)
        );

        CREATE INDEX IF NOT EXISTS idx_actors_name ON actors(name);
        CREATE INDEX IF NOT EXISTS idx_actors_original ON actors(original_actor);
        CREATE INDEX IF NOT EXISTS idx_samples_actor ON voice_samples(actor_id);
    """)
    conn.commit()
    conn.close()


def find_or_create_actor(
    name: str,
    original_actor: Optional[str] = None,
    language: str = "fr",
) -> int:
    """Find an existing actor or create a new one. Return the actor ID."""
    conn = get_connection()
    cursor = conn.cursor()

    # Try to find existing
    if original_actor:
        cursor.execute(
            "SELECT id FROM actors WHERE name = ? AND original_actor = ?",
            (name, original_actor),
        )
    else:
        cursor.execute("SELECT id FROM actors WHERE name = ?", (name,))

    row = cursor.fetchone()
    if row:
        conn.close()
        return row["id"]

    # Create new
    cursor.execute(
        "INSERT INTO actors (name, original_actor, language) VALUES (?, ?, ?)",
        (name, original_actor, language),
    )
    conn.commit()
    actor_id = cursor.lastrowid
    conn.close()
    return actor_id


def add_voice_sample(
    actor_id: int,
    embedding: np.ndarray,
    youtube_url: str = "",
    youtube_title: str = "",
    audio_path: str = "",
    duration: float = 0.0,
) -> int:
    """Store a voice embedding for an actor."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO voice_samples
           (actor_id, youtube_url, youtube_title, audio_path, embedding, duration_seconds)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (
            actor_id,
            youtube_url,
            youtube_title,
            audio_path,
            embedding.tobytes(),
            duration,
        ),
    )
    conn.commit()
    sample_id = cursor.lastrowid
    conn.close()
    return sample_id


def get_all_embeddings() -> list[dict]:
    """Retrieve all voice embeddings with actor info for matching."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT vs.id, vs.embedding, vs.youtube_url, vs.youtube_title,
               a.id as actor_id, a.name, a.original_actor, a.language
        FROM voice_samples vs
        JOIN actors a ON vs.actor_id = a.id
    """)
    results = []
    for row in cursor.fetchall():
        emb = np.frombuffer(row["embedding"], dtype=np.float32)
        results.append({
            "sample_id": row["id"],
            "actor_id": row["actor_id"],
            "name": row["name"],
            "original_actor": row["original_actor"],
            "language": row["language"],
            "youtube_url": row["youtube_url"],
            "youtube_title": row["youtube_title"],
            "embedding": emb,
        })
    conn.close()
    return results


def get_all_actors() -> list[dict]:
    """Get all actors with their sample count."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT a.id, a.name, a.original_actor, a.language,
               COUNT(vs.id) as sample_count
        FROM actors a
        LEFT JOIN voice_samples vs ON a.id = vs.actor_id
        GROUP BY a.id
        ORDER BY a.name
    """)
    results = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return results


def get_actor_samples(actor_id: int) -> list[dict]:
    """Get all voice samples for an actor."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """SELECT id, youtube_url, youtube_title, duration_seconds, created_at
           FROM voice_samples WHERE actor_id = ?""",
        (actor_id,),
    )
    results = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return results


def get_db_stats() -> dict:
    """Get database statistics."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as count FROM actors")
    actor_count = cursor.fetchone()["count"]
    cursor.execute("SELECT COUNT(*) as count FROM voice_samples")
    sample_count = cursor.fetchone()["count"]
    conn.close()
    return {"actors": actor_count, "voice_samples": sample_count}
