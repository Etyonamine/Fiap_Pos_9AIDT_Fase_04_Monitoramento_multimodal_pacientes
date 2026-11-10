import os
import json
import sqlite3
from pathlib import Path

from app.services.yolo_services import (
    DEFAULT_FENCE, DEFAULT_THRESHOLDS, FenceSubjectTracker, frame_events,
    update_threshold_anomalies,
)

DATA_DIR = Path(os.environ.get("VIDEO_DATA_DIR", "data")).expanduser()
if not DATA_DIR.is_absolute():
    DATA_DIR = Path(__file__).resolve().parents[1] / DATA_DIR
DATA_DIR = DATA_DIR.resolve()
LEGACY_DEFAULT_FENCE = {"enabled": True, "x": 0.1, "y": 0.1, "width": 0.8, "height": 0.8}


def connect():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DATA_DIR / "video.sqlite3", timeout=30)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    return db


def initialize():
    with connect() as db:
        threshold_default = json.dumps(DEFAULT_THRESHOLDS, separators=(",", ":"))
        db.executescript(f"""
            CREATE TABLE IF NOT EXISTS monitor_sessions (
                id TEXT PRIMARY KEY, video_id TEXT NOT NULL, snapshot TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS audios (
                id TEXT PRIMARY KEY, name TEXT NOT NULL, status TEXT NOT NULL,
                created_at TEXT NOT NULL, duration REAL DEFAULT 0,
                error TEXT, result TEXT, acoustic TEXT
            );
            CREATE TABLE IF NOT EXISTS videos (
                id TEXT PRIMARY KEY, name TEXT NOT NULL, mode TEXT NOT NULL,
                status TEXT NOT NULL, progress REAL DEFAULT 0,
                duration REAL DEFAULT 0, fps REAL DEFAULT 0,
                width INTEGER DEFAULT 0, height INTEGER DEFAULT 0,
                error TEXT, fence TEXT NOT NULL, thresholds TEXT NOT NULL DEFAULT '{threshold_default}',
                is_sample INTEGER DEFAULT 0,
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
        if "audio_id" not in columns:
            db.execute("ALTER TABLE videos ADD COLUMN audio_id TEXT")
        thresholds_added = "thresholds" not in columns
        if "thresholds" not in columns:
            db.execute(
                f"ALTER TABLE videos ADD COLUMN thresholds TEXT NOT NULL DEFAULT '{threshold_default}'"
            )
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

        ready_videos = db.execute(
            "SELECT id,mode,fence,thresholds FROM videos WHERE status='ready'"
        ).fetchall()
        for video in ready_videos:
            rows = db.execute(
                "SELECT timestamp,payload FROM frames WHERE video_id=? ORDER BY timestamp",
                (video["id"],),
            ).fetchall()
            payloads = [(row, json.loads(row["payload"])) for row in rows]
            if not payloads or (
                not thresholds_added
                and all(payload.get("_fence_tracking_version") == 1 for _, payload in payloads)
            ):
                continue

            tracker = FenceSubjectTracker(json.loads(video["fence"]))
            thresholds = json.loads(video["thresholds"])
            db.execute("DELETE FROM events WHERE video_id=?", (video["id"],))
            previous = set()
            for row, payload in payloads:
                if thresholds_added:
                    payload = update_threshold_anomalies(payload, video["mode"], thresholds)
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
        db.execute(
            "UPDATE audios SET status='failed', error=? WHERE status IN ('importing', 'queued', 'analyzing')",
            ("Processamento interrompido. Reanalise ou importe o arquivo novamente.",),
        )