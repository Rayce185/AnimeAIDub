"""SQLite database for job tracking and voice profiles."""

import aiosqlite
from pathlib import Path


SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'pending',
    target_language TEXT NOT NULL,
    source_language TEXT NOT NULL DEFAULT 'ja',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    error_message TEXT,
    duration_seconds REAL
);

CREATE TABLE IF NOT EXISTS voice_profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    series_name TEXT NOT NULL,
    speaker_id TEXT NOT NULL,
    speaker_label TEXT,
    sample_path TEXT NOT NULL,
    sample_duration REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(series_name, speaker_id)
);

CREATE TABLE IF NOT EXISTS processed_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path TEXT NOT NULL,
    target_language TEXT NOT NULL,
    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    tts_model TEXT,
    quality_rating INTEGER,
    UNIQUE(file_path, target_language)
);
"""


async def init_db(db_path: str) -> aiosqlite.Connection:
    """Initialize database and create tables."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    db = await aiosqlite.connect(str(path))
    await db.executescript(SCHEMA)
    await db.commit()
    return db
