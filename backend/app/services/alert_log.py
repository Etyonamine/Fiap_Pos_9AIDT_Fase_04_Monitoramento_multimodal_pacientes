import json
import uuid
from datetime import datetime, timezone


def now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def event_key(event: dict):
    return json.dumps([
        event.get("source", "image"), round(event["timestamp"], 6), event["kind"],
    ], ensure_ascii=False)


def session_alerts(db, session_id: str):
    return [dict(row) for row in db.execute(
        "SELECT * FROM monitor_alerts WHERE session_id=? ORDER BY created_at,id", (session_id,),
    )]


def write_log(db, alert: dict, action: str):
    db.execute(
        "INSERT INTO monitor_alert_log "
        "(alert_id,session_id,video_id,action,created_at,payload) VALUES (?,?,?,?,?,?)",
        (alert["id"], alert["session_id"], alert["video_id"], action, now(), json.dumps(alert)),
    )


def sync_alerts(db, session_id: str, video_id: str, events: list[dict]):
    existing = {alert["event_key"]: alert for alert in session_alerts(db, session_id)}
    active = {event_key(event): event for event in events if event["severity"] == "critical"}
    for key, event in active.items():
        status = "provisional" if event.get("provisional") else "confirmed"
        alert = existing.get(key)
        if alert is None:
            stamp = now()
            alert = {
                "id": uuid.uuid4().hex, "session_id": session_id, "video_id": video_id,
                "event_key": key, "timestamp": event["timestamp"], "kind": event["kind"],
                "source": event.get("source", "image"), "status": status,
                "created_at": stamp, "updated_at": stamp, "acknowledged_at": None, "version": 1,
            }
            db.execute(
                "INSERT INTO monitor_alerts VALUES "
                "(:id,:session_id,:video_id,:event_key,:timestamp,:kind,:source,:status,"
                ":created_at,:updated_at,:acknowledged_at,:version)", alert,
            )
            write_log(db, alert, "detected")
        elif alert["status"] != status:
            previous_status = alert["status"]
            alert.update(status=status, updated_at=now(), version=alert["version"] + 1)
            db.execute(
                "UPDATE monitor_alerts SET status=:status,updated_at=:updated_at,version=:version "
                "WHERE id=:id", alert,
            )
            write_log(db, alert, "reopened" if previous_status == "retracted" else status)
    for key, alert in existing.items():
        if key not in active and alert["status"] == "provisional":
            alert.update(status="retracted", updated_at=now(), version=alert["version"] + 1)
            db.execute(
                "UPDATE monitor_alerts SET status=:status,updated_at=:updated_at,version=:version "
                "WHERE id=:id", alert,
            )
            write_log(db, alert, "retracted")
    return session_alerts(db, session_id)


def acknowledge(db, session_id: str, alert_ids: list[str]):
    alerts = {alert["id"]: alert for alert in session_alerts(db, session_id)}
    if any(identifier not in alerts for identifier in alert_ids):
        raise ValueError("Alerta não pertence à sessão.")
    if any(alerts[identifier]["status"] == "retracted" for identifier in alert_ids):
        raise ValueError("O aviso provisório foi retirado; atualize os alertas antes de confirmar.")
    for identifier in dict.fromkeys(alert_ids):
        alert = alerts[identifier]
        if alert["acknowledged_at"] is not None:
            continue
        stamp = now()
        alert.update(acknowledged_at=stamp, updated_at=stamp, version=alert["version"] + 1)
        db.execute(
            "UPDATE monitor_alerts SET acknowledged_at=:acknowledged_at,"
            "updated_at=:updated_at,version=:version WHERE id=:id", alert,
        )
        write_log(db, alert, "immediate_care_requested")
    return session_alerts(db, session_id)
