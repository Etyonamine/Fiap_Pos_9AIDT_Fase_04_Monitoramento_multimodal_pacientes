import hmac
import json
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Header, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from app.database import connect
from app.services.clinical_data import (
    ClinicalDataError, analyze_prescriptions, analyze_vitals, patient_ref, timestamp,
)
from app.services.fhir_r4 import FhirResponseError, subscription_samples
from app.services.webhook_notifications import enqueue_clinical_event

router = APIRouter(prefix="/api/clinical-stream", tags=["clinical stream"])
logger = logging.getLogger(__name__)
MAX_SAMPLE_BYTES = 64 * 1024
MAX_BUNDLE_BYTES = 2 * 1024 * 1024
MAX_HISTORY = 1000
MAX_CLOCK_DRIFT_SECONDS = 10
NOTICE = (
    "Amostras associadas por sessão e tempo. Regras genéricas são para revisão, "
    "não diagnóstico nem validação de dose."
)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class VitalSample(StrictModel):
    heart_rate_bpm: float | None = Field(default=None, allow_inf_nan=False)
    systolic_mmhg: float | None = Field(default=None, allow_inf_nan=False)
    diastolic_mmhg: float | None = Field(default=None, allow_inf_nan=False)
    spo2_percent: float | None = Field(default=None, allow_inf_nan=False)

    @field_validator("*", mode="before")
    @classmethod
    def reject_boolean_vitals(cls, value):
        if isinstance(value, bool):
            raise ValueError("Sinais vitais devem ser numéricos.")
        return value


class PrescriptionSample(StrictModel):
    medication: str = Field(min_length=1, max_length=120)
    dose: float = Field(gt=0, le=100_000, allow_inf_nan=False)
    unit: str = Field(min_length=1, max_length=16)
    status: Literal["active", "discontinued"]
    route: str = Field(default="", max_length=40)
    frequency: str = Field(default="", max_length=80)

    @field_validator("dose", mode="before")
    @classmethod
    def reject_boolean_dose(cls, value):
        if isinstance(value, bool):
            raise ValueError("dose deve ser numérica.")
        return value


class ClinicalSample(StrictModel):
    sample_id: uuid.UUID
    source_id: str = Field(min_length=1, max_length=80)
    recorded_at: datetime
    elapsed_seconds: float = Field(ge=0, le=86_400, allow_inf_nan=False)
    vitals: VitalSample | None = None
    prescriptions: list[PrescriptionSample] = Field(default_factory=list, max_length=20)

    @field_validator("elapsed_seconds", mode="before")
    @classmethod
    def reject_boolean_elapsed(cls, value):
        if isinstance(value, bool):
            raise ValueError("elapsed_seconds deve ser numérico.")
        return value


def _configured_token() -> str:
    token = os.getenv("CLINICAL_INGEST_BEARER_TOKEN", "").strip()
    if len(token) < 32 or any(ord(character) < 33 or ord(character) > 126 for character in token):
        raise HTTPException(
            503, "Configure CLINICAL_INGEST_BEARER_TOKEN com ao menos 32 caracteres no backend."
        )
    return token


def _authorize(authorization: str | None) -> None:
    token = _configured_token()
    prefix, separator, supplied = (authorization or "").partition(" ")
    if (
        not separator or prefix.lower() != "bearer" or not supplied
        or not hmac.compare_digest(token, supplied)
    ):
        raise HTTPException(401, "Token de ingestão inválido.")


async def _json_body(request: Request, maximum: int) -> dict:
    content = bytearray()
    async for chunk in request.stream():
        content.extend(chunk)
        if len(content) > maximum:
            raise HTTPException(413, f"O limite da requisição é {maximum // 1024} KB.")
    try:
        value = json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise HTTPException(422, "Envie um objeto JSON UTF-8 válido.") from error
    if not isinstance(value, dict):
        raise HTTPException(422, "O corpo JSON deve ser um objeto.")
    return value


def _session(db, session_id: str, elapsed: float) -> None:
    row = db.execute(
        "SELECT snapshot FROM monitor_sessions WHERE id=?", (session_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(404, "Sessão de mídia não encontrada.")
    snapshot = json.loads(row["snapshot"])
    if snapshot.get("closed"):
        raise HTTPException(409, "A sessão de monitoramento está encerrada.")
    analyzed = snapshot.get("elapsed", snapshot.get("analyzed_until", 0))
    if elapsed > analyzed + MAX_CLOCK_DRIFT_SECONDS:
        raise HTTPException(422, "O instante informado está além do relógio da sessão de mídia.")


def _session_origin(snapshot: dict, supplied_origin: str | None) -> tuple[datetime, str]:
    session_mode = snapshot.get("session_mode")
    if session_mode == "camera":
        stored_origin = snapshot.get("started_at")
        if not isinstance(stored_origin, str):
            raise HTTPException(
                409, "A sessão de câmera não tem horário de origem registrado.",
            )
        try:
            normalized_stored = timestamp(stored_origin, 1, preserve_fraction=True)
        except ClinicalDataError as error:
            raise HTTPException(422, f"Origem da sessão inválida: {error}") from error
        if supplied_origin is not None:
            try:
                normalized_supplied = timestamp(supplied_origin, 1, preserve_fraction=True)
            except ClinicalDataError as error:
                raise HTTPException(422, f"session_origin_at inválido: {error}") from error
            if normalized_supplied != normalized_stored:
                raise HTTPException(
                    422, "A origem temporal da câmera é definida pelo servidor e não pode ser substituída.",
                )
        supplied_origin = normalized_stored
    elif supplied_origin is None and session_mode == "replay":
        raise HTTPException(
            422,
            "Para correlacionar FHIR com reprodução, informe session_origin_at: "
            "o horário de origem da linha do tempo do vídeo.",
        )
    elif supplied_origin is None:
        supplied_origin = snapshot.get("started_at")
    if not isinstance(supplied_origin, str):
        raise HTTPException(
            409,
            "A sessão não tem horário de origem; informe session_origin_at explicitamente.",
        )
    try:
        normalized = timestamp(supplied_origin, 1, preserve_fraction=True)
    except ClinicalDataError as error:
        raise HTTPException(422, f"session_origin_at inválido: {error}") from error
    return datetime.fromisoformat(normalized.replace("Z", "+00:00")), normalized


def _elapsed_at(
    recorded_at: str, origin: datetime, start_offset: float,
) -> float:
    event_time = datetime.fromisoformat(recorded_at.replace("Z", "+00:00"))
    if event_time < origin:
        raise HTTPException(
            422, "O Bundle contém eventos anteriores à origem da linha do tempo da sessão.",
        )
    elapsed = start_offset + (event_time - origin).total_seconds()
    return round(elapsed, 6)


def _stream_result(db, session_id: str) -> dict:
    rows = db.execute(
        "SELECT * FROM clinical_stream_samples WHERE session_id=? "
        "ORDER BY elapsed_seconds DESC,recorded_at DESC LIMIT 100",
        (session_id,),
    ).fetchall()
    incidents = [
        json.loads(row["payload"]) for row in db.execute(
            "SELECT payload FROM monitor_incidents WHERE session_id=?", (session_id,),
        )
    ]
    samples = []
    for row in rows:
        payload = json.loads(row["payload"])
        matches = []
        for incident in incidents:
            if incident["merged_into"] is not None or incident["status"] == "retracted":
                continue
            nearby = [
                evidence for evidence in incident["evidence"]
                if evidence["status"] != "retracted"
                and abs(evidence["timestamp"] - row["elapsed_seconds"]) <= 10
            ]
            if nearby:
                matches.append({
                    "id": incident["id"],
                    "timestamp": min(evidence["timestamp"] for evidence in nearby),
                    "modalities": sorted({evidence["source"] for evidence in nearby}),
                })
        events = json.loads(row["events"])
        for event in events:
            delivery_id = event.get("delivery_id")
            delivery = db.execute(
                "SELECT status,last_error,http_status,attempts,delivered_at "
                "FROM webhook_outbox WHERE id=?", (delivery_id,),
            ).fetchone() if delivery_id else None
            event["delivery"] = dict(delivery) if delivery else None
        samples.append({
            "sample_id": row["sample_id"],
            "source_id": row["source_id"],
            "recorded_at": row["recorded_at"],
            "elapsed_seconds": row["elapsed_seconds"],
            "vitals": payload["vitals"],
            "prescriptions": payload["prescriptions"],
            "events": events,
            "media_matches": matches,
        })
    return {"session_id": session_id, "samples": samples, "notice": NOTICE}


def _store_sample_in_transaction(
    db,
    session_id: str, source_id: str, sample_id: str, recorded_at: str,
    elapsed_seconds: float, vitals: dict, prescriptions: list[dict],
) -> tuple[dict, bool]:
    try:
        source_id = patient_ref(source_id, 1)
        normalized_at = timestamp(recorded_at, 1, preserve_fraction=True)
    except ClinicalDataError as error:
        raise HTTPException(422, str(error)) from error
    parsed_at = datetime.fromisoformat(normalized_at.replace("Z", "+00:00"))
    if parsed_at > datetime.now(timezone.utc) + timedelta(minutes=1):
        raise HTTPException(422, "recorded_at não pode estar mais de um minuto no futuro.")
    if not vitals and not prescriptions:
        raise HTTPException(422, "Informe ao menos um sinal vital ou uma prescrição.")

    payload = {
        "recorded_at": normalized_at,
        "elapsed_seconds": elapsed_seconds,
        "vitals": vitals,
        "prescriptions": prescriptions,
    }
    serialized = json.dumps(payload, ensure_ascii=False, allow_nan=False, sort_keys=True)
    _session(db, session_id, elapsed_seconds)
    existing = db.execute(
        "SELECT payload FROM clinical_stream_samples "
        "WHERE session_id=? AND source_id=? AND sample_id=?",
        (session_id, source_id, sample_id),
    ).fetchone()
    if existing:
        if existing["payload"] != serialized:
            raise HTTPException(409, "sample_id reutilizado com conteúdo diferente.")
        return _stream_result(db, session_id), False
    same_time = db.execute(
        "SELECT payload FROM clinical_stream_samples "
        "WHERE session_id=? AND source_id=? AND recorded_at=?",
        (session_id, source_id, normalized_at),
    ).fetchone()
    if same_time:
        if same_time["payload"] != serialized:
            raise HTTPException(
                409,
                "Envie uma amostra consolidada por fonte e instante; "
                "o horário já contém dados diferentes.",
            )
        return _stream_result(db, session_id), False

    latest = db.execute(
        "SELECT recorded_at,elapsed_seconds FROM clinical_stream_samples "
        "WHERE session_id=? AND source_id=? "
        "ORDER BY recorded_at DESC LIMIT 1",
        (session_id, source_id),
    ).fetchone()
    if latest and (
        normalized_at <= latest["recorded_at"]
        or elapsed_seconds < latest["elapsed_seconds"]
    ):
        raise HTTPException(409, "Amostras da mesma fonte devem avançar no tempo.")

    history_rows = db.execute(
        "SELECT payload FROM clinical_stream_samples "
        "WHERE session_id=? AND source_id=? ORDER BY recorded_at DESC LIMIT ?",
        (session_id, source_id, MAX_HISTORY),
    ).fetchall()
    history = [json.loads(row["payload"]) for row in reversed(history_rows)]
    events = []
    vital_history = [
        {"patient_id": source_id, "recorded_at": item["recorded_at"], **item["vitals"]}
        for item in history if item["vitals"]
    ]
    if vitals:
        current_vitals = {
            "patient_id": source_id, "recorded_at": normalized_at, **vitals,
        }
        try:
            vital_events = analyze_vitals(
                [*vital_history, current_vitals], {}, allow_partial=True,
            )["events"]
        except ClinicalDataError as error:
            raise HTTPException(422, str(error)) from error
        events.extend(
            {**event, "source": "vitals"}
            for event in vital_events
            if datetime.fromisoformat(
                event["recorded_at"].replace("Z", "+00:00")
            ) == parsed_at
        )

    prescription_history = [
        {
            "patient_id": source_id, "recorded_at": item["recorded_at"], **prescription,
        }
        for item in history for prescription in item["prescriptions"]
    ]
    if prescriptions:
        current_prescriptions = [
            {"patient_id": source_id, "recorded_at": normalized_at, **prescription}
            for prescription in prescriptions
        ]
        try:
            prescription_events = analyze_prescriptions(
                [*prescription_history, *current_prescriptions], {},
            )["events"]
        except ClinicalDataError as error:
            raise HTTPException(422, str(error)) from error
        events.extend(
            {**event, "source": "prescriptions"}
            for event in prescription_events
            if (
                datetime.fromisoformat(
                    event["recorded_at"].replace("Z", "+00:00")
                ) == parsed_at and event["kind"] != "started"
            )
        )

    for event in events:
        event["delivery_id"] = enqueue_clinical_event(
            db, session_id, event["source"], event,
        )
    db.execute(
        "INSERT INTO clinical_stream_samples "
        "(session_id,source_id,sample_id,recorded_at,elapsed_seconds,payload,events) "
        "VALUES (?,?,?,?,?,?,?)",
        (session_id, source_id, sample_id, normalized_at, elapsed_seconds,
         serialized, json.dumps(events, ensure_ascii=False, allow_nan=False)),
    )
    db.execute(
        "DELETE FROM clinical_stream_samples WHERE rowid IN ("
        "SELECT rowid FROM clinical_stream_samples WHERE session_id=? AND source_id=? "
        "ORDER BY recorded_at DESC LIMIT -1 OFFSET ?)",
        (session_id, source_id, MAX_HISTORY),
    )
    return _stream_result(db, session_id), True


def _store_sample(
    session_id: str, source_id: str, sample_id: str, recorded_at: str,
    elapsed_seconds: float, vitals: dict, prescriptions: list[dict],
) -> tuple[dict, bool]:
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        return _store_sample_in_transaction(
            db, session_id, source_id, sample_id, recorded_at,
            elapsed_seconds, vitals, prescriptions,
        )


@router.get("/configuration")
def configuration():
    token = os.getenv("CLINICAL_INGEST_BEARER_TOKEN", "").strip()
    configured = len(token) >= 32 and all(33 <= ord(char) <= 126 for char in token)
    return {
        "configured": configured,
        "message": (
            "Ingestão autenticada habilitada."
            if configured
            else "Configure CLINICAL_INGEST_BEARER_TOKEN com ao menos 32 caracteres no backend."
        ),
    }


@router.get("/{session_id}")
def get_stream(session_id: str):
    with connect() as db:
        if db.execute("SELECT id FROM monitor_sessions WHERE id=?", (session_id,)).fetchone() is None:
            raise HTTPException(404, "Sessão de mídia não encontrada.")
        return _stream_result(db, session_id)


@router.post("/{session_id}/samples", status_code=201)
async def ingest_sample(
    session_id: str, request: Request, response: Response,
    authorization: str | None = Header(default=None),
):
    _authorize(authorization)
    raw = await _json_body(request, MAX_SAMPLE_BYTES)
    try:
        sample = ClinicalSample.model_validate(raw)
    except ValidationError as error:
        raise HTTPException(422, "Amostra clínica fora do contrato de ingestão.") from error
    vitals = sample.vitals.model_dump(exclude_none=True) if sample.vitals else {}
    prescriptions = [item.model_dump() for item in sample.prescriptions]
    result, created = _store_sample(
        session_id, sample.source_id, str(sample.sample_id),
        sample.recorded_at.isoformat(), sample.elapsed_seconds, vitals, prescriptions,
    )
    if not created:
        response.status_code = 200
    return result


@router.post("/{session_id}/fhir-subscription", status_code=201)
async def ingest_fhir_subscription(
    session_id: str, source_id: str, request: Request, response: Response,
    session_origin_at: str | None = None,
    authorization: str | None = Header(default=None),
):
    _authorize(authorization)
    try:
        source_id = patient_ref(source_id, 1)
    except ClinicalDataError as error:
        raise HTTPException(422, str(error)) from error
    raw = await _json_body(request, MAX_BUNDLE_BYTES)
    try:
        samples, warnings = subscription_samples(raw, source_id)
    except FhirResponseError as error:
        raise HTTPException(422, str(error)) from error

    with connect() as db:
        row = db.execute(
            "SELECT snapshot FROM monitor_sessions WHERE id=?", (session_id,),
        ).fetchone()
    if row is None:
        raise HTTPException(404, "Sessão de mídia não encontrada.")
    snapshot = json.loads(row["snapshot"])
    if snapshot.get("closed"):
        raise HTTPException(409, "A sessão de monitoramento está encerrada.")
    origin, normalized_origin = _session_origin(snapshot, session_origin_at)
    start_offset = float(snapshot.get("start", 0))

    mapped_samples = []
    for item in samples:
        resource_ids = ",".join(item["resource_ids"])
        sample_id = str(uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"fhir:{session_id}:{source_id}:{item['recorded_at']}:{resource_ids}",
        ))
        elapsed = _elapsed_at(item["recorded_at"], origin, start_offset)
        mapped_samples.append((item, sample_id, elapsed))
    mapped_samples.sort(
        key=lambda mapped: datetime.fromisoformat(
            mapped[0]["recorded_at"].replace("Z", "+00:00")
        )
    )

    created = False
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        for item, sample_id, elapsed in mapped_samples:
            _, inserted = _store_sample_in_transaction(
                db, session_id, source_id, sample_id, item["recorded_at"], elapsed,
                item["vitals"], item["prescriptions"],
            )
            created = created or inserted
    if not created:
        response.status_code = 200
    result = get_stream(session_id)
    result["warnings"] = warnings
    result["session_origin_at"] = normalized_origin
    return result
