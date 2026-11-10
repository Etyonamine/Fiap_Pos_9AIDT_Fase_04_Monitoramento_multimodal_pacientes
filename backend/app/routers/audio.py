import json
import logging
import shutil
import subprocess
import uuid
import wave
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app.database import DATA_DIR, connect
from app.services.audio_analysis import RULES_VERSION, acoustic_analysis, critical_terms
from app.services.azure_service import AzureAudioError, analyze_language, configuration, transcribe

router = APIRouter(prefix="/api/audios", tags=["audio"])
executor = ThreadPoolExecutor(max_workers=1)
logger = logging.getLogger(__name__)
MAX_BYTES = 100 * 1024 * 1024
MAX_SECONDS = 1800
SUFFIXES = {".wav", ".mp3", ".m4a", ".ogg", ".flac", ".webm", ".aac"}


def get_audio(audio_id: str) -> dict:
    with connect() as db:
        row = db.execute("SELECT * FROM audios WHERE id=?", (audio_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "Áudio não encontrado.")
    audio = dict(row)
    for field in ("result", "acoustic"):
        audio[field] = json.loads(audio[field]) if audio[field] else None
    result = audio["result"]
    if result and result.get("rules_version", 0) < RULES_VERSION:
        result["critical_terms"] = critical_terms(result["transcription"]["text"])
        result["rules_version"] = RULES_VERSION
        with connect() as db:
            db.execute(
                "UPDATE audios SET result=? WHERE id=? AND result=?",
                (json.dumps(result), audio_id, row["result"]),
            )
    audio["url"] = f"/api/audios/{audio_id}/media" if audio["duration"] > 0 else None
    return audio


def normalized_path(audio_id: str) -> Path:
    return DATA_DIR / f"audio-{audio_id}.wav"


def fail(audio_id: str, message: str):
    with connect() as db:
        db.execute("UPDATE audios SET status='failed', error=? WHERE id=?", (message, audio_id))


def import_audio(audio_id: str, source: Path):
    output = normalized_path(audio_id)
    try:
        subprocess.run(
            ["ffmpeg", "-nostdin", "-y", "-protocol_whitelist", "file,pipe",
             "-i", str(source), "-map", "0:a:0", "-vn", "-t", str(MAX_SECONDS + 1),
             "-af", "aresample=async=1:first_pts=0",
             "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(output)],
            check=True, capture_output=True, timeout=180,
        )
        acoustic = acoustic_analysis(output)
        if acoustic["duration"] > MAX_SECONDS:
            raise ValueError("O limite por gravação é 30 minutos. Divida a consulta antes de importar.")
        with connect() as db:
            db.execute("UPDATE audios SET status='uploaded', duration=?, acoustic=? WHERE id=?",
                       (acoustic["duration"], json.dumps(acoustic), audio_id))
    except (subprocess.SubprocessError, OSError, ValueError, wave.Error) as error:
        message = str(error) if isinstance(error, ValueError) else (
            "Não foi possível decodificar o áudio. Verifique o arquivo e o FFmpeg no servidor."
        )
        logger.warning("Falha na importação do áudio %s (%s)", audio_id, type(error).__name__)
        output.unlink(missing_ok=True)
        fail(audio_id, message)
    except Exception:
        logger.exception("Falha inesperada na importação do áudio %s", audio_id)
        output.unlink(missing_ok=True)
        fail(audio_id, "Falha inesperada na importação. Consulte o log do servidor e reimporte.")
    finally:
        source.unlink(missing_ok=True)


def process_audio(audio_id: str, config: dict):
    try:
        with connect() as db:
            db.execute("UPDATE audios SET status='analyzing' WHERE id=?", (audio_id,))
        audio = get_audio(audio_id)
        result = {"transcription": transcribe(normalized_path(audio_id), audio["duration"], config)}
        result["critical_terms"] = critical_terms(result["transcription"]["text"])
        result["rules_version"] = RULES_VERSION
        # Preserve successful Speech output even if Language is unavailable.
        with connect() as db:
            db.execute("UPDATE audios SET result=? WHERE id=?", (json.dumps(result), audio_id))
        result["language"] = analyze_language(result["transcription"]["text"], config)
        with connect() as db:
            db.execute("UPDATE audios SET status='ready', result=?, error=NULL WHERE id=?",
                       (json.dumps(result), audio_id))
    except AzureAudioError as error:
        logger.warning("Falha na análise Azure do áudio %s: %s", audio_id, error)
        fail(audio_id, str(error))
    except Exception:
        logger.exception("Falha inesperada na análise do áudio %s", audio_id)
        fail(audio_id, "Falha inesperada na análise. Consulte o log do servidor e tente novamente.")


@router.get("/configuration")
def azure_configuration():
    try:
        configuration()
    except AzureAudioError as error:
        return {"configured": False, "message": str(error)}
    return {"configured": True, "message": "Credenciais configuradas; conexão validada apenas na análise."}


@router.get("")
def list_audios():
    with connect() as db:
        ids = db.execute("SELECT id FROM audios ORDER BY created_at DESC, rowid DESC").fetchall()
    return [get_audio(row["id"]) for row in ids]


@router.post("", status_code=202)
async def upload(file: UploadFile = File(...)):
    if shutil.which("ffmpeg") is None:
        raise HTTPException(503, "Instale FFmpeg no servidor antes de importar áudios.")
    name = (file.filename or "audio").replace("\\", "/").split("/")[-1]
    suffix = Path(name).suffix.lower()
    if suffix not in SUFFIXES:
        raise HTTPException(415, "Envie WAV, MP3, M4A, OGG, FLAC, WebM ou AAC.")
    audio_id = uuid.uuid4().hex
    source = DATA_DIR / f"audio-upload-{audio_id}{suffix}"
    size = 0
    try:
        with source.open("wb") as target:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_BYTES:
                    raise HTTPException(413, "O limite por arquivo é 100 MB.")
                target.write(chunk)
        if not size:
            raise HTTPException(422, "Arquivo vazio.")
        with connect() as db:
            db.execute("INSERT INTO audios (id,name,status,created_at) VALUES (?,?,'importing',?)",
                       (audio_id, name, datetime.now(timezone.utc).isoformat()))
        executor.submit(import_audio, audio_id, source)
        return get_audio(audio_id)
    except Exception:
        source.unlink(missing_ok=True)
        raise
    finally:
        await file.close()


@router.get("/{audio_id}")
def status(audio_id: str):
    return get_audio(audio_id)


@router.get("/{audio_id}/media")
def media(audio_id: str):
    audio = get_audio(audio_id)
    path = normalized_path(audio_id)
    if not audio["url"] or not path.is_file():
        raise HTTPException(409, "O áudio ainda não está disponível para reprodução.")
    return FileResponse(path, media_type="audio/wav")


@router.post("/{audio_id}/analyze", status_code=202)
def analyze(audio_id: str):
    audio = get_audio(audio_id)
    if not audio["url"] or not normalized_path(audio_id).is_file():
        raise HTTPException(409, "Importe um áudio válido antes de analisar.")
    try:
        config = configuration()
    except AzureAudioError as error:
        logger.warning("Análise do áudio %s não iniciada: %s", audio_id, error)
        raise HTTPException(503, str(error)) from error
    with connect() as db:
        changed = db.execute(
            "UPDATE audios SET status='queued', error=NULL, result=NULL "
            "WHERE id=? AND status IN ('uploaded', 'ready', 'failed')", (audio_id,)
        ).rowcount
        if not changed:
            raise HTTPException(409, "Este áudio já está em processamento.")
    executor.submit(process_audio, audio_id, config)
    return get_audio(audio_id)


@router.delete("/{audio_id}", status_code=204)
def delete(audio_id: str):
    audio = get_audio(audio_id)
    try:
        with connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT status FROM audios WHERE id=?", (audio_id,)).fetchone()
            if row is None:
                raise HTTPException(404, "Áudio não encontrado.")
            if db.execute("SELECT id FROM videos WHERE audio_id=?", (audio_id,)).fetchone():
                raise HTTPException(409, "Este áudio pertence a uma análise de leito e deve ser preservado.")
            if row["status"] in ("importing", "queued", "analyzing"):
                raise HTTPException(409, "Aguarde o processamento antes de excluir o áudio.")
            normalized_path(audio_id).unlink(missing_ok=True)
            suffix = Path(audio["name"]).suffix.lower()
            if suffix in SUFFIXES:
                (DATA_DIR / f"audio-upload-{audio_id}{suffix}").unlink(missing_ok=True)
            db.execute("DELETE FROM audios WHERE id=?", (audio_id,))
    except OSError as error:
        logger.exception("Falha na exclusão dos arquivos do áudio %s", audio_id)
        raise HTTPException(500, "Não foi possível excluir os arquivos do áudio. "
                            "Consulte o log do servidor e tente novamente.") from error