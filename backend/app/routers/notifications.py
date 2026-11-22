from fastapi import APIRouter, HTTPException, Query

from app.database import connect
from app.services.webhook_notifications import configuration_status, retry_failed, worker_running

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.get("/status")
def status(limit: int = Query(default=20, ge=1, le=100)):
    with connect() as db:
        rows = db.execute(
            "SELECT id,source,created_at,updated_at,status,attempts,last_error,http_status,"
            "delivered_at FROM webhook_outbox ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return {**configuration_status(), "worker_running": worker_running(),
            "items": [dict(row) for row in rows]}


@router.post("/{delivery_id}/retry")
def retry(delivery_id: str):
    configuration = configuration_status()
    if not configuration["enabled"] or not configuration["configured"]:
        raise HTTPException(409, "Ative e configure o webhook antes de repetir uma entrega.")
    with connect() as db:
        if not retry_failed(db, delivery_id):
            raise HTTPException(409, "Entrega não encontrada ou não está em falha.")
    return {"status": "pending"}
