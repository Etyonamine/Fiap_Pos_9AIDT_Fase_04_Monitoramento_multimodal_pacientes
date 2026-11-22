import json
import sqlite3

from app import database


def test_initialize_migrates_legacy_video_and_webhook_tables(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATA_DIR", tmp_path)
    legacy_fence = json.dumps(database.LEGACY_DEFAULT_FENCE)
    with sqlite3.connect(tmp_path / "video.sqlite3") as db:
        db.execute(
            "CREATE TABLE videos ("
            "id TEXT PRIMARY KEY, name TEXT NOT NULL, mode TEXT NOT NULL, "
            "status TEXT NOT NULL, progress REAL DEFAULT 0, duration REAL DEFAULT 0, "
            "fps REAL DEFAULT 0, width INTEGER DEFAULT 0, height INTEGER DEFAULT 0, "
            "error TEXT, fence TEXT NOT NULL, is_sample INTEGER DEFAULT 0)"
        )
        db.execute(
            "INSERT INTO videos (id,name,mode,status,fence) VALUES (?,?,?,?,?)",
            ("legacy-video", "synthetic.mp4", "bed", "ready", legacy_fence),
        )
        db.execute(
            "CREATE TABLE webhook_outbox ("
            "id TEXT PRIMARY KEY, alert_id TEXT NOT NULL, alert_version INTEGER NOT NULL, "
            "source TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, "
            "status TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0, "
            "next_attempt REAL NOT NULL DEFAULT 0, last_error TEXT, http_status INTEGER, "
            "delivered_at TEXT, UNIQUE(alert_id, alert_version))"
        )

    database.initialize()

    with database.connect() as db:
        video_columns = {row["name"] for row in db.execute("PRAGMA table_info(videos)")}
        webhook_columns = {
            row["name"] for row in db.execute("PRAGMA table_info(webhook_outbox)")
        }
        video = db.execute(
            "SELECT fence,thresholds,created_at FROM videos WHERE id='legacy-video'",
        ).fetchone()
    assert {"audio_id", "thresholds", "posture_config", "created_at"} <= video_columns
    assert {"requires_confirmation", "payload"} <= webhook_columns
    assert json.loads(video["fence"]) == database.DEFAULT_FENCE
    assert json.loads(video["thresholds"])
    assert video["created_at"]
