import json
import logging
import sqlite3
import threading

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import database
from app.routers import notifications
from app.services import alert_log, webhook_notifications as webhook


@pytest.fixture
def configured(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATA_DIR", tmp_path)
    monkeypatch.setenv("ALERT_WEBHOOK_ENABLED", "true")
    monkeypatch.setenv("ALERT_WEBHOOK_URL", "https://webhook.example.test/receive")
    monkeypatch.setenv("ALERT_WEBHOOK_BEARER_TOKEN", "synthetic-token")
    database.initialize()
    app = FastAPI()
    app.include_router(notifications.router)
    with TestClient(app) as client:
        yield client
    webhook.stop_worker()


def event(*, provisional=False, severity="critical"):
    return {
        "timestamp": 10, "kind": "synthetic-private-text", "source": "audio",
        "severity": severity, "provisional": provisional,
    }


def sync(events):
    with database.connect() as db:
        return alert_log.sync_alerts(
            db, "private-session", "private-video", events,
            [{"start": 10, "end": 11, "text": "synthetic-private-transcript"}],
        )


def deliveries():
    with database.connect() as db:
        return [dict(row) for row in db.execute("SELECT * FROM webhook_outbox ORDER BY created_at")]


def transport(monkeypatch, handler):
    monkeypatch.setattr(
        webhook, "_client", lambda: httpx.Client(transport=httpx.MockTransport(handler)),
    )


def test_enqueue_only_confirmed_critical_alerts_and_rollback_atomically(configured, monkeypatch):
    monkeypatch.setenv("ALERT_WEBHOOK_ENABLED", "false")
    sync([event()])
    assert deliveries() == []
    monkeypatch.setenv("ALERT_WEBHOOK_ENABLED", "true")
    sync([event(severity="warning")])
    assert deliveries() == []
    sync([event(provisional=True)])
    assert deliveries() == []
    sync([event(provisional=False)])
    assert len(deliveries()) == 1
    sync([event(provisional=False)])
    assert len(deliveries()) == 1

    with pytest.raises(RuntimeError, match="force rollback"):
        with database.connect() as db:
            alert_log.sync_alerts(db, "another-session", "video", [event()])
            raise RuntimeError("force rollback")
    assert len(deliveries()) == 1
    with database.connect() as db:
        assert db.execute(
            "SELECT count(*) FROM monitor_alerts WHERE session_id='another-session'",
        ).fetchone()[0] == 0


def test_delivery_sends_minimal_payload_without_private_content(configured, monkeypatch):
    captured = []

    def handler(request):
        captured.append(request)
        return httpx.Response(202)

    transport(monkeypatch, handler)
    sync([event()])
    assert webhook.dispatch_one()
    assert not webhook.dispatch_one()
    assert len(captured) == 1
    request = captured[0]
    payload = json.loads(request.content)
    assert request.method == "POST"
    assert request.headers["authorization"] == "Bearer synthetic-token"
    assert request.headers["idempotency-key"] == payload["event_id"]
    assert set(payload) == {"event_id", "category", "source", "created_at", "notice"}
    assert payload["source"] == "audio"
    assert payload["category"] == "critical_review"
    for private in ("synthetic-private", "private-session", "private-video", "synthetic-token"):
        assert private not in json.dumps(payload)
    status = configured.get("/api/notifications/status").json()
    assert status["enabled"] and status["configured"]
    assert status["items"][0]["status"] == "delivered"
    assert status["items"][0]["attempts"] == 1
    assert status["items"][0]["http_status"] == 202
    assert status["items"][0]["delivered_at"]
    assert "synthetic-token" not in json.dumps(status)


def test_webhook_does_not_log_endpoint_and_does_not_read_response_body(configured, monkeypatch, caplog):
    class UnreadableBody(httpx.SyncByteStream):
        def __iter__(self):
            raise AssertionError("A resposta do webhook não deve ser carregada.")
            yield b""

    transport(monkeypatch, lambda _request: httpx.Response(202, stream=UnreadableBody()))
    sync([event()])
    with caplog.at_level(logging.INFO, logger="httpx"):
        assert webhook.dispatch_one()
    assert "webhook.example.test" not in caplog.text
    assert "synthetic-token" not in caplog.text
    assert deliveries()[0]["status"] == "delivered"


def test_timeout_retries_with_backoff_then_allows_manual_retry(configured, monkeypatch):
    attempts = []

    def handler(request):
        attempts.append(request)
        raise httpx.ConnectTimeout("Synthetic timeout", request=request)

    transport(monkeypatch, handler)
    sync([event()])
    for instant in (0, 1, 6, 36, 156):
        assert webhook.dispatch_one(now=instant)
    assert len(attempts) == 5
    row = deliveries()[0]
    assert row["status"] == "failed"
    assert row["attempts"] == 5
    assert "tempo limite" in row["last_error"]
    assert len({request.headers["idempotency-key"] for request in attempts}) == 1
    assert configured.post(f"/api/notifications/{row['id']}/retry").json() == {"status": "pending"}
    assert deliveries()[0]["attempts"] == 0
    assert configured.post(f"/api/notifications/{row['id']}/retry").status_code == 409


@pytest.mark.parametrize("http_status,expected", [(401, "failed"), (302, "failed"), (429, "pending"), (503, "pending")])
def test_http_errors_are_visible_and_only_transient_responses_retry(
    configured, monkeypatch, http_status, expected,
):
    transport(monkeypatch, lambda _request: httpx.Response(http_status))
    sync([event()])
    assert webhook.dispatch_one(now=100)
    row = deliveries()[0]
    assert row["status"] == expected
    assert row["http_status"] == http_status
    assert row["last_error"] == f"Webhook retornou HTTP {http_status}."
    if expected == "pending":
        assert not webhook.dispatch_one(now=100)
        assert row["next_attempt"] == 101


def test_pending_delivery_is_cancelled_when_alert_becomes_provisional(configured, monkeypatch):
    sent = []
    transport(monkeypatch, lambda request: sent.append(request) or httpx.Response(200))
    sync([event()])
    sync([event(provisional=True)])
    sync([event(provisional=False)])
    assert webhook.dispatch_one()
    assert not webhook.dispatch_one()
    rows = deliveries()
    assert [row["status"] for row in rows] == ["cancelled", "delivered"]
    assert len(sent) == 1


def test_unconfigured_webhook_fails_visibly_and_disabled_state_is_explicit(configured, monkeypatch, caplog):
    monkeypatch.delenv("ALERT_WEBHOOK_URL")
    sync([event()])
    assert webhook.dispatch_one()
    status = configured.get("/api/notifications/status").json()
    assert status["enabled"] and not status["configured"]
    assert status["items"][0]["status"] == "failed"
    assert "Configure ALERT_WEBHOOK_URL" in status["items"][0]["last_error"]
    assert "Webhook não configurado" in caplog.text
    monkeypatch.setenv("ALERT_WEBHOOK_ENABLED", "false")
    assert configured.post(f"/api/notifications/{status['items'][0]['id']}/retry").status_code == 409
    assert configured.get("/api/notifications/status").json()["message"].startswith("Webhook desativado")


@pytest.mark.parametrize(
    "url,token",
    [
        ("http://external.example.test/receive", "token"),
        ("https://user:password@example.test/", "token"),
        ("https://example.test/?secret=abc", "token"),
        ("https://example.test/#secret", "token"),
        ("https://example.test:99999/", "token"),
        ("https://example.test/", "token\ninjection"),
    ],
)
def test_rejects_unsafe_webhook_configuration(configured, monkeypatch, url, token):
    monkeypatch.setenv("ALERT_WEBHOOK_URL", url)
    monkeypatch.setenv("ALERT_WEBHOOK_BEARER_TOKEN", token)
    status = configured.get("/api/notifications/status").json()
    assert status["enabled"] and not status["configured"]
    with pytest.raises(webhook.WebhookConfigurationError):
        webhook.configuration()


def test_worker_recovers_an_interrupted_delivery(configured, monkeypatch):
    delivered = threading.Event()
    transport(monkeypatch, lambda _request: delivered.set() or httpx.Response(200))
    sync([event()])
    with database.connect() as db:
        db.execute("UPDATE webhook_outbox SET status='sending',attempts=1")
    webhook.start_worker()
    try:
        assert delivered.wait(3)
    finally:
        webhook.stop_worker()
    assert deliveries()[0]["status"] == "delivered"
    assert deliveries()[0]["attempts"] == 2
    assert not webhook.worker_running()


def test_invalid_enable_flag_is_reported(configured, monkeypatch, caplog):
    monkeypatch.setenv("ALERT_WEBHOOK_ENABLED", "maybe")
    with caplog.at_level(logging.ERROR):
        webhook.start_worker()
    assert not webhook.worker_running()
    assert "deve ser true ou false" in caplog.text
    assert "deve ser true ou false" in configured.get("/api/notifications/status").json()["message"]


def test_pending_delivery_for_unconfirmed_alert_is_cancelled(configured, monkeypatch):
    sync([event()])
    with database.connect() as db:
        db.execute("UPDATE monitor_alerts SET status='retracted'")
    transport(monkeypatch, lambda _request: pytest.fail("Uma entrega cancelada não deve ser enviada."))
    assert webhook.dispatch_one()
    assert deliveries()[0]["status"] == "cancelled"
    monkeypatch.setenv("ALERT_WEBHOOK_ENABLED", "false")
    assert not webhook.dispatch_one()


def test_retry_after_network_failure_uses_wall_clock(configured, monkeypatch):
    transport(monkeypatch, lambda _request: httpx.Response(503))
    sync([event()])
    assert webhook.dispatch_one()
    assert deliveries()[0]["next_attempt"] > 0


def test_worker_reports_database_error_and_stops_cleanly(configured, monkeypatch, caplog):
    worker = webhook.WebhookWorker()
    calls = []

    def fail_once():
        calls.append(1)
        raise sqlite3.OperationalError("synthetic database failure")

    def stop_after_error(_delay):
        worker.stop_event.set()
        return True

    monkeypatch.setattr(webhook, "dispatch_one", fail_once)
    monkeypatch.setattr(worker.stop_event, "wait", stop_after_error)
    with caplog.at_level(logging.ERROR):
        worker._run()
    assert len(calls) == 1
    assert "Falha ao consultar ou atualizar a fila" in caplog.text


def test_enabled_but_misconfigured_worker_reports_problem(configured, monkeypatch, caplog):
    monkeypatch.delenv("ALERT_WEBHOOK_URL")
    with caplog.at_level(logging.ERROR):
        webhook.start_worker()
    try:
        assert webhook.worker_running()
        assert "Webhook habilitado sem configuração válida" in caplog.text
    finally:
        webhook.stop_worker()


def test_loopback_and_invalid_port_validation(configured, monkeypatch):
    monkeypatch.setenv("ALERT_WEBHOOK_URL", "http://localhost:8000/receive")
    assert webhook.configuration()[0] == "http://localhost:8000/receive"
    monkeypatch.setenv("ALERT_WEBHOOK_URL", "http://127.0.0.1:0/receive")
    with pytest.raises(webhook.WebhookConfigurationError, match="porta inválida"):
        webhook.configuration()
