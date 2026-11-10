import json
import sys
from concurrent.futures import Future
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import database
from app.routers import monitor, video
from app.services import live_audio
from app.services.yolo_services import DEFAULT_FENCE


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATA_DIR", tmp_path)
    monkeypatch.setattr(video, "DATA_DIR", tmp_path)
    monkeypatch.setattr(video, "check_dependencies", lambda: None)
    monkeypatch.setattr(monitor, "sessions", {})
    database.initialize()
    with database.connect() as db:
        db.execute(
            "INSERT INTO videos (id,name,mode,status,fence,fps,duration,width,height) "
            "VALUES ('bed','bed.mp4','bed','ready',?,25,10,100,100)",
            (json.dumps(DEFAULT_FENCE),),
        )
    app = FastAPI()
    app.include_router(monitor.router)
    with TestClient(app) as client:
        yield client
    for session in monitor.sessions.values():
        session.close()


@pytest.fixture
def inference(monkeypatch):
    frames = []
    model_calls = []

    class Capture:
        def __init__(self, path):
            self.index = 0

        def isOpened(self):
            return True

        def set(self, key, value):
            self.index = int(value)
            return True

        def read(self):
            frames.append(self.index)
            image = np.full((100, 100, 3), self.index, dtype=np.uint8)
            self.index += 1
            return True, image

        def release(self):
            pass

    class Model:
        task = "pose"

        def __init__(self, path):
            model_calls.append(path)

        def predict(self, image, verbose=False):
            points = [[50, 50, .9] for _ in range(17)]
            hip_x = 50 if image[0, 0, 0] < 5 else 95
            points[11] = [hip_x, 50, .9]
            points[12] = [hip_x, 50, .9]
            return [SimpleNamespace(
                boxes=SimpleNamespace(xyxy=np.array([[30, 20, 100, 90]])),
                keypoints=SimpleNamespace(data=np.array([points])),
            )]

    monkeypatch.setattr(monitor.cv2, "VideoCapture", Capture)
    monkeypatch.setitem(sys.modules, "ultralytics", SimpleNamespace(YOLO=Model))
    return frames, model_calls


def create(client, timestamp=0):
    response = client.post("/api/videos/bed/monitor", json={"timestamp": timestamp})
    assert response.status_code == 201, response.json()
    return response.json()["id"]


def advance(client, session_id, timestamp, flush=False):
    response = client.post(f"/api/videos/bed/monitor/{session_id}/advance", json={
        "timestamp": timestamp, "flush_audio": flush,
    })
    assert response.status_code == 200, response.json()
    return response.json()


def test_no_analysis_or_previous_alerts_before_playback(client, inference):
    frames, models = inference
    with database.connect() as db:
        db.execute("INSERT INTO events VALUES ('bed',0,'old alert','critical')")
    session_id = create(client)
    assert frames == []
    assert models == []
    report = client.get(f"/api/videos/bed/monitor/{session_id}/report").json()["monitor"]
    assert report["events"] == []
    assert report["frame_count"] == 0
    assert report["transcripts"] == []


def test_infers_every_reached_frame_and_never_anticipates_exit(client, inference):
    frames, models = inference
    session_id = create(client)
    first = advance(client, session_id, .12)
    assert frames == [0, 1, 2, 3]
    assert first["events"] == []
    assert first["frame"]["timestamp"] == .12
    exit_frame = advance(client, session_id, .2)
    assert frames == list(range(6))
    assert exit_frame["events"] == [{
        "timestamp": .2, "kind": "Saída da cerca virtual", "severity": "critical", "source": "image",
    }]
    advance(client, session_id, .2)
    assert frames == list(range(6))
    assert len(models) == 1
    report = client.get(f"/api/videos/bed/monitor/{session_id}/report").json()["monitor"]
    assert report["frame_count"] == 6
    assert report["events"] == exit_frame["events"]


def test_seek_creates_new_pass_and_retriggers_without_cached_detections(client, inference):
    session_id = create(client)
    advance(client, session_id, .4)
    response = client.post(f"/api/videos/bed/monitor/{session_id}/advance", json={"timestamp": 0})
    assert response.status_code == 409
    assert client.delete(f"/api/videos/bed/monitor/{session_id}").status_code == 204
    new_session = create(client)
    assert advance(client, new_session, .12)["events"] == []
    assert advance(client, new_session, .2)["events"][0]["timestamp"] == .2
    assert client.post(f"/api/videos/bed/monitor/{session_id}/advance", json={"timestamp": .4}).status_code == 404


def test_forward_seek_does_not_infer_skipped_frames(client, inference):
    frames, _ = inference
    session_id = create(client, 4)
    state = advance(client, session_id, 4.12)
    assert frames == [100, 101, 102, 103]
    assert state["frame_count"] == 4
    assert state["events"] == []  # No exit inferred without a tracked occupant inside.


def test_bounded_batches_do_not_drop_intermediate_frames(client, inference):
    frames, _ = inference
    session_id = create(client)
    first = advance(client, session_id, 2)
    assert len(frames) == 25
    assert first["analyzed_until"] == 1
    advance(client, session_id, 2)
    advance(client, session_id, 2)
    assert frames == list(range(51))


def test_audio_updates_do_not_wait_for_yolo_or_language(client, inference, monkeypatch):
    pending = Future()
    monkeypatch.setattr(live_audio.language_executor, "submit", lambda *args: pending)
    session_id = create(client)
    session = monitor.sessions[session_id]
    session.audio.sent_samples = 6400
    session.audio.recognized(0, "Socorro.", .1, .2)
    with session.lock:
        response = client.post(
            f"/api/videos/bed/monitor/{session_id}/audio",
            json={"timestamp": 0, "flush_audio": False},
        )
    assert response.status_code == 200
    state = response.json()
    assert state["events"][0]["kind"] == "Fala: socorro"
    assert state["transcripts"][0]["language"] is None
    assert state["language_pending"]
    assert inference[0] == []
    assert session.frame_count == 0
    assert not pending.done()
    report = client.get(f"/api/videos/bed/monitor/{session_id}/report").json()["monitor"]
    assert report["events"] == state["events"]
    image = advance(client, session_id, .4)
    assert {event["source"] for event in image["events"]} == {"audio", "image"}


def test_audio_failure_is_explicit_and_visual_monitoring_continues(client, inference, monkeypatch):
    session_id = create(client)
    monitor.sessions[session_id].audio.fail("Speech indisponível.")
    advance(client, session_id, .2, flush=True)
    state = advance(client, session_id, .4, flush=True)
    assert state["audio_error"] == "Speech indisponível."
    assert state["frame_count"] == 11
    assert state["events"][0]["source"] == "image"


def test_closing_session_discards_pending_audio_and_persists_report(client, inference, monkeypatch):
    future = Future()
    monkeypatch.setattr(live_audio.language_executor, "submit", lambda *args: future)
    session_id = create(client)
    session = monitor.sessions[session_id]
    session.audio.sent_samples = 3200
    session.audio.recognized(0, "Socorro.", .1, .1)
    session.audio.active = True
    advance(client, session_id, .2, flush=True)
    assert client.delete(f"/api/videos/bed/monitor/{session_id}").status_code == 204
    assert future.cancelled()
    report = client.get(f"/api/videos/bed/monitor/{session_id}/report").json()["monitor"]
    assert report["closed"]
    assert not report["audio_pending"]
    assert "descartado" in report["audio_error"]
    assert not report["language_pending"]
    assert report["transcripts"][0]["language_error"]
    assert report["frame_count"] == 6


def test_decoder_seek_failure_is_explicit_and_closes_session(client, inference, monkeypatch):
    monkeypatch.setattr(monitor.cv2.VideoCapture, "set", lambda *args: False)
    session_id = create(client, 4)
    response = client.post(
        f"/api/videos/bed/monitor/{session_id}/advance", json={"timestamp": 4.12},
    )
    assert response.status_code == 500
    assert "Falha ao analisar frames" in response.json()["detail"]
    assert inference[0] == []
    report = client.get(f"/api/videos/bed/monitor/{session_id}/report").json()["monitor"]
    assert report["closed"]
    assert report["frame_count"] == 0


@pytest.mark.parametrize("timestamp", [-1, "nan", "inf", 10, 11])
def test_invalid_start_is_rejected(client, timestamp):
    assert client.post("/api/videos/bed/monitor", json={"timestamp": timestamp}).status_code == 422


def test_wrong_video_and_out_of_bounds_are_rejected(client, inference):
    session_id = create(client)
    assert client.post(
        f"/api/videos/wrong/monitor/{session_id}/advance", json={"timestamp": 0},
    ).status_code == 404
    assert client.post(
        f"/api/videos/bed/monitor/{session_id}/advance", json={"timestamp": 11},
    ).status_code == 422
    with database.connect() as db:
        db.execute("UPDATE videos SET mode='fisio' WHERE id='bed'")
    assert client.post("/api/videos/bed/monitor", json={"timestamp": 0}).status_code == 409


@pytest.mark.parametrize("timestamp,status", [(-1, 422), (11, 422), ("nan", 422)])
def test_audio_rejects_invalid_positions(client, timestamp, status):
    session_id = create(client)
    assert client.post(
        f"/api/videos/bed/monitor/{session_id}/audio", json={"timestamp": timestamp},
    ).status_code == status


def test_audio_rejects_foreign_closed_and_backwards_sessions(client):
    session_id = create(client, 4)
    assert client.post(
        f"/api/videos/other/monitor/{session_id}/audio", json={"timestamp": 4},
    ).status_code == 404
    assert client.post(
        f"/api/videos/bed/monitor/{session_id}/audio", json={"timestamp": 3},
    ).status_code == 409
    client.delete(f"/api/videos/bed/monitor/{session_id}")
    assert client.post(
        f"/api/videos/bed/monitor/{session_id}/audio", json={"timestamp": 4},
    ).status_code == 404
