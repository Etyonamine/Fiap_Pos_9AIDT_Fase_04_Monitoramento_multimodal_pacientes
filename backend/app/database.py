import os
import json
import sqlite3
from pathlib import Path

from app.services.yolo_services import (
    DEFAULT_FENCE, DEFAULT_THRESHOLDS, POSE_ANOMALIES_VERSION, FenceSubjectTracker, frame_events,
    update_threshold_anomalies,
    LyingTrunkTracker, PhysiotherapyTracker, posture_interval_at,
)

DATA_DIR = Path(os.environ.get("VIDEO_DATA_DIR", "data")).expanduser()
if not DATA_DIR.is_absolute():
    DATA_DIR = Path(__file__).resolve().parents[1] / DATA_DIR
DATA_DIR = DATA_DIR.resolve()
LEGACY_DEFAULT_FENCE = {"enabled": True, "x": 0.1, "y": 0.1, "width": 0.8, "height": 0.8}


class ClosingConnection(sqlite3.Connection):
    def __exit__(self, exc_type, exc_value, traceback):
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()


def connect():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DATA_DIR / "video.sqlite3", timeout=30, factory=ClosingConnection)
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
            CREATE TABLE IF NOT EXISTS monitor_alerts (
                id TEXT PRIMARY KEY, session_id TEXT NOT NULL, video_id TEXT NOT NULL,
                event_key TEXT NOT NULL, timestamp REAL NOT NULL, kind TEXT NOT NULL,
                source TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL, acknowledged_at TEXT, version INTEGER NOT NULL,
                UNIQUE(session_id, event_key)
            );
            CREATE INDEX IF NOT EXISTS monitor_alerts_video ON monitor_alerts(video_id, created_at);
            CREATE TABLE IF NOT EXISTS monitor_alert_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT, alert_id TEXT NOT NULL,
                session_id TEXT NOT NULL, video_id TEXT NOT NULL,
                action TEXT NOT NULL, created_at TEXT NOT NULL, payload TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS monitor_alert_log_session ON monitor_alert_log(session_id, id);
            CREATE TABLE IF NOT EXISTS webhook_outbox (
                id TEXT PRIMARY KEY, alert_id TEXT NOT NULL, alert_version INTEGER NOT NULL,
                source TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                status TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
                next_attempt REAL NOT NULL DEFAULT 0, last_error TEXT,
                http_status INTEGER, delivered_at TEXT,
                UNIQUE(alert_id, alert_version)
            );
            CREATE INDEX IF NOT EXISTS webhook_outbox_pending
                ON webhook_outbox(status, next_attempt, created_at);
            CREATE TABLE IF NOT EXISTS monitor_incidents (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT NOT NULL UNIQUE,
                session_id TEXT NOT NULL, payload TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS monitor_incidents_session ON monitor_incidents(session_id);
            CREATE TABLE IF NOT EXISTS monitor_incident_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT, incident_id TEXT NOT NULL,
                session_id TEXT NOT NULL, action TEXT NOT NULL,
                created_at TEXT NOT NULL, payload TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS monitor_incident_log_session ON monitor_incident_log(session_id, id);
            CREATE INDEX IF NOT EXISTS monitor_incident_log_incident ON monitor_incident_log(incident_id, id);
            CREATE TABLE IF NOT EXISTS camera_fences (
                id INTEGER PRIMARY KEY CHECK (id = 1), fence TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS camera_sessions (
                id TEXT PRIMARY KEY, fence TEXT NOT NULL, record INTEGER NOT NULL,
                snapshot TEXT NOT NULL, closed INTEGER NOT NULL,
                recording_id TEXT, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS audios (
                id TEXT PRIMARY KEY, name TEXT NOT NULL, status TEXT NOT NULL,
                created_at TEXT NOT NULL, duration REAL DEFAULT 0,
                error TEXT, result TEXT, acoustic TEXT
            );
            CREATE TABLE IF NOT EXISTS clinical_imports (
                id TEXT PRIMARY KEY, kind TEXT NOT NULL, name TEXT NOT NULL,
                created_at TEXT NOT NULL, result TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS clinical_imports_created ON clinical_imports(created_at);
            CREATE TABLE IF NOT EXISTS videos (
                id TEXT PRIMARY KEY, name TEXT NOT NULL, mode TEXT NOT NULL,
                status TEXT NOT NULL, progress REAL DEFAULT 0,
                duration REAL DEFAULT 0, fps REAL DEFAULT 0,
                width INTEGER DEFAULT 0, height INTEGER DEFAULT 0,
                error TEXT, fence TEXT NOT NULL, thresholds TEXT NOT NULL DEFAULT '{threshold_default}',
                posture_config TEXT,
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
        if "posture_config" not in columns:
            db.execute("ALTER TABLE videos ADD COLUMN posture_config TEXT")
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
            "SELECT id,mode,fence,thresholds,posture_config,width,height,fps FROM videos WHERE status='ready'"
        ).fetchall()
        for video in ready_videos:
            rows = db.execute(
                "SELECT timestamp,payload FROM frames WHERE video_id=? ORDER BY timestamp",
                (video["id"],),
            ).fetchall()
            payloads = [(row, json.loads(row["payload"])) for row in rows]
            if not payloads or (
                not thresholds_added
                and all(
                    payload.get("_fence_tracking_version") == 2
                    and (
                        video["mode"] != "fisio"
                        or payload.get("_pose_anomalies_version") == POSE_ANOMALIES_VERSION
                    )
                    for _, payload in payloads
                )
            ):
                continue

            tracker = FenceSubjectTracker(json.loads(video["fence"]))
            thresholds = json.loads(video["thresholds"])
            config = json.loads(video["posture_config"]) if video["posture_config"] else None
            trunk_tracker = (
                PhysiotherapyTracker(video["mode"], thresholds, video["width"], video["height"], video["fps"])
                if video["mode"] == "fisio" and config is not None
                else LyingTrunkTracker(video["mode"], thresholds, video["width"], video["height"])
            )
            db.execute("DELETE FROM events WHERE video_id=?", (video["id"],))
            previous = set()
            for row, payload in payloads:
                payload = update_threshold_anomalies(payload, video["mode"], thresholds)
                payload = tracker.annotate(payload)
                interval = posture_interval_at(config, row["timestamp"])
                payload = (trunk_tracker.annotate(payload, row["timestamp"], interval)
                           if isinstance(trunk_tracker, PhysiotherapyTracker)
                           else trunk_tracker.annotate(payload, interval))
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
        from app.services.alert_log import session_alerts
        from app.services.incidents import sync_incidents

        for row in db.execute(
            "SELECT id,snapshot FROM monitor_sessions WHERE id NOT IN "
            "(SELECT session_id FROM monitor_incidents)"
        ).fetchall():
            sync_incidents(
                db, row["id"], session_alerts(db, row["id"]),
                json.loads(row["snapshot"]).get("transcripts", []),
            )