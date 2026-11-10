import json
import math
import os
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import database
from app.routers import video
from app.services.yolo_services import (
    DEFAULT_FENCE, FISIO_FENCE, FenceSubjectTracker, analyze_pose, angle, frame_events,
    update_threshold_anomalies,
)
from app.services.audio_analysis import acoustic_analysis


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATA_DIR", tmp_path)
    monkeypatch.setattr(video, "DATA_DIR", tmp_path)
    monkeypatch.setattr(video.audio, "DATA_DIR", tmp_path)
    monkeypatch.setattr(video.audio.executor, "submit", lambda *args: None)
    database.initialize()
    app = FastAPI()
    app.include_router(video.router)
    with TestClient(app) as client:
        yield client


def seed(status="ready"):
    points = [[.5, .5, .9] for _ in range(17)]
    payload = {"people": [{"box": [.2, .2, .2, .4], "keypoints": points,
                          "knee_angle": 90, "spine_angle": 10, "anomalies": []}]}
    with database.connect() as db:
        db.execute(
            "INSERT INTO videos (id,name,mode,status,fence,fps,duration,width,height) VALUES (?,?,?,?,?,25,1,100,100)",
            ("test", "bed.mp4", "bed", status, json.dumps(DEFAULT_FENCE)),
        )
        for timestamp in (0, .04, .08, .96):
            db.execute("INSERT INTO frames VALUES (?,?,?)", ("test", timestamp, json.dumps(payload)))


def test_replay_seeks_backwards_and_exact_frame(client):
    seed()
    for requested, expected in ((.081, .08), (.04, .04), (0, 0), (.039, 0), (1, .96)):
        response = client.get("/api/videos/test/frame", params={"timestamp": requested})
        assert response.status_code == 200
        assert response.json()["timestamp"] == expected
        assert len(response.json()["people"][0]["keypoints"]) == 17


def test_threshold_updates_recompute_and_persist_video_events(client):
    seed()
    with database.connect() as db:
        db.execute("UPDATE videos SET mode='fisio' WHERE id='test'")

    thresholds = {"trunk_angle": 5, "knee_angle": 100}
    response = client.put("/api/videos/test/thresholds", json=thresholds)

    assert response.status_code == 200
    assert response.json()["thresholds"] == thresholds
    events = client.get("/api/videos/test/events").json()
    assert {(event["timestamp"], event["kind"], event["severity"]) for event in events} == {
        (0, "Inclinação de tronco > 5°", "warning"),
        (0, "Ângulo interno do joelho < 100°", "warning"),
    }
    frame = client.get("/api/videos/test/frame?timestamp=0").json()
    assert {event["kind"] for event in frame["events"]} == {
        "Inclinação de tronco > 5°",
        "Ângulo interno do joelho < 100°",
    }
    report = client.get("/api/videos/test/report").json()
    assert report["thresholds"] == thresholds
    assert "nem define faixas normais" in report["disclaimer"]
    assert client.put(
        "/api/videos/test/thresholds", json={"trunk_angle": 91, "knee_angle": 60}
    ).status_code == 422


@pytest.mark.parametrize("timestamp", ["-1", "nan", "inf", "1.1"])
def test_invalid_timestamp(client, timestamp):
    seed()
    assert client.get("/api/videos/test/frame", params={"timestamp": timestamp}).status_code == 422


def test_processing_not_available_for_replay(client):
    seed("processing")
    assert client.get("/api/videos/test/frame?timestamp=0").status_code == 409
    assert client.get("/api/videos/unknown").status_code == 404


def test_video_history_includes_analysis_timestamp(client):
    seed()

    response = client.get("/api/videos")

    assert response.status_code == 200
    assert response.json()[0]["created_at"]


def test_initialize_adds_timestamp_to_existing_video_database(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATA_DIR", tmp_path)
    with database.connect() as db:
        db.execute(
            "CREATE TABLE videos (id TEXT PRIMARY KEY, name TEXT NOT NULL, mode TEXT NOT NULL, "
            "status TEXT NOT NULL, progress REAL DEFAULT 0, duration REAL DEFAULT 0, fps REAL DEFAULT 0, "
            "width INTEGER DEFAULT 0, height INTEGER DEFAULT 0, error TEXT, fence TEXT NOT NULL, "
            "is_sample INTEGER DEFAULT 0)"
        )
        db.execute(
            "INSERT INTO videos (id,name,mode,status,fence) VALUES (?, ?, ?, ?, ?)",
            ("legacy", "legacy.mp4", "fisio", "ready", json.dumps(FISIO_FENCE)),
        )
        db.execute(
            "CREATE TABLE frames (video_id TEXT NOT NULL, timestamp REAL NOT NULL, payload TEXT NOT NULL, "
            "PRIMARY KEY (video_id,timestamp))"
        )
        db.execute(
            "CREATE TABLE events (video_id TEXT NOT NULL, timestamp REAL NOT NULL, "
            "kind TEXT NOT NULL, severity TEXT NOT NULL, PRIMARY KEY (video_id,timestamp,kind))"
        )
        payload = {
            "people": [{
                "box": [.2, .2, .2, .4],
                "keypoints": [[.5, .5, .9] for _ in range(17)],
                "knee_angle": 50,
                "spine_angle": 40,
                "anomalies": [
                    {"kind": "Inclinação de tronco > 35°", "severity": "warning"},
                    {"kind": "Flexão de joelho < 60°", "severity": "warning"},
                ],
            }]
        }
        db.execute("INSERT INTO frames VALUES ('legacy',0,?)", (json.dumps(payload),))
        db.execute(
            "INSERT INTO events VALUES ('legacy',0,'Flexão de joelho < 60°','warning')"
        )

    database.initialize()

    with database.connect() as db:
        row = db.execute(
            "SELECT created_at,thresholds FROM videos WHERE id='legacy'"
        ).fetchone()
    created_at = row["created_at"]
    assert created_at.endswith("Z")
    assert json.loads(row["thresholds"]) == {"trunk_angle": 35.0, "knee_angle": 60.0}
    with database.connect() as db:
        migrated_frame = json.loads(db.execute(
            "SELECT payload FROM frames WHERE video_id='legacy'"
        ).fetchone()["payload"])
        migrated_events = db.execute(
            "SELECT kind FROM events WHERE video_id='legacy'"
        ).fetchall()
    assert {item["kind"] for item in migrated_frame["people"][0]["anomalies"]} == {
        "Inclinação de tronco > 35°",
        "Ângulo interno do joelho < 60°",
    }
    assert {event["kind"] for event in migrated_events} == {
        "Inclinação de tronco > 35°",
        "Ângulo interno do joelho < 60°",
    }


def test_fence_recomputes_events_and_report(client):
    seed()
    assert client.put("/api/videos/test/fence", json=DEFAULT_FENCE).status_code == 200
    fence = {"enabled": True, "x": 0, "y": 0, "width": .1, "height": .1}
    assert client.put("/api/videos/test/fence", json=fence).status_code == 200
    events = client.get("/api/videos/test/events").json()
    assert events == [{"timestamp": 0, "kind": "Saída da cerca virtual", "severity": "critical"}]
    assert client.get("/api/videos/test/frame?timestamp=.08").json()["events"][0]["severity"] == "critical"
    assert client.get("/api/videos/test/report").json()["events"] == events
    fence["enabled"] = False
    client.put("/api/videos/test/fence", json=fence)
    assert client.get("/api/videos/test/events").json() == []
    fence["width"] = 1.1
    assert client.put("/api/videos/test/fence", json=fence).status_code == 422
    fence.update(width=.8, x=.5)
    assert client.put("/api/videos/test/fence", json=fence).status_code == 422


def test_fence_tracks_initial_occupant_when_another_person_enters(client):
    seed()

    def person(hip_x, box_x):
        points = [[.5, .5, .9] for _ in range(17)]
        points[11] = [hip_x, .5, .9]
        points[12] = [hip_x, .5, .9]
        return {
            "box": [box_x, .2, .1, .5],
            "keypoints": points,
            "knee_angle": 90,
            "spine_angle": 10,
            "anomalies": [],
        }

    frames = [
        {"people": [person(.5, .4)]},
        {"people": [person(.35, .25), person(.8, .75)]},
        {"people": [person(.2, .1), person(.65, .6)]},
        {"people": [person(.05, 0), person(.5, .45)]},
    ]
    with database.connect() as db:
        db.execute("DELETE FROM frames WHERE video_id='test'")
        db.executemany(
            "INSERT INTO frames VALUES (?,?,?)",
            [("test", index * .04, json.dumps(payload)) for index, payload in enumerate(frames)],
        )

    response = client.put("/api/videos/test/fence", json=DEFAULT_FENCE)

    assert response.status_code == 200
    events = client.get("/api/videos/test/events").json()
    assert events == [{
        "timestamp": .12,
        "kind": "Saída da cerca virtual",
        "severity": "critical",
    }]
    assert client.get("/api/videos/test/frame?timestamp=.12").json()["events"][0]["kind"] == \
        "Saída da cerca virtual"


def test_fence_tracker_does_not_start_on_people_outside_the_area():
    points = [[.95, .5, .9] for _ in range(17)]
    person = {
        "box": [.9, .2, .1, .5],
        "keypoints": points,
        "anomalies": [],
    }
    tracker = FenceSubjectTracker(DEFAULT_FENCE)
    payload = tracker.annotate({"people": [person]})

    assert frame_events(payload, DEFAULT_FENCE) == []
    assert payload["people"][0]["fence_subject"] is False


def test_initialize_recalculates_legacy_multi_person_events(client):
    seed()
    points = [[.95, .5, .9] for _ in range(17)]
    bystander = {
        "box": [.9, .2, .1, .5],
        "keypoints": points,
        "knee_angle": 90,
        "spine_angle": 10,
        "anomalies": [],
    }
    with database.connect() as db:
        rows = db.execute("SELECT timestamp,payload FROM frames WHERE video_id='test'").fetchall()
        for row in rows:
            payload = json.loads(row["payload"])
            payload["people"].append(bystander)
            db.execute(
                "UPDATE frames SET payload=? WHERE video_id='test' AND timestamp=?",
                (json.dumps(payload), row["timestamp"]),
            )
        db.execute(
            "INSERT INTO events VALUES (?,?,?,?)",
            ("test", 0, "Saída da cerca virtual", "critical"),
        )

    database.initialize()

    assert client.get("/api/videos/test/events").json() == []
    with database.connect() as db:
        payload = json.loads(db.execute(
            "SELECT payload FROM frames WHERE video_id='test' AND timestamp=0"
        ).fetchone()["payload"])
    assert payload["people"][0]["fence_subject"] is True
    assert payload["people"][1]["fence_subject"] is False


def test_default_bed_fence_includes_bottom_and_migrates_existing_events(client):
    points = [[.5, .5, .9] for _ in range(17)]
    points[11] = [.5, .95, .9]
    points[12] = [.5, .95, .9]
    payload = {"people": [{"box": [.4, .4, .2, .5], "keypoints": points,
                          "knee_angle": 90, "spine_angle": 10, "anomalies": []}]}
    old_fence = {"enabled": True, "x": 0.1, "y": 0.1, "width": 0.8, "height": 0.8}
    with database.connect() as db:
        db.execute(
            "INSERT INTO videos (id,name,mode,status,fence,fps,duration,width,height) VALUES (?,?,?,?,?,25,1,100,100)",
            ("legacy", "bed.mp4", "bed", "ready", json.dumps(old_fence)),
        )
        db.execute("INSERT INTO frames VALUES (?,?,?)", ("legacy", 0, json.dumps(payload)))
        db.execute(
            "INSERT INTO events VALUES (?,?,?,?)",
            ("legacy", 0, "Saída da cerca virtual", "critical"),
        )

    database.initialize()

    assert client.get("/api/videos/legacy").json()["fence"] == DEFAULT_FENCE
    assert client.get("/api/videos/legacy/events").json() == []


def test_fisiotherapy_fence_includes_forward_movement_margin():
    payload = {"people": [{"keypoints": [[.5, .5, .9] for _ in range(17)], "anomalies": []}]}
    payload["people"][0]["keypoints"][11] = [.5, .97, .9]
    payload["people"][0]["keypoints"][12] = [.5, .97, .9]

    assert FISIO_FENCE["y"] + FISIO_FENCE["height"] == 1
    assert frame_events(payload, FISIO_FENCE) == []
    assert frame_events(payload, DEFAULT_FENCE) == []


def test_upload_validation_and_cleanup(client, monkeypatch):
    monkeypatch.setattr(video, "check_dependencies", lambda: None)
    assert client.post("/api/videos", files={"file": ("test.txt", b"data")},
                       data={"mode": "bed"}).status_code == 415
    assert client.post("/api/videos", files={"file": ("test.mp4", b"")},
                       data={"mode": "bed"}).status_code == 422
    monkeypatch.setattr(video, "MAX_BYTES", 3)
    assert client.post("/api/videos", files={"file": ("test.mp4", b"1234")},
                       data={"mode": "bed"}).status_code == 413
    assert list(video.DATA_DIR.glob("*.mp4")) == []
    assert client.post("/api/videos", files={"file": ("test.mp4", b"x")},
                       data={"mode": "rtsp"}).status_code == 422


def test_upload_queues_real_path(client, monkeypatch):
    queued = []
    monkeypatch.setattr(video, "check_dependencies", lambda: None)
    monkeypatch.setattr(video.executor, "submit", lambda *args: queued.append(args))
    response = client.post("/api/videos", files={"file": ("../../test.avi", b"video")},
                           data={"mode": "fisio"})
    assert response.status_code == 202
    assert response.json()["name"] == "test.avi"
    assert response.json()["status"] == "queued"
    assert queued[0][0] is video.process_video
    assert queued[0][2].parent == video.DATA_DIR
    assert queued[0][2].read_bytes() == b"video"


def test_fisiotherapy_upload_uses_forward_movement_fence(client, monkeypatch):
    queued = []
    monkeypatch.setattr(video, "check_dependencies", lambda: None)
    monkeypatch.setattr(video.executor, "submit", lambda *args: queued.append(args))
    response = client.post("/api/videos", files={"file": ("exercise.mp4", b"video")},
                           data={"mode": "fisio"})
    assert response.status_code == 202
    assert response.json()["fence"] == FISIO_FENCE


def test_missing_model_is_explicit(client, monkeypatch):
    monkeypatch.setattr(video, "MODEL_PATH", Path("/nonexistent/yolov8n-pose.pt"))
    response = client.post("/api/videos", files={"file": ("test.mp4", b"video")}, data={"mode": "bed"})
    assert response.status_code == 503
    assert "YOLO" in response.json()["detail"]


def test_geometric_angles_and_confidence():
    assert angle([1, 0], [0, 0], [0, 1]) == 90
    assert angle([0, 0], [0, 0], [0, 1]) is None
    points = [[50, 50, .1] for _ in range(17)]
    points[5] = [90, 0, .9]
    points[6] = [90, 0, .9]
    points[11] = [50, 50, .9]
    points[12] = [50, 50, .9]
    result = SimpleNamespace(
        boxes=SimpleNamespace(xyxy=np.array([[0, 0, 100, 100]])),
        keypoints=SimpleNamespace(data=np.array([points])),
    )
    person = analyze_pose(result, 100, 100, "fisio")["people"][0]
    assert person["knee_angle"] is None
    assert person["spine_angle"] > 35
    assert len(person["anomalies"]) == 1
    assert analyze_pose(result, 100, 100, "bed")["people"][0]["anomalies"] == []


def test_horizontal_trunk_does_not_trigger_fisio_alert_after_recalculation():
    points = [[50, 50, .9] for _ in range(17)]
    points[5] = [90, 40, .9]
    points[6] = [90, 42, .9]
    points[11] = [10, 60, .9]
    points[12] = [10, 62, .9]
    result = SimpleNamespace(
        boxes=SimpleNamespace(xyxy=np.array([[0, 0, 100, 100]])),
        keypoints=SimpleNamespace(data=np.array([points])),
    )

    payload = analyze_pose(result, 100, 100, "fisio")
    person = payload["people"][0]
    assert person["spine_angle"] >= 60
    assert person["anomalies"] == []

    update_threshold_anomalies(
        payload, "fisio", {"trunk_angle": 5, "knee_angle": 60}
    )
    assert person["anomalies"] == []


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="FFmpeg required")
@pytest.mark.parametrize("mode", ["bed", "fisio"])
def test_processing_pipeline_and_range_requests(client, monkeypatch, mode):
    # Model stub isolates orchestration; encoding, frame decoding and SQLite are real.
    class Model:
        task = "pose"

        def __init__(self, path):
            pass

        def predict(self, image, verbose=False):
            return [SimpleNamespace(keypoints=None)]

    monkeypatch.setitem(sys.modules, "ultralytics", SimpleNamespace(YOLO=Model))
    queued_audio = []
    monkeypatch.setattr(video.audio.executor, "submit", lambda *args: queued_audio.append(args))
    source = video.DATA_DIR / "input.avi"
    writer = cv2.VideoWriter(str(source), cv2.VideoWriter_fourcc(*"MJPG"), 25, (64, 64))
    for i in range(10):
        writer.write(np.full((64, 64, 3), i * 20, dtype=np.uint8))
    writer.release()
    with database.connect() as db:
        db.execute("INSERT INTO videos(id,name,mode,status,fence) VALUES ('pipeline','input.avi',?,'queued',?)",
                   (mode, json.dumps(DEFAULT_FENCE)))
    video.process_video("pipeline", source)
    status = client.get("/api/videos/pipeline").json()
    assert status["status"] == "ready"
    assert status["progress"] == 1
    assert status["audio"] is None
    assert queued_audio == []
    assert math.isclose(status["duration"], .4)
    assert not source.exists()
    with database.connect() as db:
        assert db.execute("SELECT count(*) FROM frames WHERE video_id='pipeline'").fetchone()[0] == (
            0 if mode == "bed" else 10
        )
    if mode == "fisio":
        assert client.get("/api/videos/pipeline/frame?timestamp=.12").json()["timestamp"] == .12
    response = client.get("/api/videos/pipeline/media", headers={"Range": "bytes=0-99"})
    assert response.status_code == 206
    assert len(response.content) == 100


def test_restart_marks_interrupted_jobs_failed(client):
    seed("processing")
    database.initialize()
    assert client.get("/api/videos/test").json()["status"] == "failed"


def test_default_paths_are_relative_to_backend_not_working_directory():
    from app.services import yolo_services

    backend = Path(__file__).resolve().parents[1]
    script = (
        "from app.services.yolo_services import MODEL_PATH; "
        "from app.database import DATA_DIR; "
        "print(MODEL_PATH); print(DATA_DIR)"
    )
    env = {**os.environ, "PYTHONPATH": str(backend)}
    env.pop("YOLO_MODEL_PATH", None)
    env.pop("VIDEO_DATA_DIR", None)
    for cwd in (backend, backend.parent):
        result = subprocess.run(
            [sys.executable, "-c", script], cwd=cwd, env=env,
            check=True, capture_output=True, text=True,
        )
        assert result.stdout.splitlines() == [
            str(backend / "models" / "yolov8n-pose.pt"), str(backend / "data"),
        ]
    assert yolo_services.BACKEND_DIR == backend


def test_full_audio_analysis_requires_playback_instead_of_upload(client, monkeypatch):
    seed()
    queued = []
    monkeypatch.setattr(video.audio.executor, "submit", lambda *args: queued.append(args))
    with database.connect() as db:
        db.execute("UPDATE videos SET mode='fisio' WHERE id='test'")
    assert client.post("/api/videos/test/audio").status_code == 409
    with database.connect() as db:
        db.execute("UPDATE videos SET mode='bed' WHERE id='test'")
    response = client.post("/api/videos/test/audio")
    assert response.status_code == 409
    assert "Reproduza" in response.json()["detail"]
    assert queued == []
    assert video.get_video("test")["audio"] is None
    assert video.get_video("test")["status"] == "ready"


def test_saved_help_requests_generate_critical_events_without_retranscription(client):
    seed()
    result = {
        "transcription": {
            "text": "Socorro. Alguém me ajuda, por favor. Eu preciso de ajuda.",
            "segments": [
                {"text": "Socorro. Alguém me ajuda, por favor. Eu preciso de ajuda.",
                 "offset": .35, "duration": .5},
            ],
        },
        "critical_terms": [], "rules_version": 1,
    }
    with database.connect() as db:
        db.execute(
            "INSERT INTO audios (id,name,status,created_at,result) VALUES ('help','help.wav','ready','now',?)",
            (json.dumps(result),),
        )
        db.execute("UPDATE videos SET audio_id='help' WHERE id='test'")
    expected = [
        {"timestamp": .35, "kind": f"Fala: {term}", "severity": "critical"}
        for term in ("socorro", "me ajuda", "preciso de ajuda")
    ]
    assert client.get("/api/videos/test/events").json() == expected
    assert client.get("/api/videos/test/report").json()["events"] == expected
    frame = client.get("/api/videos/test/frame?timestamp=.4").json()
    assert {event["kind"] for event in frame["events"]} == {event["kind"] for event in expected}


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="FFmpeg required")
def test_video_normalization_preserves_audio_delay_for_transcription(client, monkeypatch):
    model = SimpleNamespace(
        task="pose", predict=lambda image, verbose=False: [SimpleNamespace(keypoints=None)]
    )
    monkeypatch.setitem(sys.modules, "ultralytics", SimpleNamespace(YOLO=lambda path: model))
    source = video.DATA_DIR / "delayed-input.mp4"
    subprocess.run(
        ["ffmpeg", "-nostdin", "-y", "-f", "lavfi", "-i", "color=size=64x64:rate=25:duration=1",
         "-itsoffset", "0.4", "-f", "lavfi", "-i", "sine=frequency=440:duration=0.6",
         "-c:v", "libx264", "-c:a", "aac", str(source)],
        check=True, capture_output=True, timeout=30,
    )
    with database.connect() as db:
        db.execute(
            "INSERT INTO videos (id,name,mode,status,fence) VALUES ('delayed','delay.mp4','bed','queued',?)",
            (json.dumps(DEFAULT_FENCE),),
        )
    video.process_video("delayed", source)
    assert video.get_video("delayed")["status"] == "ready"
    assert video.get_video("delayed")["duration"] == 1
    with database.connect() as db:
        db.execute(
            "INSERT INTO audios (id,name,status,created_at) VALUES ('delayed-audio','delay.mp4','importing','now')"
        )
    copy = video.DATA_DIR / "delay-copy.mp4"
    shutil.copyfile(video.DATA_DIR / "delayed.mp4", copy)
    video.audio.import_audio("delayed-audio", copy)
    audio = video.audio.get_audio("delayed-audio")
    assert audio["status"] == "uploaded"
    acoustic = acoustic_analysis(video.audio.normalized_path("delayed-audio"))
    assert .95 <= acoustic["duration"] <= 1.1
    assert max(acoustic["waveform"][:3]) < .02
    assert max(acoustic["waveform"][5:]) > .02
    assert .3 <= acoustic["longest_low_energy_seconds"] <= .5
