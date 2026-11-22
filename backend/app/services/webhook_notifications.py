import ipaddress
import json
import logging
import os
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timezone
from urllib.parse import urlsplit

import httpx

from app.database import connect
from app.services.private_http import private_http

logger = logging.getLogger(__name__)
MAX_ATTEMPTS = 5
RETRY_DELAYS = (1, 5, 30, 120)
_worker = None


class WebhookConfigurationError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def enabled() -> bool:
    return os.getenv("ALERT_WEBHOOK_ENABLED", "false").strip().lower() == "true"


def _is_loopback(host: str) -> bool:
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def configuration() -> tuple[str, str]:
    url = os.getenv("ALERT_WEBHOOK_URL", "").strip()
    token = os.getenv("ALERT_WEBHOOK_BEARER_TOKEN", "").strip()
    if not url or not token:
        raise WebhookConfigurationError(
            "Configure ALERT_WEBHOOK_URL e ALERT_WEBHOOK_BEARER_TOKEN no backend."
        )
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError as error:
        raise WebhookConfigurationError("ALERT_WEBHOOK_URL é inválida.") from error
    if (
        not parsed.hostname or parsed.username is not None or parsed.password is not None
        or parsed.query or parsed.fragment or any(character.isspace() for character in url)
        or (
            parsed.scheme != "https"
            and not (parsed.scheme == "http" and _is_loopback(parsed.hostname))
        )
    ):
        raise WebhookConfigurationError(
            "O webhook deve usar HTTPS sem credenciais na URL; HTTP é permitido apenas em loopback."
        )
    if port is not None and not 1 <= port <= 65535:
        raise WebhookConfigurationError("ALERT_WEBHOOK_URL contém porta inválida.")
    if any(ord(character) < 33 or ord(character) > 126 for character in token):
        raise WebhookConfigurationError("O token do webhook é inválido.")
    return url, token


def configuration_status() -> dict:
    flag = os.getenv("ALERT_WEBHOOK_ENABLED", "false").strip().lower()
    if flag not in ("true", "false"):
        return {
            "enabled": False, "configured": False,
            "message": "ALERT_WEBHOOK_ENABLED deve ser true ou false.",
        }
    if flag == "false":
        return {
            "enabled": False, "configured": False,
            "message": "Webhook desativado; nenhum alerta externo é enviado.",
        }
    try:
        configuration()
    except WebhookConfigurationError as error:
        return {"enabled": True, "configured": False, "message": str(error)}
    return {
        "enabled": True, "configured": True,
        "message": "Webhook habilitado; a entrega depende da resposta do destino.",
    }


def enqueue_alert(db, alert: dict) -> None:
    if not enabled() or alert["status"] != "confirmed":
        return
    source = alert.get("source") if alert.get("source") in ("image", "audio") else "other"
    delivery_id = f"{alert['id']}-{alert['version']}"
    stamp = _now()
    db.execute(
        "INSERT INTO webhook_outbox "
        "(id,alert_id,alert_version,source,created_at,updated_at,status) "
        "VALUES (?,?,?,?,?,?,'pending') ON CONFLICT(alert_id,alert_version) DO NOTHING",
        (delivery_id, alert["id"], alert["version"], source, stamp, stamp),
    )


def enqueue_clinical_event(
    db, session_id: str, source: str, event: dict,
) -> str | None:
    if not enabled():
        return None
    delivery_id = f"clinical-{uuid.uuid4().hex}"
    stamp = _now()
    payload = {
        "event_id": delivery_id,
        "category": "clinical_review",
        "source": source,
        "session_ref": session_id,
        "event_kind": event["kind"],
        "field": event.get("field"),
        "recorded_at": event["recorded_at"],
        "notice": "Regra demonstrativa para revisão humana; não é diagnóstico nem ordem clínica.",
    }
    db.execute(
        "INSERT INTO webhook_outbox "
        "(id,alert_id,alert_version,source,created_at,updated_at,status,"
        "requires_confirmation,payload) VALUES (?,?,?,?,?,?,'pending',0,?) "
        "ON CONFLICT(alert_id,alert_version) DO NOTHING",
        (delivery_id, delivery_id, 1, source, stamp, stamp,
         json.dumps(payload, ensure_ascii=False)),
    )
    return delivery_id


def cancel_pending(db, alert_id: str) -> None:
    db.execute(
        "UPDATE webhook_outbox SET status='cancelled',updated_at=?,last_error=? "
        "WHERE alert_id=? AND status='pending'",
        (_now(), "O alerta deixou de estar confirmado.", alert_id),
    )


def retry_failed(db, delivery_id: str) -> bool:
    result = db.execute(
        "UPDATE webhook_outbox SET status='pending',attempts=0,next_attempt=0,"
        "last_error=NULL,http_status=NULL,updated_at=? WHERE id=? AND status='failed'",
        (_now(), delivery_id),
    )
    return bool(result.rowcount)


def _client() -> httpx.Client:
    return httpx.Client(timeout=10, follow_redirects=False, trust_env=False)


def _claim(now: float) -> dict | None:
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute(
            "SELECT o.*,a.status AS alert_status FROM webhook_outbox o "
            "LEFT JOIN monitor_alerts a ON a.id=o.alert_id "
            "WHERE o.status='pending' AND o.next_attempt<=? "
            "ORDER BY o.created_at,o.id LIMIT 1",
            (now,),
        ).fetchone()
        if row is None:
            return None
        delivery = dict(row)
        if delivery["requires_confirmation"] and delivery["alert_status"] != "confirmed":
            db.execute(
                "UPDATE webhook_outbox SET status='cancelled',updated_at=?,"
                "last_error=? WHERE id=?",
                (_now(), "O alerta não está confirmado.", delivery["id"]),
            )
            delivery["cancelled"] = True
            return delivery
        delivery["attempts"] += 1
        db.execute(
            "UPDATE webhook_outbox SET status='sending',attempts=?,updated_at=? WHERE id=?",
            (delivery["attempts"], _now(), delivery["id"]),
        )
        return delivery


def _finish(delivery: dict, status: str, *, error: str | None = None,
            http_status: int | None = None, now: float | None = None) -> None:
    stamp = _now()
    retry_at = 0.0
    if status == "pending":
        retry_at = (time.time() if now is None else now) + RETRY_DELAYS[delivery["attempts"] - 1]
    with connect() as db:
        db.execute(
            "UPDATE webhook_outbox SET status=?,updated_at=?,last_error=?,http_status=?,"
            "next_attempt=?,delivered_at=? WHERE id=?",
            (status, stamp, error, http_status, retry_at,
             stamp if status == "delivered" else None, delivery["id"]),
        )


@private_http
def dispatch_one(*, now: float | None = None) -> bool:
    if not enabled():
        return False
    current_time = time.time() if now is None else now
    delivery = _claim(current_time)
    if delivery is None:
        return False
    if delivery.get("cancelled"):
        return True
    try:
        url, token = configuration()
    except WebhookConfigurationError as error:
        logger.error("Webhook não configurado: %s", error)
        _finish(delivery, "failed", error=str(error))
        return True
    if delivery["payload"]:
        try:
            payload = json.loads(delivery["payload"])
        except (json.JSONDecodeError, TypeError):
            logger.error("Payload inválido na entrega de webhook %s.", delivery["id"])
            _finish(delivery, "failed", error="Payload de alerta inválido.")
            return True
        if not isinstance(payload, dict) or payload.get("event_id") != delivery["id"]:
            logger.error("Payload inconsistente na entrega de webhook %s.", delivery["id"])
            _finish(delivery, "failed", error="Payload de alerta inconsistente.")
            return True
    else:
        payload = {
            "event_id": delivery["id"],
            "category": "critical_review",
            "source": delivery["source"],
            "created_at": delivery["created_at"],
            "notice": "Alerta para revisão humana; não confirma emergência ou atendimento.",
        }
    try:
        with _client() as client:
            with client.stream(
                "POST", url, json=payload,
                headers={"Authorization": f"Bearer {token}", "Idempotency-Key": delivery["id"]},
            ) as response:
                status_code = response.status_code
    except httpx.RequestError:
        message = "Falha de conexão ou tempo limite ao enviar webhook."
        logger.warning("%s Tentativa %s.", message, delivery["attempts"])
        next_status = "failed" if delivery["attempts"] >= MAX_ATTEMPTS else "pending"
        _finish(delivery, next_status, error=message, now=current_time)
        return True
    if 200 <= status_code < 300:
        _finish(delivery, "delivered", http_status=status_code)
    else:
        message = f"Webhook retornou HTTP {status_code}."
        logger.warning("%s Tentativa %s.", message, delivery["attempts"])
        retryable = status_code >= 500 or status_code in (408, 429)
        next_status = (
            "pending" if retryable and delivery["attempts"] < MAX_ATTEMPTS else "failed"
        )
        _finish(delivery, next_status, error=message, http_status=status_code, now=current_time)
    return True


class WebhookWorker:
    def __init__(self):
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._run, name="webhook-dispatch", daemon=True)

    def start(self) -> None:
        with connect() as db:
            db.execute(
                "UPDATE webhook_outbox SET status='pending',updated_at=? WHERE status='sending'",
                (_now(),),
            )
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        self.thread.join(timeout=15)
        if self.thread.is_alive():
            logger.error("O worker de webhook não encerrou dentro do prazo.")

    def _run(self) -> None:
        while not self.stop_event.is_set():
            try:
                dispatched = dispatch_one()
            except sqlite3.Error:
                logger.exception("Falha ao consultar ou atualizar a fila do webhook.")
                dispatched = False
            if not dispatched:
                self.stop_event.wait(1)


def start_worker() -> None:
    global _worker
    status = configuration_status()
    if status["enabled"] and not status["configured"]:
        logger.error("Webhook habilitado sem configuração válida: %s", status["message"])
    if status["enabled"]:
        _worker = WebhookWorker()
        _worker.start()
    elif not status["configured"] and status["message"].startswith("ALERT_WEBHOOK_ENABLED"):
        logger.error("%s", status["message"])


def stop_worker() -> None:
    global _worker
    if _worker is not None:
        _worker.stop()
        _worker = None


def worker_running() -> bool:
    return _worker is not None and _worker.thread.is_alive()
