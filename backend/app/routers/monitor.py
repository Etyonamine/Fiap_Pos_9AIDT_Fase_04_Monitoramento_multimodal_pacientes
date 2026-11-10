import json
import logging
import math
import threading
import time
import uuid

import cv2
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.database import connect
from app.routers import video
from app.services.azure_service import AzureAudioError
from app.services import alert_log
from app.services.live_audio import StreamingAudio, language_executor
from app.services.yolo_services import FenceSubjectTracker, analyze_pose, frame_events

router = APIRouter(prefix="/api/videos", tags=["live-monitor"])
logger = logging.getLogger(__name__)
sessions: dict[str, "Monitor"] = {}
registry_lock = threading.Lock()


class Position(BaseModel):
    timestamp: float = Field(ge=0, allow_inf_nan=False)


class Advance(Position):
    flush_audio: bool = False


class AcknowledgeAlerts(BaseModel):
    alert_ids: list[str] = Field(min_length=1, max_length=100)


class Monitor:
    def __init__(self, recording: dict, start: float):
        self.id = uuid.uuid4().hex
        self.video = recording
        self.lock = threading.Lock()
        self.persist_lock = threading.Lock()
        self.last_used = time.monotonic()
        self.capture = None
        self.model = None
        self.closed = False
        self.start = math.floor(start * recording["fps"]) / recording["fps"]
        self.next_index = round(self.start * recording["fps"])
        self.frame_count = 0
        self.target = self.start
        self.latest = None
        self.events: list[dict] = []
        self.alerts: list[dict] = []
        self.previous: set[tuple[str, str]] = set()
        self.tracker = FenceSubjectTracker(recording["fence"])
        self.audio = StreamingAudio(
            video.DATA_DIR / f"{recording['id']}.mp4", self.start, recording["duration"],
        )
        self.persist()

    def snapshot(self):
        sound = self.audio.snapshot()
        return {
            **sound,
            "id": self.id, "video_id": self.video["id"], "start": self.start,
            "closed": self.closed, "target": self.target,
            "analyzed_until": self.next_index / self.video["fps"],
            "frame_count": self.frame_count, "frame": self.latest,
            "events": sorted(self.events + sound["events"], key=lambda event: event["timestamp"]),
            "alerts": self.alerts,
        }

    def persist(self):
        with self.persist_lock, connect() as db:
            db.execute("BEGIN IMMEDIATE")
            state = self.snapshot()
            self.alerts = alert_log.sync_alerts(db, self.id, self.video["id"], state["events"])
            state["alerts"] = self.alerts
            db.execute(
                "INSERT INTO monitor_sessions VALUES (?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET snapshot=excluded.snapshot",
                (self.id, self.video["id"], json.dumps(state)),
            )

    def persist_audio(self, sound: dict):
        # Audio polling must not take the inference lock or overwrite newer image results.
        with self.persist_lock, connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if self.closed:
                sound = self.audio.snapshot()
            row = db.execute(
                "SELECT snapshot FROM monitor_sessions WHERE id=?", (self.id,),
            ).fetchone()
            stored = json.loads(row["snapshot"])
            image_events = [event for event in stored["events"] if event.get("source") != "audio"]
            stored.update(sound)
            stored["events"] = sorted(image_events + sound["events"], key=lambda event: event["timestamp"])
            self.alerts = alert_log.sync_alerts(db, self.id, self.video["id"], stored["events"])
            stored["alerts"] = self.alerts
            sound["alerts"] = self.alerts
            db.execute(
                "UPDATE monitor_sessions SET snapshot=? WHERE id=?", (json.dumps(stored), self.id),
            )

    def advance(self, position: Advance):
        if position.timestamp > self.video["duration"]:
            raise HTTPException(422, "Timestamp fora do vídeo.")
        if position.timestamp + 1e-6 < self.target:
            raise HTTPException(409, "Crie uma nova sessão ao retroceder o vídeo.")
        self.target = position.timestamp
        self.last_used = time.monotonic()
        fps = self.video["fps"]
        last_index = min(
            math.floor(position.timestamp * fps + 1e-6),
            round(self.video["duration"] * fps) - 1,
        )
        if self.next_index <= last_index:
            if self.capture is None:
                from ultralytics import YOLO

                self.model = YOLO(str(video.MODEL_PATH))
                if self.model.task != "pose":
                    raise ValueError("Os pesos devem ser YOLO Pose.")
                self.capture = cv2.VideoCapture(str(video.DATA_DIR / f"{self.video['id']}.mp4"))
                if not self.capture.isOpened():
                    raise ValueError("Não foi possível abrir o vídeo.")
                if not self.capture.set(cv2.CAP_PROP_POS_FRAMES, self.next_index):
                    raise ValueError("Não foi possível posicionar o decoder no início da passagem.")
            # Bound each request without skipping any intermediate frames.
            stop = min(last_index + 1, self.next_index + 25)
            while self.next_index < stop:
                ok, image = self.capture.read()
                if not ok:
                    raise ValueError("Decodificação interrompida durante o monitoramento.")
                timestamp = self.next_index / fps
                result = self.model.predict(image, verbose=False)[0]
                payload = self.tracker.annotate(analyze_pose(
                    result, self.video["width"], self.video["height"], "bed", self.video["thresholds"],
                ))
                current = set(frame_events(payload, self.video["fence"]))
                for kind, severity in sorted(current - self.previous):
                    self.events.append({
                        "timestamp": timestamp, "kind": kind, "severity": severity, "source": "image",
                    })
                self.previous = current
                self.latest = {
                    "timestamp": timestamp, "people": payload["people"],
                    "fence": self.video["fence"],
                    "events": [{"kind": kind, "severity": severity} for kind, severity in sorted(current)],
                }
                self.next_index += 1
                self.frame_count += 1
        self.persist()
        return self.snapshot()

    def close(self):
        self.closed = True
        if self.capture is not None:
            self.capture.release()
            self.capture = None
        self.model = None
        self.audio.close()
        self.persist()


@router.post("/{video_id}/monitor", status_code=201)
def create_monitor(video_id: str, position: Position):
    recording = video.require_ready(video_id)
    if recording["mode"] != "bed":
        raise HTTPException(409, "Monitoramento durante reprodução exige modo leito.")
    if position.timestamp >= recording["duration"]:
        raise HTTPException(422, "Inicie antes do fim do vídeo.")
    video.check_dependencies()
    with registry_lock:
        for session_id, monitor in list(sessions.items()):
            if time.monotonic() - monitor.last_used > 1800:
                with monitor.lock:
                    monitor.close()
                del sessions[session_id]
        if len(sessions) >= 8:
            raise HTTPException(429, "Feche uma sessão de monitoramento antes de abrir outra.")
        monitor = Monitor(recording, position.timestamp)
        sessions[monitor.id] = monitor
    return monitor.snapshot()


@router.post("/{video_id}/monitor/{session_id}/advance")
def advance_monitor(video_id: str, session_id: str, position: Advance):
    with registry_lock:
        monitor = sessions.get(session_id)
    if monitor is None or monitor.video["id"] != video_id:
        raise HTTPException(404, "Sessão não encontrada. Inicie novamente a reprodução.")
    with monitor.lock:
        if monitor.closed:
            raise HTTPException(409, "Sessão encerrada. Inicie novamente a reprodução.")
        try:
            return monitor.advance(position)
        except HTTPException:
            raise
        except Exception as error:
            logger.exception("Falha na inferência de monitoramento %s", session_id)
            monitor.close()
            raise HTTPException(500, "Falha ao analisar frames. Consulte o log e reinicie a reprodução.") from error


@router.delete("/{video_id}/monitor/{session_id}", status_code=204)
def close_monitor(video_id: str, session_id: str):
    with registry_lock:
        monitor = sessions.get(session_id)
        if monitor is None or monitor.video["id"] != video_id:
            raise HTTPException(404, "Sessão não encontrada.")
        with monitor.lock:
            monitor.close()
        del sessions[session_id]


@router.post("/{video_id}/monitor/{session_id}/audio")
def advance_audio(video_id: str, session_id: str, position: Advance):
    with registry_lock:
        monitor = sessions.get(session_id)
    if monitor is None or monitor.video["id"] != video_id:
        raise HTTPException(404, "Sessão não encontrada. Inicie novamente a reprodução.")
    if monitor.closed:
        raise HTTPException(409, "Sessão encerrada.")
    if position.timestamp > monitor.video["duration"]:
        raise HTTPException(422, "Timestamp fora do vídeo.")
    if position.timestamp + 1e-6 < monitor.audio.target:
        raise HTTPException(409, "Crie uma nova sessão ao retroceder o vídeo.")
    try:
        sound = monitor.audio.advance(position.timestamp, position.flush_audio)
    except AzureAudioError as error:
        raise HTTPException(409, str(error)) from error
    monitor.last_used = time.monotonic()
    monitor.persist_audio(sound)
    return sound


@router.get("/{video_id}/monitor/{session_id}/report")
def monitor_report(video_id: str, session_id: str):
    with connect() as db:
        row = db.execute(
            "SELECT snapshot FROM monitor_sessions WHERE id=? AND video_id=?", (session_id, video_id),
        ).fetchone()
    if row is None:
        raise HTTPException(404, "Relatório de monitoramento não encontrado.")
    return {
        "monitor": json.loads(row["snapshot"]),
        "alert_log": read_alert_log(video_id, session_id),
        "disclaimer": "Análise durante reprodução, sujeita à latência de YOLO e Azure. "
                      "Alertas simulados; sem acionamento real ou diagnóstico. "
                      "Apenas frames alcançados e trechos de áudio reproduzidos são analisados.",
    }


def read_alert_log(video_id: str, session_id: str | None = None):
    with connect() as db:
        rows = db.execute(
            "SELECT id,action,created_at,payload FROM monitor_alert_log "
            "WHERE video_id=? AND (? IS NULL OR session_id=?) ORDER BY id DESC LIMIT 200",
            (video_id, session_id, session_id),
        ).fetchall()
    return [{**dict(row), "payload": json.loads(row["payload"])} for row in rows]


@router.get("/{video_id}/alert-log")
def video_alert_log(video_id: str):
    video.get_video(video_id)
    return read_alert_log(video_id)


@router.post("/{video_id}/monitor/{session_id}/acknowledge")
def acknowledge_alerts(video_id: str, session_id: str, request: AcknowledgeAlerts):
    with registry_lock:
        monitor = sessions.get(session_id)
    if monitor is None or monitor.video["id"] != video_id:
        raise HTTPException(404, "Sessão não encontrada.")
    with monitor.persist_lock, connect() as db:
        db.execute("BEGIN IMMEDIATE")
        if monitor.closed:
            raise HTTPException(409, "Sessão encerrada.")
        try:
            monitor.alerts = alert_log.acknowledge(db, session_id, request.alert_ids)
        except ValueError as error:
            raise HTTPException(409, str(error)) from error
        row = db.execute("SELECT snapshot FROM monitor_sessions WHERE id=?", (session_id,)).fetchone()
        stored = json.loads(row["snapshot"])
        stored["alerts"] = monitor.alerts
        db.execute(
            "UPDATE monitor_sessions SET snapshot=? WHERE id=?", (json.dumps(stored), session_id),
        )
    return monitor.alerts


def shutdown():
    with registry_lock:
        for monitor in sessions.values():
            with monitor.lock:
                monitor.close()
        sessions.clear()
    language_executor.shutdown(wait=True, cancel_futures=True)
