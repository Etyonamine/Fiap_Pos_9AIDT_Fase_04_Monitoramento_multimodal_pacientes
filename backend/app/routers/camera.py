import hashlib
import io
import json
import logging
import math
import shutil
import subprocess
import threading
import uuid
import wave
from concurrent.futures import Future
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, ConfigDict, Field, model_validator
from starlette.concurrency import run_in_threadpool

from app.database import DATA_DIR, connect
from app.services import alert_log
from app.services.azure_service import AzureAudioError, configuration
from app.services.live_audio import SpeechStream, inspect_language, speech_events, language_executor
from app.services.yolo_services import (
    DEFAULT_THRESHOLDS, MODEL_PATH, FenceSubjectTracker, analyze_pose, frame_events,
)

router = APIRouter(prefix="/api/camera", tags=["camera"])
logger = logging.getLogger(__name__)
registry_lock = threading.Lock()
sessions: dict[str, "CameraSession"] = {}

MAX_FRAME_BYTES = 10 * 1024 * 1024
MAX_AUDIO_BYTES = 2 * 1024 * 1024
MAX_AUDIO_SECONDS = 30
MAX_SESSION_SECONDS = 30 * 60
MAX_FRAME_PIXELS = 16_000_000
MAX_FRAMES = MAX_SESSION_SECONDS * 6
RECORD_FPS = 5


class Fence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool
    x: float = Field(ge=0, le=1, allow_inf_nan=False)
    y: float = Field(ge=0, le=1, allow_inf_nan=False)
    width: float = Field(gt=0, le=1, allow_inf_nan=False)
    height: float = Field(gt=0, le=1, allow_inf_nan=False)

    @model_validator(mode="after")
    def valid_bounds(self):
        if not self.enabled:
            raise ValueError("A cerca precisa estar ativada.")
        if self.x + self.width > 1 or self.y + self.height > 1:
            raise ValueError("A cerca deve estar dentro do vídeo.")
        return self


class CreateCameraMonitor(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fence: Fence
    record: bool


class AcknowledgeAlerts(BaseModel):
    model_config = ConfigDict(extra="forbid")
    alert_ids: list[str] = Field(min_length=1, max_length=100)


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _timestamp(value: str) -> float:
    try:
        timestamp = float(value)
    except (TypeError, ValueError) as error:
        raise HTTPException(422, "Timestamp inválido.") from error
    if not math.isfinite(timestamp) or timestamp < 0:
        raise HTTPException(422, "Timestamp precisa ser um número finito não negativo.")
    if timestamp > MAX_SESSION_SECONDS:
        raise HTTPException(422, "O limite por sessão é de 30 minutos.")
    return timestamp


def _camera_session_row(session_id: str):
    with connect() as db:
        row = db.execute(
            "SELECT snapshot,closed FROM camera_sessions WHERE id=?", (session_id,),
        ).fetchone()
    if row is None:
        raise HTTPException(404, "Sessão de câmera não encontrada.")
    return json.loads(row["snapshot"]), bool(row["closed"])


def _require_session(session_id: str) -> "CameraSession":
    with registry_lock:
        session = sessions.get(session_id)
    if session is None:
        _camera_session_row(session_id)
        raise HTTPException(409, "A sessão não está ativa neste servidor; consulte o estado persistido.")
    return session


def _check_dependencies(record: bool):
    if not MODEL_PATH.is_file():
        raise HTTPException(
            503, f"Pesos YOLOv8 Pose não encontrados em {MODEL_PATH}. "
            "Configure YOLO_MODEL_PATH e reinicie o backend.",
        )
    if record and shutil.which("ffmpeg") is None:
        raise HTTPException(503, "Instale FFmpeg no servidor para salvar a gravação.")


def _read_frame(data: bytes):
    if not data:
        raise HTTPException(422, "Envie um frame JPEG não vazio.")
    if not data.startswith(b"\xff\xd8"):
        raise HTTPException(415, "Envie uma imagem JPEG.")
    frame = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
    if frame is None:
        raise HTTPException(422, "O JPEG não pôde ser decodificado.")
    height, width = frame.shape[:2]
    if not width or not height or width * height > MAX_FRAME_PIXELS:
        raise HTTPException(413, "A imagem excede o limite de 16 megapixels.")
    return frame


def _read_audio(data: bytes):
    if not data:
        raise HTTPException(422, "Envie um trecho WAV não vazio.")
    try:
        with wave.open(io.BytesIO(data), "rb") as source:
            if (
                source.getcomptype() != "NONE"
                or source.getnchannels() != 1
                or source.getsampwidth() != 2
                or source.getframerate() != 16_000
            ):
                raise HTTPException(415, "O áudio deve ser WAV PCM16, mono e 16 kHz.")
            frames = source.getnframes()
            duration = frames / 16_000
            if frames < 1 or duration > MAX_AUDIO_SECONDS:
                raise HTTPException(413, "Cada trecho deve ter entre 1 amostra e 30 segundos.")
            pcm = source.readframes(frames)
            if len(pcm) != frames * 2:
                raise HTTPException(422, "O trecho WAV está incompleto.")
            return pcm, duration
    except (wave.Error, EOFError) as error:
        raise HTTPException(422, "WAV inválido ou corrompido.") from error


class CameraSession:
    def __init__(self, fence: dict, record: bool, speech_config: dict):
        self.id = uuid.uuid4().hex
        self.fence = fence
        self.record = record
        self.lock = threading.RLock()
        self.closed = False
        self.closing = False
        self.created_at = _now()
        self.tracker = FenceSubjectTracker(fence)
        self.model = None
        self.frame = None
        self.frame_count = 0
        self.last_frame_timestamp: float | None = None
        self.last_frame_hash: str | None = None
        self.previous_frame_events: set[tuple[str, str]] = set()
        self.image_events: list[dict] = []
        self.audio_events: list[dict] = []
        self.provisional_events: list[dict] = []
        self.alerts: list[dict] = []
        self.audio_error: str | None = None
        self.partial_text = ""
        self.transcripts: list[dict] = []
        self.language_futures: dict[int, Future] = {}
        self.audio_origin: float | None = None
        self.audio_end = 0.0
        self.last_audio_start: float | None = None
        self.last_audio_hash: str | None = None
        self.audio_bytes_written = 0
        self.record_frame_count = 0
        self.record_width = 0
        self.record_height = 0
        self.record_input_width = 0
        self.record_input_height = 0
        self.last_recorded_timestamp = 0.0
        self.last_recorded_image = None
        self.recording_id: str | None = None
        self.speech: SpeechStream | None = None
        self.speech_finished = False
        self.record_dir: Path | None = None
        self.writer = None
        if record:
            self.record_dir = DATA_DIR / f".camera-session-{self.id}"
            self.record_dir.mkdir(parents=True, exist_ok=False)
            (self.record_dir / "audio.pcm").touch()
        try:
            self.speech = SpeechStream(
                speech_config, self._recognized, self._partial, self._speech_failed,
            )
            self.speech.start()
        except Exception:
            self._release_writer()
            if self.record_dir is not None:
                shutil.rmtree(self.record_dir, ignore_errors=True)
            raise

    @property
    def elapsed(self):
        return max(
            self.last_frame_timestamp or 0.0,
            self.audio_end,
            self.frame["timestamp"] if self.frame else 0.0,
        )

    def _events(self):
        merged: dict[tuple[str, float, str], dict] = {}
        for event in self.image_events + self.audio_events + self.provisional_events:
            key = (event.get("source", "image"), round(event["timestamp"], 6), event["kind"])
            merged[key] = event
        return sorted(merged.values(), key=lambda event: (event["timestamp"], event.get("source", "")))

    def _collect_language(self):
        changed = False
        for index, future in list(self.language_futures.items()):
            if not future.done():
                continue
            segment = self.transcripts[index]
            try:
                segment["language"] = future.result()
            except Exception as error:
                logger.warning("Falha na análise Language da câmera: %s", error)
                segment["language_error"] = (
                    str(error) if isinstance(error, AzureAudioError)
                    else "Falha na análise de linguagem. Consulte o log do servidor."
                )
            segment["language_pending"] = False
            del self.language_futures[index]
            changed = True
        return changed

    def _snapshot(self):
        self._collect_language()
        return {
            "id": self.id,
            "closed": self.closed,
            "frame": self.frame,
            "alerts": self.alerts,
            "events": self._events(),
            "frame_count": self.frame_count,
            "elapsed": self.elapsed,
            "recording_id": self.recording_id,
            "audio_error": self.audio_error,
            "partial_text": self.partial_text,
            "transcripts": self.transcripts,
        }

    def _persist(self):
        with connect() as db:
            db.execute("BEGIN IMMEDIATE")
            self.alerts = alert_log.sync_alerts(db, self.id, self.id, self._events())
            snapshot = self._snapshot()
            db.execute(
                "INSERT INTO monitor_sessions (id,video_id,snapshot) VALUES (?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET snapshot=excluded.snapshot",
                (self.id, self.id, json.dumps(snapshot, ensure_ascii=False)),
            )
            db.execute(
                "INSERT INTO camera_sessions "
                "(id,fence,record,snapshot,closed,recording_id,created_at) VALUES (?,?,?,?,?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET snapshot=excluded.snapshot,closed=excluded.closed,"
                "recording_id=excluded.recording_id",
                (self.id, json.dumps(self.fence), int(self.record), json.dumps(snapshot, ensure_ascii=False),
                 int(self.closed), self.recording_id, self.created_at),
            )

    def snapshot(self):
        with self.lock:
            if self._collect_language():
                self._persist()
            return self._snapshot()

    def _recognized(self, text: str, offset: float, duration: float):
        with self.lock:
            if self.closed:
                return
            if not all(math.isfinite(value) and value >= 0 for value in (offset, duration)):
                self.audio_error = "Azure Speech retornou tempos inválidos."
                self.partial_text = ""
                self.provisional_events = []
                self._persist()
                return
            self.partial_text = ""
            self.provisional_events = []
            if text.strip() and self.audio_origin is not None:
                start = self.audio_origin + offset
                end = start + duration
                self.transcripts.append({
                    "start": start, "end": end, "text": text,
                    "language": None, "language_pending": True, "language_error": None,
                })
                index = len(self.transcripts) - 1
                future = language_executor.submit(inspect_language, text)
                self.language_futures[index] = future
                future.add_done_callback(self._language_completed)
                known = {(event["timestamp"], event["kind"]) for event in self.audio_events}
                self.audio_events.extend(
                    event for event in speech_events(text, start, False)
                    if (event["timestamp"], event["kind"]) not in known
                )
            self._persist()

    def _language_completed(self, future: Future):
        with self.lock:
            if self._collect_language():
                self._persist()

    def _partial(self, text: str, offset: float = 0.0, duration: float = 0.0):
        with self.lock:
            if self.closed:
                return
            self.partial_text = text
            if self.audio_origin is not None and math.isfinite(offset) and offset >= 0:
                self.provisional_events = speech_events(text, self.audio_origin + offset, True)
            self._persist()

    def _speech_failed(self, message: str):
        with self.lock:
            if self.closed:
                return
            self.audio_error = message
            self.partial_text = ""
            self.provisional_events = []
            self._persist()

    def _ensure_model(self):
        if self.model is not None:
            return
        try:
            from ultralytics import YOLO

            model = YOLO(str(MODEL_PATH))
            if getattr(model, "task", None) != "pose":
                raise ValueError("Os pesos configurados devem ser de um modelo YOLO Pose.")
            self.model = model
        except Exception as error:
            logger.exception("Falha ao carregar YOLO para a câmera")
            raise HTTPException(
                503, "Não foi possível carregar o modelo YOLO Pose. Verifique pesos e dependências.",
            ) from error

    def _write_video_frame(self, image, timestamp: float):
        if not self.record:
            return
        height, width = image.shape[:2]
        if self.writer is None:
            self.record_input_width, self.record_input_height = width, height
            self.record_width = width + width % 2
            self.record_height = height + height % 2
            path = self.record_dir / "camera.avi"
            self.writer = cv2.VideoWriter(
                str(path), cv2.VideoWriter_fourcc(*"MJPG"), RECORD_FPS,
                (self.record_width, self.record_height),
            )
            if not self.writer.isOpened():
                self.writer.release()
                self.writer = None
                raise HTTPException(500, "Não foi possível iniciar a gravação de vídeo.")
        elif (width, height) != (self.record_input_width, self.record_input_height):
            raise HTTPException(422, "A resolução da câmera mudou durante a gravação.")
        if self.record_width != width or self.record_height != height:
            image = cv2.copyMakeBorder(
                image, 0, self.record_height - height, 0, self.record_width - width,
                cv2.BORDER_REPLICATE,
            )
        copies = max(1, round((timestamp - self.last_recorded_timestamp) * RECORD_FPS))
        if self.record_frame_count + copies > MAX_SESSION_SECONDS * RECORD_FPS + RECORD_FPS:
            raise HTTPException(413, "A gravação excede o limite de 30 minutos.")
        for _ in range(copies):
            self.writer.write(image)
        self.record_frame_count += copies
        self.last_recorded_timestamp = timestamp
        self.last_recorded_image = image.copy()

    def add_frame(self, image, timestamp: float, digest: str):
        with self.lock:
            if self.closed or self.closing:
                raise HTTPException(409, "Sessão encerrada ou em finalização.")
            if timestamp > MAX_SESSION_SECONDS:
                raise HTTPException(422, "O limite por sessão é de 30 minutos.")
            if self.last_frame_timestamp is not None:
                if timestamp < self.last_frame_timestamp:
                    raise HTTPException(409, "Timestamp de imagem retrocedeu.")
                if timestamp == self.last_frame_timestamp:
                    if digest == self.last_frame_hash:
                        self._persist()
                        return self._snapshot()
                    raise HTTPException(409, "Timestamp já usado por outro frame.")
            if self.frame_count >= MAX_FRAMES:
                raise HTTPException(413, "A sessão excedeu o limite de frames.")
            self._ensure_model()
            height, width = image.shape[:2]
            try:
                result = self.model.predict(image, verbose=False)[0]
                payload = self.tracker.annotate(
                    analyze_pose(result, width, height, "bed", DEFAULT_THRESHOLDS),
                )
                current = set(frame_events(payload, self.fence))
                self._write_video_frame(image, timestamp)
                for kind, severity in sorted(current - self.previous_frame_events):
                    self.image_events.append({
                        "timestamp": timestamp, "kind": kind, "severity": severity, "source": "image",
                    })
                self.previous_frame_events = current
            except HTTPException:
                raise
            except Exception as error:
                logger.exception("Falha ao analisar frame da câmera %s", self.id)
                raise HTTPException(500, "Falha na análise YOLO do frame. O frame pode ser reenviado.") from error
            self.last_frame_timestamp = timestamp
            self.last_frame_hash = digest
            self.frame_count += 1
            self.frame = {
                "timestamp": timestamp,
                "people": payload["people"],
                "fence": self.fence,
                "events": [{"kind": kind, "severity": severity} for kind, severity in sorted(current)],
            }
            self._persist()
            return self._snapshot()

    def add_audio(self, pcm: bytes, duration: float, timestamp: float, digest: str):
        with self.lock:
            if self.closed or self.closing:
                raise HTTPException(409, "Sessão encerrada ou em finalização.")
            end = timestamp + duration
            if end > MAX_SESSION_SECONDS:
                raise HTTPException(422, "O limite por sessão é de 30 minutos.")
            if self.last_audio_start is not None and timestamp == self.last_audio_start:
                if digest == self.last_audio_hash:
                    self._persist()
                    return self._snapshot()
                raise HTTPException(409, "Timestamp já usado por outro trecho de áudio.")
            if self.speech_finished:
                raise HTTPException(409, "Sessão de áudio já finalizada.")
            if timestamp + 1e-6 < self.audio_end:
                raise HTTPException(409, "Trechos de áudio precisam ser enviados em ordem e sem sobreposição.")
            gap = max(0.0, timestamp - self.audio_end)
            if gap > MAX_AUDIO_SECONDS:
                raise HTTPException(422, "Intervalo entre trechos de áudio excede 30 segundos.")
            if self.audio_origin is None:
                self.audio_origin = timestamp
            try:
                if self.record:
                    audio_path = self.record_dir / "audio.pcm"
                    with audio_path.open("r+b") as output:
                        output.seek(round(timestamp * 16_000) * 2)
                        output.write(pcm)
                    self.audio_bytes_written += len(pcm)
                if gap:
                    self.speech.write(bytes(round(gap * 16_000) * 2))
                self.speech.write(pcm)
            except Exception as error:
                logger.exception("Falha ao receber áudio da câmera %s", self.id)
                self.audio_error = "Não foi possível encaminhar o áudio ao Azure Speech."
                self._persist()
                return self._snapshot()
            self.last_audio_start = timestamp
            self.last_audio_hash = digest
            self.audio_end = end
            self._persist()
            return self._snapshot()

    def _release_writer(self):
        if self.writer is not None:
            self.writer.release()
            self.writer = None

    def _finalize_recording(self):
        if not self.record:
            return None
        if self.record_frame_count == 0:
            raise RuntimeError("Não há frames para salvar; mantenha a câmera ativa e tente novamente.")
        target_frames = max(
            self.record_frame_count,
            math.ceil(max(self.last_frame_timestamp or 0.0, self.audio_end) * RECORD_FPS - 1e-9),
        )
        for _ in range(target_frames - self.record_frame_count):
            self.writer.write(self.last_recorded_image)
        self.record_frame_count = target_frames
        self._release_writer()
        identifier = uuid.uuid4().hex
        staging = self.record_dir / "recording.mp4"
        source = self.record_dir / "camera.avi"
        command = ["ffmpeg", "-nostdin", "-y", "-v", "error", "-i", str(source)]
        if self.audio_bytes_written:
            command += [
                "-f", "s16le", "-ar", "16000", "-ac", "1",
                "-i", str(self.record_dir / "audio.pcm"),
            ]
        else:
            command += [
                "-f", "lavfi", "-i", "anullsrc=channel_layout=mono:sample_rate=16000",
            ]
        command += [
            "-map", "0:v:0",
            "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2",
        ]
        command += ["-map", "1:a:0"]
        command += ["-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p"]
        command += ["-af", "apad", "-c:a", "aac", "-shortest", "-movflags", "+faststart", str(staging)]
        try:
            subprocess.run(command, check=True, capture_output=True, timeout=600)
        except (subprocess.SubprocessError, OSError) as error:
            logger.exception("Falha ao finalizar gravação de câmera %s", self.id)
            if isinstance(error, subprocess.CalledProcessError) and error.stderr:
                logger.error("FFmpeg: %s", error.stderr.decode(errors="replace").strip())
            raise RuntimeError(
                "A gravação não foi finalizada. Os arquivos temporários foram preservados; "
                "tente encerrar novamente.",
            ) from error
        destination = DATA_DIR / f"{identifier}.mp4"
        try:
            staging.replace(destination)
            with connect() as db:
                db.execute(
                    "INSERT INTO videos "
                    "(id,name,mode,status,progress,duration,fps,width,height,error,fence,thresholds,"
                    "posture_config,is_sample,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        identifier, f"Câmera {self.created_at[:16].replace('T', ' ')}",
                        "bed", "ready", 1, max(
                            self.record_frame_count / RECORD_FPS, self.audio_end,
                        ), RECORD_FPS, self.record_width, self.record_height, None,
                        json.dumps(self.fence), json.dumps(DEFAULT_THRESHOLDS), None, 0, self.created_at,
                    ),
                )
        except Exception:
            destination.unlink(missing_ok=True)
            raise
        self.recording_id = identifier
        shutil.rmtree(self.record_dir, ignore_errors=True)
        self.record_dir = None
        return identifier

    def close(self):
        with self.lock:
            if self.closed:
                self._persist()
                return self._snapshot()
            if self.closing:
                raise HTTPException(409, "Finalização já está em andamento.")
            self.closing = True
            speech = self.speech
        if speech is not None and not self.speech_finished:
            try:
                speech.finish()
                self.speech_finished = True
            except Exception as error:
                logger.warning("Falha ao concluir Azure Speech da câmera %s: %s", self.id, error)
                with self.lock:
                    self.audio_error = str(error) if isinstance(error, AzureAudioError) else (
                        "Falha ao concluir o reconhecimento de áudio."
                    )
                    self.speech_finished = True
        with self.lock:
            try:
                self._finalize_recording()
            except Exception as error:
                self.closing = False
                self.audio_error = self.audio_error or str(error)
                self._persist()
                raise HTTPException(500, str(error)) from error
            self.closed = True
            self.closing = False
            self._persist()
            return self._snapshot()


@router.get("/fence")
def get_fence():
    with connect() as db:
        row = db.execute("SELECT fence FROM camera_fences WHERE id=1").fetchone()
    return {"fence": json.loads(row["fence"]) if row else None}


@router.put("/fence")
def save_fence(fence: Fence):
    value = fence.model_dump()
    with connect() as db:
        db.execute(
            "INSERT INTO camera_fences (id,fence) VALUES (1,?) "
            "ON CONFLICT(id) DO UPDATE SET fence=excluded.fence",
            (json.dumps(value),),
        )
    return {"fence": value}


@router.post("/monitor", status_code=201)
def create_monitor(request: CreateCameraMonitor):
    with connect() as db:
        row = db.execute("SELECT fence FROM camera_fences WHERE id=1").fetchone()
    if row is None:
        raise HTTPException(409, "Salve uma cerca virtual ativa antes de iniciar o monitoramento.")
    saved_fence = json.loads(row["fence"])
    if saved_fence != request.fence.model_dump():
        raise HTTPException(409, "A cerca enviada não corresponde à última cerca salva.")
    _check_dependencies(request.record)
    try:
        speech_config = configuration(require_language=False)
        session = CameraSession(saved_fence, request.record, speech_config)
    except AzureAudioError as error:
        raise HTTPException(503, str(error)) from error
    except Exception as error:
        logger.exception("Não foi possível iniciar Azure Speech para a câmera")
        raise HTTPException(
            503, "Não foi possível iniciar Azure Speech. Verifique SDK, região, quota e rede.",
        ) from error
    with registry_lock:
        if len(sessions) >= 8:
            session.speech.stop()
            if session.record_dir is not None:
                shutil.rmtree(session.record_dir, ignore_errors=True)
            raise HTTPException(429, "Feche uma sessão de câmera antes de abrir outra.")
        sessions[session.id] = session
    try:
        session._persist()
    except Exception:
        with registry_lock:
            sessions.pop(session.id, None)
        try:
            session.speech.stop()
        finally:
            if session.record_dir is not None:
                shutil.rmtree(session.record_dir, ignore_errors=True)
        raise
    return session.snapshot()


@router.get("/monitor/{session_id}")
def get_monitor(session_id: str):
    with registry_lock:
        session = sessions.get(session_id)
    if session is not None:
        return session.snapshot()
    snapshot, _ = _camera_session_row(session_id)
    return snapshot


@router.post("/monitor/{session_id}/frame")
async def upload_frame(
    session_id: str,
    file: UploadFile = File(...),
    timestamp: str = Form(...),
):
    session = _require_session(session_id)
    try:
        moment = _timestamp(timestamp)
        data = await file.read(MAX_FRAME_BYTES + 1)
    finally:
        await file.close()
    if len(data) > MAX_FRAME_BYTES:
        raise HTTPException(413, "O limite por frame é 10 MB.")
    image = await run_in_threadpool(_read_frame, data)
    return await run_in_threadpool(
        session.add_frame, image, moment, hashlib.sha256(data).hexdigest(),
    )


@router.post("/monitor/{session_id}/audio")
async def upload_audio(
    session_id: str,
    file: UploadFile = File(...),
    timestamp: str = Form(...),
):
    session = _require_session(session_id)
    try:
        moment = _timestamp(timestamp)
        data = await file.read(MAX_AUDIO_BYTES + 1)
    finally:
        await file.close()
    if len(data) > MAX_AUDIO_BYTES:
        raise HTTPException(413, "O limite por trecho de áudio é 2 MB.")
    pcm, duration = await run_in_threadpool(_read_audio, data)
    return await run_in_threadpool(
        session.add_audio, pcm, duration, moment, hashlib.sha256(data).hexdigest(),
    )


@router.post("/monitor/{session_id}/acknowledge")
def acknowledge_monitor(session_id: str, request: AcknowledgeAlerts):
    with registry_lock:
        session = sessions.get(session_id)
    lock = session.lock if session else threading.RLock()
    with lock, connect() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute(
            "SELECT snapshot FROM camera_sessions WHERE id=?", (session_id,),
        ).fetchone()
        if row is None:
            raise HTTPException(404, "Sessão de câmera não encontrada.")
        try:
            alerts = alert_log.acknowledge(db, session_id, request.alert_ids)
        except ValueError as error:
            raise HTTPException(409, str(error)) from error
        if session is not None:
            session.alerts = alerts
            snapshot = session._snapshot()
        else:
            snapshot = json.loads(row["snapshot"])
            snapshot["alerts"] = alerts
        encoded = json.dumps(snapshot, ensure_ascii=False)
        db.execute("UPDATE monitor_sessions SET snapshot=? WHERE id=?", (encoded, session_id))
        db.execute("UPDATE camera_sessions SET snapshot=? WHERE id=?", (encoded, session_id))
    return alerts


@router.get("/alert-log")
def camera_alert_log():
    with connect() as db:
        rows = db.execute(
            "SELECT l.id,l.action,l.created_at,l.payload FROM monitor_alert_log l "
            "JOIN camera_sessions c ON c.id=l.session_id ORDER BY l.id DESC LIMIT 500",
        ).fetchall()
    return [{**dict(row), "payload": json.loads(row["payload"])} for row in rows]


@router.delete("/monitor/{session_id}")
def close_monitor(session_id: str):
    with registry_lock:
        session = sessions.get(session_id)
    if session is None:
        snapshot, closed = _camera_session_row(session_id)
        if closed:
            return snapshot
        raise HTTPException(409, "Sessão interrompida pelo servidor; arquivos e estado foram preservados.")
    snapshot = session.close()
    with registry_lock:
        if session.closed:
            sessions.pop(session_id, None)
    return snapshot


def shutdown():
    with registry_lock:
        active = list(sessions.values())
    for session in active:
        try:
            session.close()
        except HTTPException:
            logger.exception("Falha ao salvar gravação de câmera durante o encerramento.")
        except Exception:
            logger.exception("Falha ao encerrar sessão de câmera %s.", session.id)
    with registry_lock:
        sessions.clear()
