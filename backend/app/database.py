import os
import json
import sqlite3
from pathlib import Path

from app.services.yolo_services import DEFAULT_FENCE, FenceSubjectTracker, frame_events

DATA_DIR = Path(os.environ.get("VIDEO_DATA_DIR", "data")).resolve()
LEGACY_DEFAULT_FENCE = {"enabled": True, "x": 0.1, "y": 0.1, "width": 0.8, "height": 0.8}


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
                error TEXT, fence TEXT NOT NULL, is_sample INTEGER DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
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
        columns = {row["name"] for row in db.execute("PRAGMA table_info(videos)")}
        if "created_at" not in columns:
            db.execute("ALTER TABLE videos ADD COLUMN created_at TEXT")
            db.execute(
                "UPDATE videos SET created_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') "
                "WHERE created_at IS NULL"
            )
        legacy_fence = json.dumps(LEGACY_DEFAULT_FENCE)
        new_fence = json.dumps(DEFAULT_FENCE)
        videos = db.execute("SELECT id FROM videos WHERE mode='bed' AND fence=?", (legacy_fence,)).fetchall()
        for video in videos:
            db.execute("UPDATE videos SET fence=? WHERE id=?", (new_fence, video["id"]))
            db.execute("DELETE FROM events WHERE video_id=?", (video["id"],))

        ready_videos = db.execute("SELECT id,fence FROM videos WHERE status='ready'").fetchall()
        for video in ready_videos:
            rows = db.execute(
                "SELECT timestamp,payload FROM frames WHERE video_id=? ORDER BY timestamp",
                (video["id"],),
            ).fetchall()
            payloads = [(row, json.loads(row["payload"])) for row in rows]
            if not payloads or all(payload.get("_fence_tracking_version") == 1 for _, payload in payloads):
                continue

            tracker = FenceSubjectTracker(json.loads(video["fence"]))
            db.execute("DELETE FROM events WHERE video_id=?", (video["id"],))
            previous = set()
            for row, payload in payloads:
                payload = tracker.annotate(payload)
                db.execute(
                    "UPDATE frames SET payload=? WHERE video_id=? AND timestamp=?",
                    (json.dumps(payload), video["id"], row["timestamp"]),
                )
                current = set(frame_events(payload, json.loads(video["fence"])))
                for kind, severity in current - previous:
                    db.execute(
                        "INSERT INTO events VALUES (?, ?, ?, ?)",
                        (video["id"], row["timestamp"], kind, severity),
                    )
                previous = current
        db.execute(
            "UPDATE videos SET status='failed', error=? WHERE status IN ('queued', 'processing')",
            ("Processamento interrompido. Envie o arquivo novamente.",),
        )