import json
import logging
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import httpx
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.database import connect
from app.services.audio_analysis import critical_terms
from app.services.azure_service import AzureAudioError, analyze_language, configuration
from app.services.clinical_data import (
    ClinicalDataError, analyze_prescriptions, analyze_vitals, note_events, parse_records,
    patient_ref, timestamp,
)
from app.services.fhir_r4 import FhirConfigurationError, FhirResponseError, import_patient_data

router = APIRouter(prefix="/api/clinical-data", tags=["clinical data"])
logger = logging.getLogger(__name__)
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
MAX_NOTE_BYTES = 1024 * 1024
EXAMPLES = Path(__file__).resolve().parents[2] / "evaluation" / "examples"
EXAMPLE_FILES = {
    "vitals": ("synthetic_vitals_24h.csv", "text/csv"),
    "prescriptions": ("synthetic_prescriptions.json", "application/json"),
    "note": ("synthetic_clinical_note.json", "application/json"),
}


class FhirImport(BaseModel):
    patient_id: str
    kind: Literal["vitals", "prescriptions"]
    authorized: bool


def _safe_filename(upload: UploadFile) -> str:
    filename = (upload.filename or "import").replace("\\", "/").split("/")[-1]
    if not filename or len(filename) > 160:
        raise HTTPException(422, "Nome do arquivo inválido.")
    return filename


def _store(kind: str, filename: str, result: dict) -> dict:
    import_id = uuid.uuid4().hex
    created_at = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    patient_refs = {}

    def scoped_patient_ref(value: str) -> str:
        return patient_refs.setdefault(value, f"imp-{import_id[:8]}-{len(patient_refs) + 1:03d}")

    if "patient_ref" in result:
        result["patient_ref"] = scoped_patient_ref(result["patient_ref"])
    for collection in ("points", "records", "events"):
        for item in result.get(collection, []):
            if "patient_ref" in item:
                item["patient_ref"] = scoped_patient_ref(item["patient_ref"])
    serialized = json.dumps(result, ensure_ascii=False, allow_nan=False)
    with connect() as db:
        db.execute(
            "INSERT INTO clinical_imports (id,kind,name,created_at,result) VALUES (?,?,?,?,?)",
            (import_id, kind, filename, created_at, serialized),
        )
    return {"id": import_id, "kind": kind, "name": filename, "created_at": created_at, **result}


async def _read_upload(upload: UploadFile, maximum: int) -> tuple[str, bytes]:
    name = _safe_filename(upload)
    content = await upload.read(maximum + 1)
    await upload.close()
    if not content:
        raise HTTPException(422, "O arquivo está vazio.")
    if len(content) > maximum:
        raise HTTPException(413, f"O limite por arquivo é {maximum // (1024 * 1024)} MB.")
    return name, content


def _analysis_error(error: Exception) -> HTTPException:
    logger.warning("Falha na análise de texto clínico (%s)", type(error).__name__)
    return HTTPException(
        502, "Azure AI Language não concluiu a análise. O texto não foi persistido; "
        "verifique a configuração e tente novamente."
    )


@router.get("/examples/{kind}")
def download_example(kind: str):
    example = EXAMPLE_FILES.get(kind)
    if example is None:
        raise HTTPException(404, "Exemplo não encontrado.")
    filename, media_type = example
    path = EXAMPLES / filename
    if not path.is_file():
        raise HTTPException(404, "O arquivo de exemplo não está instalado no servidor.")
    return FileResponse(path, media_type=media_type, filename=filename)


@router.get("/imports")
def list_imports():
    with connect() as db:
        rows = db.execute(
            "SELECT id,kind,name,created_at,result FROM clinical_imports "
            "ORDER BY created_at DESC LIMIT 200"
        ).fetchall()
    return [
        {"id": row["id"], "kind": row["kind"], "name": row["name"],
         "created_at": row["created_at"], **json.loads(row["result"])}
        for row in rows
    ]


@router.post("/vitals", status_code=201)
async def import_vitals(file: UploadFile = File(...)):
    name, content = await _read_upload(file, MAX_UPLOAD_BYTES)
    try:
        records = parse_records(content, name)
        result = analyze_vitals(records, {})
    except ClinicalDataError as error:
        raise HTTPException(422, str(error)) from error
    return _store("vitals", name, result)


@router.post("/prescriptions", status_code=201)
async def import_prescriptions(file: UploadFile = File(...)):
    name, content = await _read_upload(file, MAX_UPLOAD_BYTES)
    try:
        records = parse_records(content, name)
        result = analyze_prescriptions(records, {})
    except ClinicalDataError as error:
        raise HTTPException(422, str(error)) from error
    return _store("prescriptions", name, result)


@router.post("/fhir", status_code=201)
def import_fhir(request: FhirImport):
    if not request.authorized:
        raise HTTPException(400, "Confirme autorização para consultar o prontuário FHIR.")
    try:
        result = import_patient_data(request.patient_id, request.kind)
    except ClinicalDataError as error:
        raise HTTPException(422, str(error)) from error
    except FhirConfigurationError as error:
        raise HTTPException(503, str(error)) from error
    except FhirResponseError as error:
        logger.warning("Falha na importação FHIR (%s)", type(error).__name__)
        raise HTTPException(502, str(error)) from error
    name = "FHIR R4 · sinais vitais" if request.kind == "vitals" else "FHIR R4 · prescrições"
    return _store(request.kind, name, result)


@router.post("/notes", status_code=201)
async def import_note(
    file: UploadFile = File(...),
    consent_to_cloud: bool = Form(False),
):
    if not consent_to_cloud:
        await file.close()
        raise HTTPException(
            400, "Confirme a autorização para enviar o texto ao Azure AI Language."
        )
    name, content = await _read_upload(file, MAX_NOTE_BYTES)
    if not name.lower().endswith(".json"):
        raise HTTPException(415, "Envie uma nota sintética/desidentificada em JSON.")
    try:
        payload = json.loads(content.decode("utf-8-sig"))
        if not isinstance(payload, dict):
            raise ClinicalDataError("A nota JSON deve ser um objeto.")
        patient = patient_ref(payload.get("patient_id"), 1)
        recorded_at = timestamp(payload.get("recorded_at"), 1)
        text = payload.get("text")
        if not isinstance(text, str) or not text.strip() or len(text) > 12_000:
            raise ClinicalDataError("text é obrigatório e deve ter até 12.000 caracteres.")
        config = configuration(require_speech=False)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise HTTPException(422, "Não foi possível interpretar o JSON da nota.") from error
    except ClinicalDataError as error:
        raise HTTPException(422, str(error)) from error
    except AzureAudioError as error:
        raise HTTPException(503, str(error)) from error

    try:
        language = analyze_language(text, config)
    except AzureAudioError as error:
        raise _analysis_error(error) from error
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as error:
        raise _analysis_error(error) from error

    pseudonym = {"case": "caso-001"}
    mentions = critical_terms(text)
    result = {
        "kind": "notes", "record_count": 1, "patient_count": 1,
        "patient_ref": next(iter(pseudonym.values())), "recorded_at": recorded_at,
        "events": note_events(text, next(iter(pseudonym.values())), recorded_at, mentions),
        "mentions": [
            {"term": item["term"], "severity": item["severity"], "negated": item["negated"]}
            for item in mentions
        ],
        "language": {
            "provider": language["provider"],
            "key_phrases": language["key_phrases"],
            "key_phrase_mentions": language["key_phrase_mentions"],
            "sentiment": {
                "label": language["sentiment"]["label"],
                "scores": language["sentiment"]["scores"],
                "aggregation": language["sentiment"]["aggregation"],
            },
        },
        "notice": (
            "Análise de texto, não de voz. Menções e sentimento não são diagnóstico. "
            "O texto original não é armazenado localmente; o resumo derivado fica no histórico."
        ),
    }
    return _store("notes", name, result)
