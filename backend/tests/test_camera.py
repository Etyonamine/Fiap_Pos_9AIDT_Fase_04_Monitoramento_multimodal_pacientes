import io
import json
import shutil
import subprocess
import sys
import wave
from concurrent.futures import Future
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import database
from app.routers import camera, video


class FakeSpeech:
    def __init__(self, config, recognized, partial, failed):
        self.recognized = recognized
        self.writes = []
        self.finished = False

    def start(self):
        pass

    def write(self, data):
        self.writes.append(data)
        if data and not self.finished:
            self.finished = True
            self.recognized("Socorro", 0.1, 0.2)

    def finish(self):
        pass

    def stop(self):
        pass


class FakeModel:
    task = "pose"

    def __init__(self, path):
        pass

    def predict(self, image, verbose=False):
        points = [[50, 50, .9] for _ in range(17)]
        hip_x = 95 if image[0, 0, 0] > 100 else 40
        points[11] = [hip_x, 50, .9]
        points[12] = [hip_x, 50, .9]
        return [SimpleNamespace(
            boxes=SimpleNamespace(xyxy=np.array([[30, 20, 70, 90]])),
            keypoints=SimpleNamespace(data=np.array([points])),
        )]


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATA_DIR", tmp_path)
    monkeypatch.setattr(camera, "DATA_DIR", tmp_path)
    monkeypatch.setattr(video, "DATA_DIR", tmp_path)
    model_path = tmp_path / "pose.pt"
    model_path.touch()
    monkeypatch.setattr(camera, "MODEL_PATH", model_path)
    monkeypatch.setattr(camera, "configuration", lambda **kwargs: {
        "AZURE_SPEECH_KEY": "test-key", "AZURE_SPEECH_REGION": "eastus",
    })
    monkeypatch.setattr(camera, "SpeechStream", FakeSpeech)
    monkeypatch.setattr(camera.language_executor, "submit", lambda *args: _completed_future({
        "key_phrases": ["Socorro"], "sentiment": {"label": "negative"},
    }))
    monkeypatch.setitem(sys.modules, "ultralytics", SimpleNamespace(YOLO=FakeModel))
    database.initialize()
    app = FastAPI()
    app.include_router(video.router)
    app.include_router(camera.router)
    with TestClient(app) as test_client:
        yield test_client
    camera.shutdown()


def _completed_future(value):
    future = Future()
    future.set_result(value)
    return future


def _jpeg(person_x=40):
    image = np.full((100, 100, 3), person_x, dtype=np.uint8)
    ok, encoded = cv2.imencode(".jpg", image)
    assert ok
    return encoded.tobytes()


def _wav(seconds=0.1):
    output = io.BytesIO()
    with wave.open(output, "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(16_000)
        target.writeframes(bytes(int(16_000 * seconds) * 2))
    return output.getvalue()


def _fence(client):
    response = client.put("/api/camera/fence", json={
        "enabled": True, "x": .2, "y": .2, "width": .5, "height": .5,
    })
    assert response.status_code == 200
    return response.json()["fence"]


def _start(client, record=False):
    fence = _fence(client)
    response = client.post("/api/camera/monitor", json={"fence": fence, "record": record})
    assert response.status_code == 201, response.text
    return response.json()


def _frame(client, session_id, image, timestamp):
    return client.post(
        f"/api/camera/monitor/{session_id}/frame",
        files={"file": ("frame.jpg", image, "image/jpeg")},
        data={"timestamp": str(timestamp)},
    )


def test_fence_is_manual_enabled_and_must_match_saved_value(client):
    assert client.get("/api/camera/fence").json() == {"fence": None}
    response = client.post("/api/camera/monitor", json={
        "fence": {"enabled": True, "x": .2, "y": .2, "width": .5, "height": .5},
        "record": False,
    })
    assert response.status_code == 409
    assert client.put("/api/camera/fence", json={
        "enabled": False, "x": .2, "y": .2, "width": .5, "height": .5,
    }).status_code == 422
    fence = _fence(client)
    stale = {**fence, "x": .1}
    response = client.post("/api/camera/monitor", json={"fence": stale, "record": False})
    assert response.status_code == 409


def test_azure_speech_configuration_is_checked_before_session_start(client, monkeypatch):
    def missing_config(**kwargs):
        raise camera.AzureAudioError("Configure AZURE_SPEECH_KEY.")

    monkeypatch.setattr(camera, "configuration", missing_config)
    fence = _fence(client)
    response = client.post("/api/camera/monitor", json={"fence": fence, "record": False})
    assert response.status_code == 503
    assert response.json()["detail"] == "Configure AZURE_SPEECH_KEY."
    assert camera.sessions == {}


def test_image_exit_is_detected_and_alert_history_is_acknowledgeable(client, tmp_path):
    session = _start(client)
    session_id = session["id"]
    first = _frame(client, session_id, _jpeg(40), 0)
    assert first.status_code == 200
    assert first.json()["events"] == []
    outside = _frame(client, session_id, _jpeg(220), 0.2)
    assert outside.status_code == 200
    state = outside.json()
    assert state["frame"]["fence"] == {
        "enabled": True, "x": .2, "y": .2, "width": .5, "height": .5,
    }
    assert state["events"] == [{
        "timestamp": 0.2, "kind": "Saída da cerca virtual",
        "severity": "critical", "source": "image",
    }]
    assert state["alerts"][0]["source"] == "image"
    assert state["alerts"][0]["status"] == "confirmed"
    acknowledged = client.post(
        f"/api/camera/monitor/{session_id}/acknowledge",
        json={"alert_ids": [state["alerts"][0]["id"]]},
    )
    assert acknowledged.status_code == 200
    assert acknowledged.json()[0]["acknowledged_at"]
    later_frame = _frame(client, session_id, _jpeg(220), 0.4)
    assert later_frame.status_code == 200
    assert later_frame.json()["alerts"][0]["acknowledged_at"]
    history = client.get("/api/camera/alert-log").json()
    assert [entry["action"] for entry in history] == ["immediate_care_requested", "detected"]
    closed = client.delete(f"/api/camera/monitor/{session_id}")
    assert closed.status_code == 200
    assert closed.json()["closed"] is True
    assert closed.json()["recording_id"] is None
    assert client.get(f"/api/camera/monitor/{session_id}").json()["closed"] is True
    assert not list(tmp_path.glob(".camera-session-*"))


def test_upload_validation_and_timestamp_idempotency(client):
    session = _start(client)
    session_id = session["id"]
    assert _frame(client, session_id, b"not-jpeg", 0).status_code == 415
    assert _frame(client, session_id, _jpeg(), "NaN").status_code == 422
    first = _frame(client, session_id, _jpeg(), 0)
    assert first.status_code == 200
    retry = _frame(client, session_id, _jpeg(), 0)
    assert retry.status_code == 200
    assert retry.json()["frame_count"] == 1
    older = _frame(client, session_id, _jpeg(220), 0)
    assert older.status_code == 409


def test_audio_wav_streaming_is_independent_and_persisted(client):
    session = _start(client)
    session_id = session["id"]
    response = client.post(
        f"/api/camera/monitor/{session_id}/audio",
        files={"file": ("audio.wav", _wav(), "audio/wav")},
        data={"timestamp": "0"},
    )
    assert response.status_code == 200
    state = response.json()
    assert state["transcripts"][0]["text"] == "Socorro"
    assert state["transcripts"][0]["language"]["key_phrases"] == ["Socorro"]
    assert state["events"] == [{
        "timestamp": 0.1, "kind": "Fala: socorro",
        "severity": "critical", "source": "audio", "provisional": False,
    }]
    assert state["alerts"][0]["source"] == "audio"
    assert state["frame"] is None
    assert client.get(f"/api/camera/monitor/{session_id}").json()["frame"] is None
    invalid = client.post(
        f"/api/camera/monitor/{session_id}/audio",
        files={"file": ("bad.wav", b"not-wav", "audio/wav")},
        data={"timestamp": "0.1"},
    )
    assert invalid.status_code == 422


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="FFmpeg não instalado")
def test_recording_is_playable_and_added_to_bed_library(client, tmp_path):
    session = _start(client, record=True)
    session_id = session["id"]
    assert _frame(client, session_id, _jpeg(), 0).status_code == 200
    audio = client.post(
        f"/api/camera/monitor/{session_id}/audio",
        files={"file": ("audio.wav", _wav(), "audio/wav")},
        data={"timestamp": "0"},
    )
    assert audio.status_code == 200
    closed = client.delete(f"/api/camera/monitor/{session_id}")
    assert closed.status_code == 200, closed.text
    recording_id = closed.json()["recording_id"]
    assert recording_id
    media = client.get(f"/api/videos/{recording_id}/media")
    assert media.status_code == 200
    assert media.headers["content-type"] == "video/mp4"
    assert any(item["id"] == recording_id for item in client.get("/api/videos").json())
    path = tmp_path / f"{recording_id}.mp4"
    assert path.is_file() and path.stat().st_size > 0
    subprocess.run(
        ["ffmpeg", "-nostdin", "-v", "error", "-i", str(path), "-f", "null", "-"],
        check=True, capture_output=True, timeout=60,
    )
    subprocess.run(
        ["ffmpeg", "-nostdin", "-v", "error", "-i", str(path), "-map", "0:a:0", "-f", "null", "-"],
        check=True, capture_output=True, timeout=60,
    )
    with database.connect() as db:
        row = db.execute("SELECT fence,mode,status FROM videos WHERE id=?", (recording_id,)).fetchone()
    assert row["mode"] == "bed"
    assert row["status"] == "ready"
    assert json.loads(row["fence"]) == {
        "enabled": True, "x": .2, "y": .2, "width": .5, "height": .5,
    }
    assert not (tmp_path / f".camera-session-{session_id}").exists()


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="FFmpeg não instalado")
def test_recording_failure_keeps_scoped_assets_for_retry(client, monkeypatch, tmp_path):
    session = _start(client, record=True)
    session_id = session["id"]
    assert _frame(client, session_id, _jpeg(), 0).status_code == 200
    directory = tmp_path / f".camera-session-{session_id}"
    real_run = camera.subprocess.run
    calls = 0

    def fail_once(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise subprocess.CalledProcessError(1, args[0], stderr=b"test")
        return real_run(*args, **kwargs)

    monkeypatch.setattr(camera.subprocess, "run", fail_once)
    failed = client.delete(f"/api/camera/monitor/{session_id}")
    assert failed.status_code == 500
    assert directory.exists()
    assert client.get(f"/api/camera/monitor/{session_id}").json()["closed"] is False
    succeeded = client.delete(f"/api/camera/monitor/{session_id}")
    assert succeeded.status_code == 200
    assert succeeded.json()["recording_id"]
    assert not directory.exists()


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="FFmpeg não instalado")
def test_recording_without_audio_keeps_silent_playable_audio_track(client, tmp_path):
    session = _start(client, record=True)
    session_id = session["id"]
    assert _frame(client, session_id, _jpeg(), 0).status_code == 200
    closed = client.delete(f"/api/camera/monitor/{session_id}")
    assert closed.status_code == 200, closed.text
    path = tmp_path / f"{closed.json()['recording_id']}.mp4"
    subprocess.run(
        ["ffmpeg", "-nostdin", "-v", "error", "-i", str(path), "-map", "0:a:0", "-f", "null", "-"],
        check=True, capture_output=True, timeout=60,
    )
