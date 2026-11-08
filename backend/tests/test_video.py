import json
import math
import shutil
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
from app.services.yolo_services import DEFAULT_FENCE, FISIO_FENCE, analyze_pose, angle, frame_events


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATA_DIR", tmp_path)
    monkeypatch.setattr(video, "DATA_DIR", tmp_path)
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


@pytest.mark.parametrize("timestamp", ["-1", "nan", "inf", "1.1"])
def test_invalid_timestamp(client, timestamp):
    seed()
    assert client.get("/api/videos/test/frame", params={"timestamp": timestamp}).status_code == 422


def test_processing_not_available_for_replay(client):
    seed("processing")
    assert client.get("/api/videos/test/frame?timestamp=0").status_code == 409
    assert client.get("/api/videos/unknown").status_code == 404


def test_fence_recomputes_events_and_report(client):
    seed()
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


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="FFmpeg required")
def test_processing_pipeline_and_range_requests(client, monkeypatch):
    # Model stub isolates orchestration; encoding, frame decoding and SQLite are real.
    class Model:
        task = "pose"

        def __init__(self, path):
            pass

        def predict(self, image, verbose=False):
            return [SimpleNamespace(keypoints=None)]

    monkeypatch.setitem(sys.modules, "ultralytics", SimpleNamespace(YOLO=Model))
    source = video.DATA_DIR / "input.avi"
    writer = cv2.VideoWriter(str(source), cv2.VideoWriter_fourcc(*"MJPG"), 25, (64, 64))
    for i in range(10):
        writer.write(np.full((64, 64, 3), i * 20, dtype=np.uint8))
    writer.release()
    with database.connect() as db:
        db.execute("INSERT INTO videos(id,name,mode,status,fence) VALUES ('pipeline','input.avi','bed','queued',?)",
                   (json.dumps(DEFAULT_FENCE),))
    video.process_video("pipeline", source)
    status = client.get("/api/videos/pipeline").json()
    assert status["status"] == "ready"
    assert status["progress"] == 1
    assert math.isclose(status["duration"], .4)
    assert not source.exists()
    with database.connect() as db:
        assert db.execute("SELECT count(*) FROM frames WHERE video_id='pipeline'").fetchone()[0] == 10
    assert client.get("/api/videos/pipeline/frame?timestamp=.12").json()["timestamp"] == .12
    response = client.get("/api/videos/pipeline/media", headers={"Range": "bytes=0-99"})
    assert response.status_code == 206
    assert len(response.content) == 100


def test_restart_marks_interrupted_jobs_failed(client):
    seed("processing")
    database.initialize()
    assert client.get("/api/videos/test").json()["status"] == "failed"
