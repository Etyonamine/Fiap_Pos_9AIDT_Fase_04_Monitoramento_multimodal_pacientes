"""Synthetic, explicitly session-bound demonstration; not a clinical integration."""

import ipaddress
import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Literal

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.database import connect
from app.services.audio_analysis import critical_terms
from app.services.clinical_data import (
    analyze_prescriptions, analyze_vitals, note_events, note_evolution,
)

router = APIRouter(prefix="/api/synthetic-stream", tags=["synthetic stream"])
NOTICE = "Simulação sintética para revisão; não é diagnóstico nem comunicação com equipe."


class SampleRequest(BaseModel):
    sample_id: uuid.UUID
    timestamp: float = Field(ge=0, le=1800, allow_inf_nan=False)
    scenario: Literal["stable", "change"]
    note: str | None = Field(default=None, max_length=1200)


class SyntheticReceipt(BaseModel):
    event_id: uuid.UUID
    category: Literal["synthetic_review"]


@router.post("/receiver", status_code=202)
def receive_synthetic_alert(receipt: SyntheticReceipt, request: Request):
    try:
        local = request.client is not None and ipaddress.ip_address(request.client.host).is_loopback
    except ValueError:
        local = False
    if not local:
        raise HTTPException(403, "O receptor sintético aceita somente conexões locais.")
    with connect() as db:
        db.execute(
            "INSERT OR IGNORE INTO synthetic_stream_receipts VALUES (?,?)",
            (str(receipt.event_id), datetime.now(timezone.utc).isoformat()),
        )
    return {"accepted": True, "notice": NOTICE}


def _session(db, session_id: str) -> dict:
    row = db.execute("SELECT snapshot FROM monitor_sessions WHERE id=?", (session_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "Sessão de vídeo ou câmera não encontrada.")
    return json.loads(row["snapshot"])


def _client() -> httpx.Client:
    return httpx.Client(timeout=3, trust_env=False, follow_redirects=False)


def _local_port(request: Request) -> int:
    server = request.scope.get("server")
    if not server or not isinstance(server[1], int) or not 1 <= server[1] <= 65535:
        raise HTTPException(503, "Porta local do receptor sintético indisponível.")
    return server[1]


def _deliver(session_id: str, sample_id: str, port: int):
    url = f"http://127.0.0.1:{port}/api/synthetic-stream/receiver"
    event_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"synthetic:{session_id}:{sample_id}"))
    try:
        with _client() as client:
            response = client.post(url, json={"event_id": event_id, "category": "synthetic_review"})
            response.raise_for_status()
            payload = response.json()
            if response.status_code != 202 or not isinstance(payload, dict) or payload.get("accepted") is not True:
                raise ValueError("Resposta inválida do receptor sintético.")
    except (httpx.HTTPError, ValueError) as error:
        with connect() as db:
            db.execute(
                "UPDATE synthetic_stream_deliveries SET status='failed',error=? "
                "WHERE session_id=? AND sample_id=?",
                (f"Falha no receptor sintético local: {type(error).__name__}", session_id, sample_id),
            )
        return
    with connect() as db:
        db.execute(
            "UPDATE synthetic_stream_deliveries SET status='delivered',error=NULL "
            "WHERE session_id=? AND sample_id=?",
            (session_id, sample_id),
        )


def _result(db, session_id: str) -> dict:
    _session(db, session_id)
    rows = db.execute(
        "SELECT s.*,d.status AS delivery_status,d.error AS delivery_error "
        "FROM synthetic_stream_samples s LEFT JOIN synthetic_stream_deliveries d "
        "ON d.session_id=s.session_id AND d.sample_id=s.sample_id "
        "WHERE s.session_id=? ORDER BY s.timestamp DESC LIMIT 100",
        (session_id,),
    ).fetchall()
    incidents = [
        json.loads(row["payload"]) for row in db.execute(
            "SELECT payload FROM monitor_incidents WHERE session_id=?", (session_id,),
        )
    ]
    samples = []
    for row in rows:
        matches = []
        for item in incidents:
            if item["merged_into"] is not None or item["status"] == "retracted":
                continue
            nearby = [
                evidence for evidence in item["evidence"]
                if evidence["status"] != "retracted"
                and abs(evidence["timestamp"] - row["timestamp"]) <= 10
            ]
            if nearby:
                matches.append({
                    "id": item["id"], "timestamp": min(evidence["timestamp"] for evidence in nearby),
                    "modalities": sorted({evidence["source"] for evidence in nearby}),
                })
        samples.append({
            "sample_id": row["sample_id"], "timestamp": row["timestamp"],
            "scenario": row["scenario"], "values": json.loads(row["payload"]),
            "events": json.loads(row["events"]), "media_matches": matches,
            "delivery_status": row["delivery_status"], "delivery_error": row["delivery_error"],
        })
    return {"session_id": session_id, "samples": samples, "notice": NOTICE}


@router.get("/{session_id}")
def get_stream(session_id: str):
    with connect() as db:
        return _result(db, session_id)


@router.post("/{session_id}/samples", status_code=201)
def add_sample(session_id: str, sample: SampleRequest, request: Request):
    port = _local_port(request)
    sample_id = str(sample.sample_id)
    created = False
    supplied_note = sample.note.strip() if sample.note is not None else None
    if supplied_note == "":
        raise HTTPException(422, "A nota sintética opcional não pode ficar vazia.")
    note_signature = (
        hashlib.sha256(supplied_note.encode("utf-8")).hexdigest()
        if supplied_note is not None else None
    )
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        snapshot = _session(db, session_id)
        previous = db.execute(
            "SELECT * FROM synthetic_stream_samples WHERE session_id=? ORDER BY timestamp DESC LIMIT 1",
            (session_id,),
        ).fetchone()
        existing = db.execute(
            "SELECT * FROM synthetic_stream_samples WHERE session_id=? AND sample_id=?",
            (session_id, sample_id),
        ).fetchone()
        if existing:
            existing_values = json.loads(existing["payload"])
            if (
                existing["timestamp"] != sample.timestamp
                or existing["scenario"] != sample.scenario
                or existing_values.get("note_signature") != note_signature
            ):
                raise HTTPException(409, "Identificador de amostra reutilizado com dados diferentes.")
        else:
            if snapshot.get("closed"):
                raise HTTPException(409, "A sessão de monitoramento está encerrada.")
            elapsed = snapshot.get("elapsed", snapshot.get("analyzed_until", 0))
            if sample.timestamp > elapsed + 1:
                raise HTTPException(422, "A amostra está além do tempo analisado da sessão.")
            count = db.execute(
                "SELECT count(*) FROM synthetic_stream_samples WHERE session_id=?", (session_id,),
            ).fetchone()[0]
            if count >= 1000:
                raise HTTPException(409, "Limite de 1000 amostras sintéticas por sessão.")
            if previous and sample.timestamp - previous["timestamp"] < 1:
                raise HTTPException(409, "Amostras devem avançar ao menos um segundo.")
            changed = previous is not None and sample.scenario == "change"
            recorded_at = (datetime(2020, 1, 1, tzinfo=timezone.utc)
                           + timedelta(seconds=sample.timestamp)).isoformat()
            previous_values = json.loads(previous["payload"]) if previous else {}
            values = {
                "patient_id": "synthetic-case", "recorded_at": recorded_at,
                "heart_rate_bpm": 132 if changed else 78,
                "systolic_mmhg": 120, "diastolic_mmhg": 80,
                "spo2_percent": 88 if changed else 97,
                "medication": "Medicamento sintético", "dose": 30 if changed else 10,
                "unit": "mg", "status": "active",
                "expected_regimen": {"dose": 10, "unit": "mg", "status": "active"},
                "synthetic_note": (
                    "Pessoa sintética relata cansaço." if changed else
                    "Pessoa sintética relata bem-estar."
                ),
            }
            previous_mentions = previous_values.get("note_mentions")
            if previous_mentions is None and previous_values.get("synthetic_note"):
                previous_mentions = critical_terms(previous_values["synthetic_note"])
            current_note = supplied_note or values["synthetic_note"]
            current_mentions = critical_terms(current_note)
            values["note_mentions"] = [
                {
                    "term": mention["term"],
                    "severity": mention["severity"],
                    "negated": mention["negated"],
                }
                for mention in current_mentions
            ]
            values["note_evolution"] = note_evolution(previous_mentions or [], current_mentions)
            if supplied_note is not None:
                values.pop("synthetic_note")
                values["custom_note"] = True
                values["note_signature"] = note_signature
            records = ([json.loads(previous["payload"])] if previous else []) + [values]
            vital_events = analyze_vitals(records, {})["events"]
            prescription_events = analyze_prescriptions(records, {})["events"]
            current_at = values["recorded_at"].replace("+00:00", "Z")
            current_at = current_at.split(".")[0] + "Z" if "." in current_at else current_at
            events = [
                event for event in vital_events + prescription_events
                if event["recorded_at"] == current_at and event["kind"] != "started"
            ]
            introduced = {
                mention["term"] for mention in values["note_evolution"]["introduced"]
            }
            events.extend(note_events(
                "", "caso-001", current_at,
                [
                    {**mention, "offset": 0, "end_offset": 0, "context": ""}
                    for mention in values["note_mentions"]
                    if mention["term"] in introduced
                ],
            ))
            for transition in ("persisted", "resolved"):
                if transition == "persisted" and supplied_note is None:
                    continue
                events.extend(
                    {
                        "recorded_at": current_at, "patient_ref": "caso-001",
                        "kind": f"text_{transition}", "field": mention["term"],
                        "message": (
                            f"Menção textual {('mantida' if transition == 'persisted' else 'não observada')}: "
                            f"{mention['term']}."
                        ),
                        "priority": "information",
                    }
                    for mention in values["note_evolution"][transition]
                )
            db.execute(
                "INSERT INTO synthetic_stream_samples VALUES (?,?,?,?,?,?)",
                (session_id, sample_id, sample.timestamp, sample.scenario,
                 json.dumps(values), json.dumps(events, ensure_ascii=False)),
            )
            if any(event["priority"] == "review" for event in events):
                db.execute(
                    "INSERT INTO synthetic_stream_deliveries VALUES (?,?,'sending',NULL)",
                    (session_id, sample_id),
                )
                created = True
    if created:
        _deliver(session_id, sample_id, port)
    with connect() as db:
        return _result(db, session_id)


@router.post("/{session_id}/samples/{sample_id}/retry")
def retry_delivery(session_id: str, sample_id: uuid.UUID, request: Request):
    port = _local_port(request)
    with connect() as db:
        changed = db.execute(
            "UPDATE synthetic_stream_deliveries SET status='sending',error=NULL "
            "WHERE session_id=? AND sample_id=? AND status='failed'",
            (session_id, str(sample_id)),
        ).rowcount
        if not changed:
            raise HTTPException(409, "Entrega sintética não encontrada ou não está em falha.")
    _deliver(session_id, str(sample_id), port)
    with connect() as db:
        return _result(db, session_id)
