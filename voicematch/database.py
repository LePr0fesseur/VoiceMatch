"""Database layer for storing voice profiles and admin settings."""

import sqlite3
import numpy as np
from typing import Optional

from .config import DB_PATH


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
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
            audio_path TEXT,
            description TEXT DEFAULT '',
            embedding BLOB NOT NULL,
            duration_seconds REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (actor_id) REFERENCES actors(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS admin_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_actors_name ON actors(name);
        CREATE INDEX IF NOT EXISTS idx_samples_actor ON voice_samples(actor_id);
    """)

    # Migration: add description column if upgrading from old schema
    try:
        conn.execute(
            "ALTER TABLE voice_samples ADD COLUMN description TEXT DEFAULT ''"
        )
    except sqlite3.OperationalError:
        pass  # Column already exists

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

    cursor.execute("SELECT id FROM actors WHERE name = ?", (name,))
    row = cursor.fetchone()
    if row:
        conn.close()
        return row["id"]

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
    audio_path: str = "",
    description: str = "",
    duration: float = 0.0,
) -> int:
    """Store a voice embedding for an actor."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO voice_samples
           (actor_id, audio_path, description, embedding, duration_seconds)
           VALUES (?, ?, ?, ?, ?)""",
        (actor_id, audio_path, description, embedding.tobytes(), duration),
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
        SELECT vs.id, vs.embedding,
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
        """SELECT id, audio_path, description, duration_seconds, created_at
           FROM voice_samples WHERE actor_id = ?""",
        (actor_id,),
    )
    results = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return results


def delete_actor(actor_id: int) -> bool:
    """Delete an actor and all their voice samples."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM voice_samples WHERE actor_id = ?", (actor_id,))
    cursor.execute("DELETE FROM actors WHERE id = ?", (actor_id,))
    deleted = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return deleted


def delete_sample(sample_id: int) -> bool:
    """Delete a single voice sample."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM voice_samples WHERE id = ?", (sample_id,))
    deleted = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return deleted


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


# --- Admin password management ---


def get_admin_password_hash() -> Optional[str]:
    """Get the stored admin password hash."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT value FROM admin_settings WHERE key = 'password_hash'"
    )
    row = cursor.fetchone()
    conn.close()
    return row["value"] if row else None


def set_admin_password_hash(password_hash: str):
    """Set the admin password hash."""
    conn = get_connection()
    conn.execute(
        "INSERT OR REPLACE INTO admin_settings (key, value) VALUES ('password_hash', ?)",
        (password_hash,),
    )
    conn.commit()
    conn.close()
