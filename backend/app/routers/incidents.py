import json

from fastapi import APIRouter, HTTPException, Query

from app.database import connect

router = APIRouter(prefix="/api/incidents", tags=["incidents"])


@router.get("")
def incident_history(
    before: int | None = Query(default=None, ge=1),
    limit: int = Query(default=50, ge=1, le=100),
):
    with connect() as db:
        rows = db.execute(
            "SELECT i.sequence,i.payload,c.id AS camera_id,v.name FROM monitor_incidents i "
            "JOIN monitor_sessions s ON s.id=i.session_id "
            "LEFT JOIN camera_sessions c ON c.id=i.session_id "
            "LEFT JOIN videos v ON v.id=s.video_id "
            "WHERE (? IS NULL OR i.sequence<?) "
            "AND json_extract(i.payload,'$.merged_into') IS NULL "
            "ORDER BY i.sequence DESC LIMIT ?",
            (before, before, limit + 1),
        ).fetchall()
    return {
        "items": [
            {**json.loads(row["payload"]),
             "origin": "camera" if row["camera_id"] else "recording",
             "name": "Câmera" if row["camera_id"] else row["name"] or "Gravação indisponível"}
            for row in rows[:limit]
        ],
        "next_cursor": rows[limit - 1]["sequence"] if len(rows) > limit else None,
    }


@router.get("/{incident_id}/history")
def incident_audit(
    incident_id: str,
    before: int | None = Query(default=None, ge=1),
    limit: int = Query(default=50, ge=1, le=100),
):
    with connect() as db:
        if db.execute("SELECT id FROM monitor_incidents WHERE id=?", (incident_id,)).fetchone() is None:
            raise HTTPException(404, "Incidente não encontrado.")
        rows = db.execute(
            "WITH RECURSIVE related(id) AS ("
            "SELECT id FROM monitor_incidents WHERE id=? UNION "
            "SELECT i.id FROM monitor_incidents i JOIN related r "
            "ON json_extract(i.payload,'$.merged_into')=r.id) "
            "SELECT id,action,created_at,payload FROM monitor_incident_log "
            "WHERE incident_id IN (SELECT id FROM related) "
            "AND (? IS NULL OR id<?) ORDER BY id DESC LIMIT ?",
            (incident_id, before, before, limit + 1),
        ).fetchall()
    return {
        "items": [{**dict(row), "payload": json.loads(row["payload"])} for row in rows[:limit]],
        "next_cursor": rows[limit - 1]["id"] if len(rows) > limit else None,
    }
