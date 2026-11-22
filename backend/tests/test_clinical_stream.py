import json
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import database
from app.routers import clinical_stream
from app.services import webhook_notifications

TOKEN = "test-clinical-ingest-token-0123456789"
SESSION_ID = "media-session"
SOURCE_ID = "case-001"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATA_DIR", tmp_path)
    monkeypatch.setenv("CLINICAL_INGEST_BEARER_TOKEN", TOKEN)
    monkeypatch.setenv("ALERT_WEBHOOK_ENABLED", "false")
    database.initialize()
    with database.connect() as db:
        db.execute(
            "INSERT INTO monitor_sessions (id,video_id,snapshot) VALUES (?,?,?)",
            (SESSION_ID, "video-1", json.dumps({
                "elapsed": 20,
                "closed": False,
                "session_mode": "camera",
                "started_at": (
                    datetime.now(timezone.utc) - timedelta(seconds=5)
                ).isoformat(),
            })),
        )
    app = FastAPI()
    app.include_router(clinical_stream.router)
    with TestClient(app) as test_client:
        yield test_client


def headers(token=TOKEN):
    return {"Authorization": f"Bearer {token}"}


def sample(sample_id, recorded_at, elapsed, *, heart_rate=78, spo2=97, dose=10):
    return {
        "sample_id": str(sample_id),
        "source_id": SOURCE_ID,
        "recorded_at": recorded_at,
        "elapsed_seconds": elapsed,
        "vitals": {"heart_rate_bpm": heart_rate, "spo2_percent": spo2},
        "prescriptions": [{
            "medication": "medicine-opaque",
            "dose": dose,
            "unit": "mg",
            "status": "active",
        }],
    }


def test_stream_requires_configured_bearer_and_validates_session(client, monkeypatch):
    response = client.post(
        f"/api/clinical-stream/{SESSION_ID}/samples", json={},
    )
    assert response.status_code == 401
    response = client.post(
        f"/api/clinical-stream/{SESSION_ID}/samples",
        json={}, headers=headers("wrong-token"),
    )
    assert response.status_code == 401

    monkeypatch.delenv("CLINICAL_INGEST_BEARER_TOKEN")
    response = client.post(
        f"/api/clinical-stream/{SESSION_ID}/samples", json={}, headers=headers(),
    )
    assert response.status_code == 503


@pytest.mark.parametrize(("body", "status"), [
    (b"{", 422),
    (b"[]", 422),
    (b"x" * (clinical_stream.MAX_SAMPLE_BYTES + 1), 413),
])
def test_stream_rejects_malformed_non_object_and_oversized_json(client, body, status):
    response = client.post(
        f"/api/clinical-stream/{SESSION_ID}/samples",
        content=body,
        headers={**headers(), "Content-Type": "application/json"},
    )
    assert response.status_code == status


def test_stream_rejects_empty_clinical_sample(client):
    response = client.post(
        f"/api/clinical-stream/{SESSION_ID}/samples",
        json={
            "sample_id": str(uuid.uuid4()),
            "source_id": SOURCE_ID,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "elapsed_seconds": 1,
            "vitals": {},
            "prescriptions": [],
        },
        headers=headers(),
    )
    assert response.status_code == 422
    assert "ao menos um sinal vital" in response.json()["detail"]


def test_stream_detects_vital_and_prescription_changes_and_is_idempotent(client, monkeypatch):
    monkeypatch.setenv("ALERT_WEBHOOK_ENABLED", "true")
    start = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(minutes=5)
    first = sample(uuid.uuid4(), start.isoformat(), 1)
    second = sample(
        uuid.uuid4(), (start + timedelta(minutes=5)).isoformat(),
        2, heart_rate=132, spo2=88, dose=30,
    )

    initial = client.post(
        f"/api/clinical-stream/{SESSION_ID}/samples", json=first, headers=headers(),
    )
    assert initial.status_code == 201
    assert initial.json()["samples"][0]["events"] == []

    changed = client.post(
        f"/api/clinical-stream/{SESSION_ID}/samples", json=second, headers=headers(),
    )
    assert changed.status_code == 201
    events = changed.json()["samples"][0]["events"]
    assert {event["source"] for event in events} == {"vitals", "prescriptions"}
    assert {event["kind"] for event in events} >= {"threshold_crossing", "regimen_changed"}
    assert all(event["delivery_id"] for event in events)

    repeated = client.post(
        f"/api/clinical-stream/{SESSION_ID}/samples", json=second, headers=headers(),
    )
    assert repeated.status_code == 200
    with database.connect() as db:
        assert db.execute("SELECT count(*) FROM clinical_stream_samples").fetchone()[0] == 2
        assert db.execute("SELECT count(*) FROM webhook_outbox").fetchone()[0] == len(events)


def test_stream_rejects_bad_values_future_clock_and_out_of_order_samples(client):
    now = datetime.now(timezone.utc)
    invalid = sample(uuid.uuid4(), now.isoformat(), 1, heart_rate=500)
    response = client.post(
        f"/api/clinical-stream/{SESSION_ID}/samples", json=invalid, headers=headers(),
    )
    assert response.status_code == 422

    invalid_boolean = sample(uuid.uuid4(), now.isoformat(), 1, heart_rate=True)
    assert client.post(
        f"/api/clinical-stream/{SESSION_ID}/samples",
        json=invalid_boolean, headers=headers(),
    ).status_code == 422

    invalid_elapsed = sample(uuid.uuid4(), now.isoformat(), True)
    assert client.post(
        f"/api/clinical-stream/{SESSION_ID}/samples",
        json=invalid_elapsed, headers=headers(),
    ).status_code == 422

    invalid_dose = sample(uuid.uuid4(), now.isoformat(), 1)
    invalid_dose["prescriptions"][0]["dose"] = True
    assert client.post(
        f"/api/clinical-stream/{SESSION_ID}/samples",
        json=invalid_dose, headers=headers(),
    ).status_code == 422

    future = sample(
        uuid.uuid4(), (now + timedelta(minutes=2)).isoformat(), 1,
    )
    assert client.post(
        f"/api/clinical-stream/{SESSION_ID}/samples", json=future, headers=headers(),
    ).status_code == 422

    first = sample(uuid.uuid4(), now.isoformat(), 1)
    assert client.post(
        f"/api/clinical-stream/{SESSION_ID}/samples", json=first, headers=headers(),
    ).status_code == 201
    older = sample(
        uuid.uuid4(), (now - timedelta(seconds=1)).isoformat(), 2,
    )
    assert client.post(
        f"/api/clinical-stream/{SESSION_ID}/samples", json=older, headers=headers(),
    ).status_code == 409


def test_stream_requires_active_session_and_pseudonymous_source_id(client):
    now = datetime.now(timezone.utc).isoformat()
    invalid_source = sample(uuid.uuid4(), now, 1)
    invalid_source["source_id"] = "Patient Name"
    assert client.post(
        f"/api/clinical-stream/{SESSION_ID}/samples",
        json=invalid_source, headers=headers(),
    ).status_code == 422

    assert client.post(
        "/api/clinical-stream/unknown-session/samples",
        json=sample(uuid.uuid4(), now, 1), headers=headers(),
    ).status_code == 404

    with database.connect() as db:
        db.execute(
            "UPDATE monitor_sessions SET snapshot=? WHERE id=?",
            (json.dumps({"elapsed": 20, "closed": True}), SESSION_ID),
        )
    assert client.post(
        f"/api/clinical-stream/{SESSION_ID}/samples",
        json=sample(uuid.uuid4(), now, 1), headers=headers(),
    ).status_code == 409


def test_fhir_subscription_bundle_ingests_observations_and_orders(client):
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    bundle = {
        "resourceType": "Bundle",
        "type": "collection",
        "entry": [
            {"resource": {
                "resourceType": "Observation", "id": "hr-1", "status": "final",
                "subject": {"reference": f"Patient/{SOURCE_ID}"},
                "effectiveDateTime": now,
                "code": {"coding": [{"system": "http://loinc.org", "code": "8867-4"}]},
                "valueQuantity": {
                    "value": 132, "system": "http://unitsofmeasure.org", "code": "/min",
                },
            }},
            {"resource": {
                "resourceType": "Observation", "id": "spo2-1", "status": "final",
                "subject": {"reference": f"Patient/{SOURCE_ID}"},
                "effectiveDateTime": now,
                "code": {"coding": [{"system": "http://loinc.org", "code": "59408-5"}]},
                "valueQuantity": {
                    "value": 88, "system": "http://unitsofmeasure.org", "code": "%",
                },
            }},
            {"resource": {
                "resourceType": "MedicationRequest", "id": "med-1", "status": "active",
                "subject": {"reference": f"Patient/{SOURCE_ID}"},
                "authoredOn": now,
                "medicationCodeableConcept": {"text": "medicine-opaque"},
                "dosageInstruction": [{
                    "doseAndRate": [{
                        "doseQuantity": {
                            "value": 10, "system": "http://unitsofmeasure.org",
                            "code": "mg", "unit": "mg",
                        },
                    }],
                }],
            }},
        ],
    }
    response = client.post(
        f"/api/clinical-stream/{SESSION_ID}/fhir-subscription",
        params={"source_id": SOURCE_ID},
        json=bundle,
        headers=headers(),
    )
    assert response.status_code == 201
    sample_result = response.json()["samples"][0]
    assert sample_result["vitals"] == {"heart_rate_bpm": 132, "spo2_percent": 88}
    assert len(sample_result["prescriptions"]) == 1
    assert {event["field"] for event in sample_result["events"]} == {
        "heart_rate_bpm", "spo2_percent",
    }
    assert client.post(
        f"/api/clinical-stream/{SESSION_ID}/fhir-subscription",
        params={"source_id": SOURCE_ID},
        json=bundle,
        headers=headers(),
    ).status_code == 200
    assert client.get(f"/api/clinical-stream/{SESSION_ID}").json()["samples"]


def test_fhir_subscription_maps_recorded_at_to_media_elapsed(client):
    origin = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(seconds=50)
    with database.connect() as db:
        db.execute(
            "UPDATE monitor_sessions SET snapshot=? WHERE id=?",
            (json.dumps({
                "elapsed": 50, "closed": False, "session_mode": "camera",
                "started_at": origin.isoformat(),
            }), SESSION_ID),
        )
        for incident_id, elapsed in (("incident-12", 12), ("incident-39", 39)):
            payload = {
                "id": incident_id,
                "merged_into": None,
                "status": "confirmed",
                "evidence": [{
                    "status": "confirmed", "timestamp": elapsed, "source": "image",
                }],
            }
            db.execute(
                "INSERT INTO monitor_incidents (id,session_id,payload) VALUES (?,?,?)",
                (incident_id, SESSION_ID, json.dumps(payload)),
            )

    def observation(resource_id, elapsed, heart_rate):
        return {"resource": {
            "resourceType": "Observation",
            "id": resource_id,
            "status": "final",
            "subject": {"reference": f"Patient/{SOURCE_ID}"},
            "effectiveDateTime": (origin + timedelta(seconds=elapsed)).isoformat(),
            "code": {"coding": [{"system": "http://loinc.org", "code": "8867-4"}]},
            "valueQuantity": {
                "value": heart_rate,
                "system": "http://unitsofmeasure.org",
                "code": "/min",
            },
        }}

    response = client.post(
        f"/api/clinical-stream/{SESSION_ID}/fhir-subscription",
        params={"source_id": SOURCE_ID},
        json={
            "resourceType": "Bundle",
            "type": "collection",
            "entry": [observation("hr-12", 12, 78), observation("hr-39", 39, 80)],
        },
        headers=headers(),
    )
    assert response.status_code == 201
    samples = response.json()["samples"]
    assert {item["elapsed_seconds"] for item in samples} == {12, 39}
    matches = {
        item["elapsed_seconds"]: {match["id"] for match in item["media_matches"]}
        for item in samples
    }
    assert matches == {12: {"incident-12"}, 39: {"incident-39"}}


def test_fhir_replay_requires_and_applies_explicit_timeline_origin(client):
    origin = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(seconds=20)
    with database.connect() as db:
        db.execute(
            "UPDATE monitor_sessions SET snapshot=? WHERE id=?",
            (json.dumps({
                "elapsed": 40, "analyzed_until": 40, "closed": False,
                "session_mode": "replay", "started_at": origin.isoformat(), "start": 10,
            }), SESSION_ID),
        )
    bundle = {
        "resourceType": "Bundle",
        "type": "collection",
        "entry": [{"resource": {
            "resourceType": "Observation",
            "id": "hr-replay",
            "status": "final",
            "subject": {"reference": f"Patient/{SOURCE_ID}"},
            "effectiveDateTime": (origin + timedelta(seconds=20)).isoformat(),
            "code": {"coding": [{"system": "http://loinc.org", "code": "8867-4"}]},
            "valueQuantity": {
                "value": 78, "system": "http://unitsofmeasure.org", "code": "/min",
            },
        }}],
    }

    url = f"/api/clinical-stream/{SESSION_ID}/fhir-subscription"
    response = client.post(
        url, params={"source_id": SOURCE_ID}, json=bundle, headers=headers(),
    )
    assert response.status_code == 422
    assert "session_origin_at" in response.json()["detail"]

    response = client.post(
        url,
        params={"source_id": SOURCE_ID, "session_origin_at": origin.isoformat()},
        json=bundle,
        headers=headers(),
    )
    assert response.status_code == 201
    assert response.json()["samples"][0]["elapsed_seconds"] == 30


def test_fhir_replay_rejects_events_before_source_origin_even_with_start_offset(client):
    origin = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(seconds=20)
    with database.connect() as db:
        db.execute(
            "UPDATE monitor_sessions SET snapshot=? WHERE id=?",
            (json.dumps({
                "elapsed": 40, "analyzed_until": 40, "closed": False,
                "session_mode": "replay", "start": 10,
            }), SESSION_ID),
        )
    bundle = {
        "resourceType": "Bundle",
        "type": "collection",
        "entry": [{"resource": {
            "resourceType": "Observation",
            "id": "hr-before-origin",
            "status": "final",
            "subject": {"reference": f"Patient/{SOURCE_ID}"},
            "effectiveDateTime": (origin - timedelta(seconds=5)).isoformat(),
            "code": {"coding": [{"system": "http://loinc.org", "code": "8867-4"}]},
            "valueQuantity": {
                "value": 78, "system": "http://unitsofmeasure.org", "code": "/min",
            },
        }}],
    }

    response = client.post(
        f"/api/clinical-stream/{SESSION_ID}/fhir-subscription",
        params={
            "source_id": SOURCE_ID,
            "session_origin_at": origin.isoformat(),
        },
        json=bundle,
        headers=headers(),
    )

    assert response.status_code == 422
    assert "anteriores à origem" in response.json()["detail"]
    assert client.get(f"/api/clinical-stream/{SESSION_ID}").json()["samples"] == []


def test_fhir_camera_origin_cannot_be_overridden(client):
    origin = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(seconds=20)
    with database.connect() as db:
        db.execute(
            "UPDATE monitor_sessions SET snapshot=? WHERE id=?",
            (json.dumps({
                "elapsed": 20, "closed": False, "session_mode": "camera",
                "started_at": origin.isoformat(),
            }), SESSION_ID),
        )
    bundle = {
        "resourceType": "Bundle",
        "type": "collection",
        "entry": [{"resource": {
            "resourceType": "Observation",
            "id": "hr-camera-origin",
            "status": "final",
            "subject": {"reference": f"Patient/{SOURCE_ID}"},
            "effectiveDateTime": (origin + timedelta(seconds=5)).isoformat(),
            "code": {"coding": [{"system": "http://loinc.org", "code": "8867-4"}]},
            "valueQuantity": {
                "value": 78, "system": "http://unitsofmeasure.org", "code": "/min",
            },
        }}],
    }

    url = f"/api/clinical-stream/{SESSION_ID}/fhir-subscription"
    invalid_origin = client.post(
        url,
        params={"source_id": SOURCE_ID, "session_origin_at": "not-a-timestamp"},
        json=bundle,
        headers=headers(),
    )
    assert invalid_origin.status_code == 422
    assert "session_origin_at inválido" in invalid_origin.json()["detail"]

    replaced_origin = client.post(
        url,
        params={
            "source_id": SOURCE_ID,
            "session_origin_at": (origin + timedelta(seconds=1)).isoformat(),
        },
        json=bundle,
        headers=headers(),
    )
    assert replaced_origin.status_code == 422
    assert "não pode ser substituída" in replaced_origin.json()["detail"]
    assert client.get(f"/api/clinical-stream/{SESSION_ID}").json()["samples"] == []


def test_fhir_bundle_rejection_rolls_back_every_sample_and_notification(client):
    origin = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(seconds=100)
    with database.connect() as db:
        db.execute(
            "UPDATE monitor_sessions SET snapshot=? WHERE id=?",
            (json.dumps({
                "elapsed": 10, "closed": False, "session_mode": "camera",
                "started_at": origin.isoformat(),
            }), SESSION_ID),
        )

    def observation(resource_id, elapsed):
        return {"resource": {
            "resourceType": "Observation",
            "id": resource_id,
            "status": "final",
            "subject": {"reference": f"Patient/{SOURCE_ID}"},
            "effectiveDateTime": (origin + timedelta(seconds=elapsed)).isoformat(),
            "code": {"coding": [{"system": "http://loinc.org", "code": "8867-4"}]},
            "valueQuantity": {
                "value": 132, "system": "http://unitsofmeasure.org", "code": "/min",
            },
        }}

    response = client.post(
        f"/api/clinical-stream/{SESSION_ID}/fhir-subscription",
        params={"source_id": SOURCE_ID},
        json={
            "resourceType": "Bundle",
            "type": "collection",
            "entry": [observation("hr-valid", 5), observation("hr-beyond-clock", 25)],
        },
        headers=headers(),
    )

    assert response.status_code == 422
    assert "além do relógio" in response.json()["detail"]
    assert client.get(f"/api/clinical-stream/{SESSION_ID}").json()["samples"] == []
    with database.connect() as db:
        assert db.execute(
            "SELECT count(*) FROM webhook_outbox",
        ).fetchone()[0] == 0


def test_fhir_requires_a_valid_timeline_origin_and_rejects_pre_origin_events(client):
    now = datetime.now(timezone.utc).replace(microsecond=0)
    bundle = {
        "resourceType": "Bundle",
        "type": "collection",
        "entry": [{"resource": {
            "resourceType": "Observation",
            "id": "hr-origin",
            "status": "final",
            "subject": {"reference": f"Patient/{SOURCE_ID}"},
            "effectiveDateTime": now.isoformat(),
            "code": {"coding": [{"system": "http://loinc.org", "code": "8867-4"}]},
            "valueQuantity": {
                "value": 78, "system": "http://unitsofmeasure.org", "code": "/min",
            },
        }}],
    }
    url = f"/api/clinical-stream/{SESSION_ID}/fhir-subscription"
    params = {"source_id": SOURCE_ID}

    with database.connect() as db:
        db.execute(
            "UPDATE monitor_sessions SET snapshot=? WHERE id=?",
            (json.dumps({"elapsed": 20, "closed": False, "session_mode": "camera"}), SESSION_ID),
        )
    missing_origin = client.post(url, params=params, json=bundle, headers=headers())
    assert missing_origin.status_code == 409

    with database.connect() as db:
        db.execute(
            "UPDATE monitor_sessions SET snapshot=? WHERE id=?",
            (json.dumps({
                "elapsed": 20, "closed": False, "session_mode": "camera",
                "started_at": "not-a-timestamp",
            }), SESSION_ID),
        )
    invalid_origin = client.post(url, params=params, json=bundle, headers=headers())
    assert invalid_origin.status_code == 422

    future_origin = now + timedelta(seconds=5)
    with database.connect() as db:
        db.execute(
            "UPDATE monitor_sessions SET snapshot=? WHERE id=?",
            (json.dumps({
                "elapsed": 20, "closed": False, "session_mode": "camera",
                "started_at": future_origin.isoformat(),
            }), SESSION_ID),
        )
    before_origin = client.post(url, params=params, json=bundle, headers=headers())
    assert before_origin.status_code == 422
    assert "anteriores à origem" in before_origin.json()["detail"]


def test_fhir_mapping_remains_within_analyzed_media_clock(client):
    origin = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(seconds=20)
    with database.connect() as db:
        db.execute(
            "UPDATE monitor_sessions SET snapshot=? WHERE id=?",
            (json.dumps({
                "elapsed": 1, "closed": False, "session_mode": "camera",
                "started_at": origin.isoformat(),
            }), SESSION_ID),
        )
    bundle = {
        "resourceType": "Bundle",
        "type": "collection",
        "entry": [{"resource": {
            "resourceType": "Observation",
            "id": "hr-too-far-ahead",
            "status": "final",
            "subject": {"reference": f"Patient/{SOURCE_ID}"},
            "effectiveDateTime": (origin + timedelta(seconds=20)).isoformat(),
            "code": {"coding": [{"system": "http://loinc.org", "code": "8867-4"}]},
            "valueQuantity": {
                "value": 78, "system": "http://unitsofmeasure.org", "code": "/min",
            },
        }}],
    }
    response = client.post(
        f"/api/clinical-stream/{SESSION_ID}/fhir-subscription",
        params={"source_id": SOURCE_ID},
        json=bundle,
        headers=headers(),
    )
    assert response.status_code == 422
    assert "além do relógio" in response.json()["detail"]


def test_fhir_subscription_rejects_wrong_subject_and_invalid_bundle(client):
    response = client.post(
        f"/api/clinical-stream/{SESSION_ID}/fhir-subscription",
        params={"source_id": SOURCE_ID},
        json={"resourceType": "Bundle", "type": "searchset", "entry": []},
        headers=headers(),
    )
    assert response.status_code == 422

    bundle = {
        "resourceType": "Bundle", "type": "collection",
        "entry": [{"resource": {
            "resourceType": "Observation", "id": "hr-1", "status": "final",
            "subject": {"reference": "Patient/someone-else"},
            "effectiveDateTime": datetime.now(timezone.utc).isoformat(),
            "code": {"coding": [{"system": "http://loinc.org", "code": "8867-4"}]},
            "valueQuantity": {
                "value": 132, "system": "http://unitsofmeasure.org", "code": "/min",
            },
        }}],
    }
    response = client.post(
        f"/api/clinical-stream/{SESSION_ID}/fhir-subscription",
        params={"source_id": SOURCE_ID}, json=bundle, headers=headers(),
    )
    assert response.status_code == 422
