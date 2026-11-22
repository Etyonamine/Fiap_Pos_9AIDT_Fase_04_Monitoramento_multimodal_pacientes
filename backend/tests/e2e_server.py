"""Dedicated local E2E server. All media and recognizer outputs are synthetic."""

import os
import socket
import sys
import tempfile
import threading
import types
from contextlib import asynccontextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

# Do not load backend/.env or pass inherited external-service configuration into the app.
for key in list(os.environ):
    if key.upper().startswith(("AZURE_", "FHIR_", "ALERT_WEBHOOK_")):
        del os.environ[key]

_socket_connect = socket.socket.connect
_socket_connect_ex = socket.socket.connect_ex


def _loopback_only(connect):
    def guarded(sock, address):
        host = address[0] if isinstance(address, tuple) else address
        if host not in ("127.0.0.1", "::1", "localhost"):
            raise OSError("E2E server blocks outbound network connections.")
        return connect(sock, address)
    return guarded


socket.socket.connect = _loopback_only(_socket_connect)
socket.socket.connect_ex = _loopback_only(_socket_connect_ex)
data_dir = Path(os.environ.get("VIDEO_DATA_DIR") or tempfile.mkdtemp(prefix="ytos-e2e-backend-"))
data_dir.mkdir(parents=True, exist_ok=True)
os.environ["VIDEO_DATA_DIR"] = str(data_dir)
os.environ["FHIR_BASE_URL"] = "http://127.0.0.1:8011/e2e-fhir"
os.environ["FHIR_BEARER_TOKEN"] = "synthetic-fhir-token"
os.environ["ALERT_WEBHOOK_ENABLED"] = "true"
os.environ["ALERT_WEBHOOK_URL"] = "http://127.0.0.1:8011/e2e-webhook"
os.environ["ALERT_WEBHOOK_BEARER_TOKEN"] = "synthetic-webhook-token"

import numpy as np
import uvicorn
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect

from app import database
from app.routers import audio, camera, clinical_data, incidents, monitor, notifications, synthetic_stream, video
from app.services import live_audio, webhook_notifications


class SyntheticYOLO:
    task = "pose"

    def __init__(self, _path):
        self.frames = 0

    def predict(self, image, verbose=False):
        height, width = image.shape[:2]
        # Move the tracked subject just beyond the fence after five frames.
        x = .5 if self.frames < 5 else .92
        self.frames += 1
        points = [[x * width, .5 * height, .9] for _ in range(17)]
        points[5] = [(x - .1) * width, .25 * height, .9]
        points[6] = [(x + .1) * width, .25 * height, .9]
        points[11] = [x * width, .5 * height, .9]
        points[12] = [x * width, .5 * height, .9]
        points[13] = [(x + .05) * width, .7 * height, .9]
        points[14] = [(x + .05) * width, .7 * height, .9]
        points[15] = [(x - .05) * width, .85 * height, .9]
        points[16] = [(x - .05) * width, .85 * height, .9]
        return [types.SimpleNamespace(
            boxes=types.SimpleNamespace(xyxy=np.array([[
                (x - .2) * width, .1 * height, (x + .2) * width, .9 * height,
            ]])),
            keypoints=types.SimpleNamespace(data=np.array([points])),
        )]


class SyntheticSpeechStream:
    def __init__(self, _config, recognized, _partial, _failed):
        self.recognized = recognized
        self.sent = False

    def start(self):
        pass

    def write(self, data):
        if data and not self.sent:
            self.sent = True
            self.recognized("Estou com falta de ar.", 0, .1)

    def finish(self):
        pass

    def stop(self):
        pass


sys.modules["ultralytics"] = types.SimpleNamespace(YOLO=SyntheticYOLO)
video.check_dependencies = lambda: None
camera.configuration = lambda *args, **kwargs: {}
camera._check_dependencies = lambda _record: None
audio.configuration = lambda *args, **kwargs: {}
clinical_data.configuration = lambda *args, **kwargs: {}
live_audio.configuration = lambda *args, **kwargs: {}
live_audio.SpeechStream = SyntheticSpeechStream
camera.SpeechStream = SyntheticSpeechStream


def language(_text, _config):
    return {
        "provider": "Synthetic E2E",
        "key_phrases": ["falta de ar"],
        "sentiment": {"label": "negative", "scores": {
            "positive": .01, "neutral": .09, "negative": .9,
        }, "aggregation": "Média ponderada do texto sintético."},
    }


audio.transcribe = lambda *_args: {
    "provider": "Synthetic E2E", "language": "pt-BR",
    "text": "Estou com falta de ar.",
    "segments": [{"text": "Estou com falta de ar.", "offset": .1,
                  "duration": 1, "confidence": .99}],
}
audio.analyze_language = language
clinical_data.analyze_language = language
live_audio.analyze_language = language


@asynccontextmanager
async def lifespan(_app):
    database.initialize()
    webhook_notifications.start_worker()
    try:
        yield
    finally:
        camera.shutdown()
        video.executor.shutdown(wait=True)
        monitor.shutdown()
        audio.executor.shutdown(wait=True)
        webhook_notifications.stop_worker()


app = FastAPI(lifespan=lifespan)
for router in (
    video.router, audio.router, monitor.router, camera.router, incidents.router,
    clinical_data.router, notifications.router, synthetic_stream.router,
):
    app.include_router(router)
server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=8011, log_level="warning"))


@app.get("/e2e-health")
def health():
    return {"status": "ok"}


@app.get("/e2e-fhir/Observation")
def synthetic_fhir_observation(request: Request, patient: str):
    if request.headers.get("authorization") != "Bearer synthetic-fhir-token" or patient != "synthetic-patient":
        raise HTTPException(403, "Consulta sintética não autorizada.")
    return {
        "resourceType": "Bundle", "type": "searchset", "entry": [{
            "resource": {
                "resourceType": "Observation", "status": "final",
                "subject": {"reference": "Patient/synthetic-patient"},
                "effectiveDateTime": "2026-11-18T10:00:00.500Z",
                "code": {"coding": [{"system": "http://loinc.org", "code": "8867-4"}]},
                "valueQuantity": {"system": "http://unitsofmeasure.org", "code": "/min", "value": 132},
            },
        }],
    }


@app.get("/e2e-fhir/MedicationRequest")
def synthetic_fhir_medication(request: Request, patient: str):
    if request.headers.get("authorization") != "Bearer synthetic-fhir-token" or patient != "synthetic-patient":
        raise HTTPException(403, "Consulta sintética não autorizada.")
    return {
        "resourceType": "Bundle", "type": "searchset", "entry": [{
            "resource": {
                "resourceType": "MedicationRequest", "status": "active",
                "subject": {"reference": "Patient/synthetic-patient"},
                "authoredOn": "2026-11-18T10:00:00Z",
                "medicationCodeableConcept": {"text": "Medicamento sintético"},
            },
        }],
    }


@app.post("/e2e-webhook", status_code=202)
async def synthetic_webhook(request: Request):
    if request.headers.get("authorization") != "Bearer synthetic-webhook-token":
        raise HTTPException(403, "Webhook sintético não autorizado.")
    payload = await request.json()
    if set(payload) != {"event_id", "category", "source", "created_at", "notice"}:
        raise HTTPException(422, "Formato do webhook sintético inválido.")
    if request.headers.get("idempotency-key") != payload["event_id"]:
        raise HTTPException(422, "Chave de idempotência inválida.")
    return {"accepted": True}


@app.post("/e2e-shutdown")
def shutdown():
    threading.Timer(0.25, setattr, args=(server, "should_exit", True)).start()
    return {"status": "stopping"}


@app.websocket("/api/ws")
async def connection(websocket: WebSocket):
    await websocket.accept()
    await websocket.send_json({"status": "connected"})
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass


if __name__ == "__main__":
    server.run()
