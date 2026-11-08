import os
import sqlite3
from pathlib import Path

DATA_DIR = Path(os.environ.get("VIDEO_DATA_DIR", "data")).resolve()


def connect():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DATA_DIR / "video.sqlite3", timeout=30)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    return db


def initialize():
    with connect() as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS videos (
                id TEXT PRIMARY KEY, name TEXT NOT NULL, mode TEXT NOT NULL,
                status TEXT NOT NULL, progress REAL DEFAULT 0,
                duration REAL DEFAULT 0, fps REAL DEFAULT 0,
                width INTEGER DEFAULT 0, height INTEGER DEFAULT 0,
                error TEXT, fence TEXT NOT NULL, is_sample INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS frames (
                video_id TEXT NOT NULL, timestamp REAL NOT NULL, payload TEXT NOT NULL,
                PRIMARY KEY (video_id, timestamp)
            );
            CREATE TABLE IF NOT EXISTS events (
                video_id TEXT NOT NULL, timestamp REAL NOT NULL,
                kind TEXT NOT NULL, severity TEXT NOT NULL,
                PRIMARY KEY (video_id, timestamp, kind)
            );
        """)
        db.execute(
            "UPDATE videos SET status='failed', error=? WHERE status IN ('queued', 'processing')",
            ("Processamento interrompido. Envie o arquivo novamente.",),
        )