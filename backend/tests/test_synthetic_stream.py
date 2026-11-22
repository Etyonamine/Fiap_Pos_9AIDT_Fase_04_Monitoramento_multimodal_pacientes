import json
import uuid

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import database
from app.routers import synthetic_stream


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATA_DIR", tmp_path)
    database.initialize()
    app = FastAPI()
    app.include_router(synthetic_stream.router)
    with database.connect() as db:
        db.execute(
            "INSERT INTO monitor_sessions VALUES (?,?,?)",
            ("session-one", "video-one", json.dumps({"closed": False, "elapsed": 30})),
        )
        db.execute(
            "INSERT INTO monitor_sessions VALUES (?,?,?)",
            ("session-two", "video-two", json.dumps({"closed": False, "elapsed": 30})),
        )
        db.execute(
            "INSERT INTO monitor_incidents (id,session_id,payload) VALUES (?,?,?)",
            ("incident-1", "session-one", json.dumps({
                "id": "incident-1", "timestamp": 10, "modalities": ["audio", "image"],
                "status": "confirmed", "merged_into": None,
                "evidence": [
                    {"source": "image", "timestamp": 10, "status": "confirmed"},
                    {"source": "audio", "timestamp": 10, "status": "confirmed"},
                ],
            })),
        )
    with TestClient(app, base_url="http://127.0.0.1:8000", client=("127.0.0.1", 50000)) as test_client:
        yield test_client


def sample(client, session="session-one", *, timestamp=0, scenario="stable", sample_id=None):
    return client.post(
        f"/api/synthetic-stream/{session}/samples",
        json={"sample_id": sample_id or str(uuid.uuid4()), "timestamp": timestamp, "scenario": scenario},
    )


def test_stream_correlates_same_session_and_notifies_local_receiver(client, monkeypatch):
    requests = []

    def transport(request):
        requests.append(json.loads(request.content))
        response = client.post("/api/synthetic-stream/receiver", json=requests[-1])
        return httpx.Response(response.status_code, json=response.json())

    monkeypatch.setattr(
        synthetic_stream, "_client", lambda: httpx.Client(transport=httpx.MockTransport(transport)),
    )
    first = sample(client)
    assert first.status_code == 201
    assert first.json()["samples"][0]["events"] == []
    identifier = str(uuid.uuid4())
    second = sample(client, timestamp=10, scenario="change", sample_id=identifier)
    assert second.status_code == 201
    current = second.json()["samples"][0]
    assert {event["kind"] for event in current["events"]} >= {
        "threshold_crossing", "rapid_change", "regimen_changed", "text_mention",
    }
    assert current["values"]["synthetic_note"] == "Pessoa sintética relata cansaço."
    assert current["media_matches"] == [{
        "id": "incident-1", "timestamp": 10, "modalities": ["audio", "image"],
    }]
    assert current["delivery_status"] == "delivered"
    assert requests[0]["category"] == "synthetic_review"
    assert set(requests[0]) == {"event_id", "category"}
    assert sample(client, timestamp=10, scenario="change", sample_id=identifier).status_code == 201
    assert len(requests) == 1
    assert sample(client, timestamp=11, scenario="change", sample_id=identifier).status_code == 409
    unchanged = sample(client, timestamp=15, scenario="change").json()["samples"][0]
    assert unchanged["events"] == []
    assert unchanged["delivery_status"] is None
    assert len(requests) == 1
    assert client.get("/api/synthetic-stream/session-two").json()["samples"] == []
    with database.connect() as db:
        assert db.execute("SELECT count(*) FROM synthetic_stream_receipts").fetchone()[0] == 1
        assert db.execute("SELECT count(*) FROM webhook_outbox").fetchone()[0] == 0


def test_delivery_failure_is_visible_and_retry_deduplicates_receipt(client, monkeypatch):
    monkeypatch.setattr(
        synthetic_stream, "_client",
        lambda: httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(503))),
    )
    sample(client)
    identifier = str(uuid.uuid4())
    result = sample(client, timestamp=10, scenario="change", sample_id=identifier).json()["samples"][0]
    assert result["delivery_status"] == "failed"
    assert "Falha no receptor" in result["delivery_error"]

    def transport(request):
        response = client.post("/api/synthetic-stream/receiver", json=json.loads(request.content))
        return httpx.Response(response.status_code, json=response.json())

    monkeypatch.setattr(
        synthetic_stream, "_client", lambda: httpx.Client(transport=httpx.MockTransport(transport)),
    )
    retry = client.post(f"/api/synthetic-stream/session-one/samples/{identifier}/retry")
    assert retry.json()["samples"][0]["delivery_status"] == "delivered"
    assert client.post(f"/api/synthetic-stream/session-one/samples/{identifier}/retry").status_code == 409


def test_rejects_missing_closed_invalid_and_out_of_order_sessions(client):
    assert sample(client, session="missing").status_code == 404
    assert sample(client, timestamp=31.1).status_code == 422
    assert sample(client, timestamp=-1).status_code == 422
    assert sample(client, sample_id="not-a-uuid").status_code == 422
    identifier = str(uuid.uuid4())
    assert sample(client, sample_id=identifier).status_code == 201
    assert sample(client, timestamp=0.5).status_code == 409
    with database.connect() as db:
        db.execute(
            "UPDATE monitor_sessions SET snapshot=? WHERE id='session-one'",
            (json.dumps({"closed": True, "elapsed": 30}),),
        )
    assert sample(client, timestamp=5).status_code == 409
    assert sample(client, sample_id=identifier).status_code == 201
    assert client.get("/api/synthetic-stream/session-one").status_code == 200


def test_receiver_is_idempotent_and_requires_loopback(client):
    payload = {"event_id": str(uuid.uuid4()), "category": "synthetic_review"}
    assert client.post("/api/synthetic-stream/receiver", json=payload).status_code == 202
    assert client.post("/api/synthetic-stream/receiver", json=payload).status_code == 202
    with database.connect() as db:
        assert db.execute("SELECT count(*) FROM synthetic_stream_receipts").fetchone()[0] == 1
    app = client.app
    with TestClient(app, client=("192.0.2.1", 1)) as remote:
        assert remote.post("/api/synthetic-stream/receiver", json=payload).status_code == 403


def test_correlates_only_active_evidence_within_window_and_in_same_session(client, monkeypatch):
    with database.connect() as db:
        db.execute(
            "UPDATE monitor_incidents SET payload=? WHERE id='incident-1'",
            (json.dumps({
                "id": "incident-1", "timestamp": 1, "modalities": ["audio", "image"],
                "status": "confirmed", "merged_into": None,
                "evidence": [
                    {"source": "image", "timestamp": 1, "status": "confirmed"},
                    {"source": "audio", "timestamp": 20, "status": "confirmed"},
                ],
            }),),
        )
    monkeypatch.setattr(synthetic_stream, "_deliver", lambda *args: None)
    sample(client)
    current = sample(client, timestamp=20, scenario="change").json()["samples"][0]
    assert current["media_matches"] == [{"id": "incident-1", "timestamp": 20, "modalities": ["audio"]}]
    other = sample(client, session="session-two", timestamp=20).json()["samples"][0]
    assert other["media_matches"] == []


def test_interrupted_delivery_is_retryable_after_restart(client, monkeypatch):
    monkeypatch.setattr(synthetic_stream, "_deliver", lambda *args: None)
    sample(client)
    identifier = str(uuid.uuid4())
    sample(client, timestamp=10, scenario="change", sample_id=identifier)
    assert client.get("/api/synthetic-stream/session-one").json()["samples"][0]["delivery_status"] == "sending"
    database.initialize()
    result = client.get("/api/synthetic-stream/session-one").json()["samples"][0]
    assert result["delivery_status"] == "failed"
    assert "interrompida" in result["delivery_error"]


@pytest.mark.parametrize("response", [
    httpx.Response(200, json={"accepted": True}),
    httpx.Response(202, json={"accepted": False}),
    httpx.Response(202, content=b"not-json"),
])
def test_invalid_receiver_confirmation_does_not_report_delivery(client, monkeypatch, response):
    monkeypatch.setattr(
        synthetic_stream, "_client",
        lambda: httpx.Client(transport=httpx.MockTransport(lambda request: response)),
    )
    sample(client)
    result = sample(client, timestamp=10, scenario="change").json()["samples"][0]
    assert result["delivery_status"] == "failed"
