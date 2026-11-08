import json
import logging
import math
import shutil
import subprocess
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import cv2
from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, model_validator

from app.database import DATA_DIR, connect
from app.services.yolo_services import (
    DEFAULT_FENCE, DEFAULT_THRESHOLDS, FISIO_FENCE, MODEL_PATH, FenceSubjectTracker,
    analyze_pose, frame_events, update_threshold_anomalies,
)

router = APIRouter(prefix="/api/videos", tags=["video"])
logger = logging.getLogger(__name__)
executor = ThreadPoolExecutor(max_workers=1)
MAX_BYTES = 500 * 1024 * 1024


class Fence(BaseModel):
    enabled: bool = True
    x: float = Field(ge=0, le=1, allow_inf_nan=False)
    y: float = Field(ge=0, le=1, allow_inf_nan=False)
    width: float = Field(gt=0, le=1, allow_inf_nan=False)
    height: float = Field(gt=0, le=1, allow_inf_nan=False)

    @model_validator(mode="after")
    def bounds(self):
        if self.x + self.width > 1 or self.y + self.height > 1:
            raise ValueError("A cerca deve estar dentro do vídeo.")
        return self


class Thresholds(BaseModel):
    trunk_angle: float = Field(ge=0, le=90, allow_inf_nan=False)
    knee_angle: float = Field(ge=0, le=180, allow_inf_nan=False)


def get_video(video_id):
    with connect() as db:
        row = db.execute("SELECT * FROM videos WHERE id=?", (video_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "Vídeo não encontrado.")
    video = dict(row)
    video["fence"] = json.loads(video["fence"])
    video["thresholds"] = json.loads(video["thresholds"])
    video["url"] = f"/api/videos/{video_id}/media"
    return video


def require_ready(video_id):
    video = get_video(video_id)
    if video["status"] != "ready":
        raise HTTPException(409, "O processamento ainda não foi concluído.")
    return video


def check_dependencies():
    if not MODEL_PATH.is_file():
        raise HTTPException(503, "Instale os pesos YOLOv8 Pose em YOLO_MODEL_PATH antes do upload.")
    if shutil.which("ffmpeg") is None:
        raise HTTPException(503, "FFmpeg não está instalado no servidor.")


def process_video(video_id, source):
    capture = None
    try:
        from ultralytics import YOLO

        with connect() as db:
            db.execute("UPDATE videos SET status='processing' WHERE id=?", (video_id,))
        # Normalize AVI/MOV and variable-rate sources to a browser-playable, indexed CFR timeline.
        output = DATA_DIR / f"{video_id}.mp4"
        subprocess.run(
            ["ffmpeg", "-nostdin", "-y", "-i", str(source), "-map", "0:v:0",
             "-map", "0:a?", "-vf", "fps=25,pad=ceil(iw/2)*2:ceil(ih/2)*2", "-c:v", "libx264", "-pix_fmt", "yuv420p",
             "-c:a", "aac", "-shortest", "-movflags", "+faststart", str(output)],
            check=True, capture_output=True, timeout=1800,
        )
        capture = cv2.VideoCapture(str(output))
        width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        total = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = capture.get(cv2.CAP_PROP_FPS)
        if not capture.isOpened() or not total or not width or not height or not math.isfinite(fps) or fps <= 0:
            raise ValueError("Arquivo sem frames de vídeo decodificáveis.")
        video = get_video(video_id)
        model = YOLO(str(MODEL_PATH))
        if model.task != "pose":
            raise ValueError("Os pesos configurados devem ser de um modelo YOLO Pose.")
        fence_tracker = FenceSubjectTracker(video["fence"])
        previous = set()
        index = 0
        with connect() as db:
            db.execute("UPDATE videos SET width=?, height=?, fps=?, duration=? WHERE id=?",
                       (width, height, fps, total / fps, video_id))
            while True:
                ok, image = capture.read()
                if not ok:
                    break
                timestamp = index / fps
                result = model.predict(image, verbose=False)[0]
                payload = fence_tracker.annotate(
                    analyze_pose(result, width, height, video["mode"], video["thresholds"])
                )
                db.execute("INSERT INTO frames VALUES (?, ?, ?)",
                           (video_id, timestamp, json.dumps(payload)))
                events = set(frame_events(payload, video["fence"]))
                for kind, severity in events - previous:
                    db.execute("INSERT INTO events VALUES (?, ?, ?, ?)", (video_id, timestamp, kind, severity))
                previous = events
                index += 1
                if index % 25 == 0:
                    db.execute("UPDATE videos SET progress=? WHERE id=?", (index / total, video_id))
                    db.commit()
            if index != total:
                raise ValueError("Decodificação incompleta; envie um arquivo íntegro.")
            db.execute("UPDATE videos SET status='ready', progress=1 WHERE id=?", (video_id,))
    except Exception:
        logger.exception("Falha no processamento do vídeo %s", video_id)
        with connect() as db:
            db.execute("UPDATE videos SET status='failed', error=? WHERE id=?",
                       ("Falha ao decodificar ou executar YOLO. Consulte o log do servidor e reenvie.", video_id))
    finally:
        if capture is not None:
            capture.release()
        source.unlink(missing_ok=True)


def register(name, mode, source, is_sample=False):
    video_id = uuid.uuid4().hex
    fence = FISIO_FENCE if mode == "fisio" else DEFAULT_FENCE
    created_at = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    with connect() as db:
        db.execute(
            "INSERT INTO videos (id,name,mode,status,fence,thresholds,is_sample,created_at) "
            "VALUES (?,?,?,'queued',?,?,?,?)",
            (video_id, name, mode, json.dumps(fence), json.dumps(DEFAULT_THRESHOLDS),
             int(is_sample), created_at),
        )
    executor.submit(process_video, video_id, source)
    return get_video(video_id)


def load_samples():
    directory = DATA_DIR / "samples"
    directory.mkdir(parents=True, exist_ok=True)
    for source in sorted(directory.iterdir()):
        if not source.is_file() or source.suffix.lower() not in {".mp4", ".avi", ".mov", ".webm"}:
            continue
        with connect() as db:
            exists = db.execute("SELECT id FROM videos WHERE name=? AND is_sample=1 AND status!='failed'",
                                (source.name,)).fetchone()
        if exists:
            continue
        check_dependencies()
        copy = DATA_DIR / f"{uuid.uuid4().hex}{source.suffix}"
        shutil.copyfile(source, copy)
        register(source.name, "fisio" if source.name.startswith(("physio", "fisio")) else "bed", copy, True)


@router.get("")
def list_videos():
    with connect() as db:
        ids = db.execute("SELECT id FROM videos ORDER BY rowid DESC").fetchall()
    return [get_video(row["id"]) for row in ids]


@router.post("", status_code=202)
async def upload(file: UploadFile = File(...), mode: Literal["bed", "fisio"] = Form(...)):
    check_dependencies()
    name = (file.filename or "video").replace("\\", "/").split("/")[-1]
    suffix = Path(name).suffix.lower()
    if suffix not in {".mp4", ".avi", ".mov", ".webm"}:
        raise HTTPException(415, "Envie MP4, AVI, MOV ou WebM.")
    path = DATA_DIR / f"{uuid.uuid4().hex}{suffix}"
    size = 0
    try:
        with path.open("wb") as target:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_BYTES:
                    raise HTTPException(413, "O limite é 500 MB.")
                target.write(chunk)
        if not size:
            raise HTTPException(422, "Arquivo vazio.")
        return register(name, mode, path)
    except Exception:
        path.unlink(missing_ok=True)
        raise
    finally:
        await file.close()


@router.get("/{video_id}")
def status(video_id: str):
    return get_video(video_id)


@router.get("/{video_id}/media")
def media(video_id: str):
    require_ready(video_id)
    return FileResponse(DATA_DIR / f"{video_id}.mp4", media_type="video/mp4")


@router.get("/{video_id}/frame")
def frame(video_id: str, timestamp: float = Query(ge=0, allow_inf_nan=False)):
    video = require_ready(video_id)
    if timestamp > video["duration"]:
        raise HTTPException(422, "Timestamp fora do vídeo.")
    frame_number = min(math.floor(timestamp * video["fps"] + 1e-6),
                       math.ceil(video["duration"] * video["fps"]) - 1)
    with connect() as db:
        row = db.execute(
            "SELECT timestamp,payload FROM frames WHERE video_id=? AND timestamp<=? ORDER BY timestamp DESC LIMIT 1",
            (video_id, frame_number / video["fps"] + 1e-9),
        ).fetchone()
    if row is None:
        raise HTTPException(404, "Metadados não encontrados.")
    payload = json.loads(row["payload"])
    current_events = frame_events(payload, video["fence"])
    payload.pop("_fence_tracking_version", None)
    for person in payload["people"]:
        person.pop("fence_subject", None)
    return {"timestamp": row["timestamp"], **payload, "fence": video["fence"],
            "events": [{"kind": k, "severity": s} for k, s in current_events]}


@router.get("/{video_id}/events")
def events(video_id: str):
    require_ready(video_id)
    with connect() as db:
        return [dict(row) for row in db.execute(
            "SELECT timestamp,kind,severity FROM events WHERE video_id=? ORDER BY timestamp", (video_id,))]


@router.put("/{video_id}/fence")
def update_fence(video_id: str, fence: Fence):
    require_ready(video_id)
    value = fence.model_dump()
    fence_tracker = FenceSubjectTracker(value)
    previous = set()
    with connect() as db:
        db.execute("UPDATE videos SET fence=? WHERE id=?", (json.dumps(value), video_id))
        db.execute("DELETE FROM events WHERE video_id=?", (video_id,))
        rows = db.execute(
            "SELECT timestamp,payload FROM frames WHERE video_id=? ORDER BY timestamp", (video_id,)
        ).fetchall()
        for row in rows:
            payload = fence_tracker.annotate(json.loads(row["payload"]))
            db.execute(
                "UPDATE frames SET payload=? WHERE video_id=? AND timestamp=?",
                (json.dumps(payload), video_id, row["timestamp"]),
            )
            current = set(frame_events(payload, value))
            for kind, severity in current - previous:
                db.execute("INSERT INTO events VALUES (?,?,?,?)", (video_id, row["timestamp"], kind, severity))
            previous = current
    return get_video(video_id)


@router.put("/{video_id}/thresholds")
def update_thresholds(video_id: str, thresholds: Thresholds):
    video = require_ready(video_id)
    value = thresholds.model_dump()
    previous = set()
    with connect() as db:
        db.execute("UPDATE videos SET thresholds=? WHERE id=?", (json.dumps(value), video_id))
        db.execute("DELETE FROM events WHERE video_id=?", (video_id,))
        rows = db.execute(
            "SELECT timestamp,payload FROM frames WHERE video_id=? ORDER BY timestamp", (video_id,)
        ).fetchall()
        for row in rows:
            payload = update_threshold_anomalies(
                json.loads(row["payload"]), video["mode"], value
            )
            db.execute(
                "UPDATE frames SET payload=? WHERE video_id=? AND timestamp=?",
                (json.dumps(payload), video_id, row["timestamp"]),
            )
            current = set(frame_events(payload, video["fence"]))
            for kind, severity in current - previous:
                db.execute(
                    "INSERT INTO events VALUES (?,?,?,?)",
                    (video_id, row["timestamp"], kind, severity),
                )
            previous = current
    return get_video(video_id)


@router.get("/{video_id}/report")
def report(video_id: str):
    video = require_ready(video_id)
    return {
        "video": video, "model": "YOLOv8 Pose", "thresholds": video["thresholds"],
        "events": events(video_id),
        "disclaimer": "Triagem experimental por regras geométricas; não constitui diagnóstico "
                      "nem define faixas normais. Limiares configuráveis exigem validação "
                      "profissional. Saída da cerca não comprova queda.",
    }