import json
import sqlite3
import uuid
from datetime import datetime, timezone

CORRELATION_SECONDS = 10
FENCE_EXIT = "Saída da cerca virtual"


def session_incidents(db: sqlite3.Connection, session_id: str) -> list[dict]:
    return [json.loads(row["payload"]) for row in db.execute(
        "SELECT payload FROM monitor_incidents WHERE session_id=? ORDER BY sequence", (session_id,),
    )]


def sync_incidents(
    db: sqlite3.Connection, session_id: str, alerts: list[dict], transcripts: list[dict],
) -> list[dict]:
    """Project individual alerts into audited, session-local temporal incidents."""
    previous = session_incidents(db, session_id)
    old_evidence = {
        evidence["id"]: evidence for incident in previous if incident["merged_into"] is None
        for evidence in incident["evidence"]
    }
    images = [alert for alert in alerts if alert["source"] == "image" and alert["kind"] == FENCE_EXIT]
    groups: dict[str, list[dict]] = {alert["id"]: [alert] for alert in alerts if alert["source"] != "audio"}
    for alert in alerts:
        if alert["source"] != "audio":
            continue
        nearby = [
            image for image in images
            if abs(image["timestamp"] - alert["timestamp"]) <= CORRELATION_SECONDS
        ]
        if nearby:
            anchor = min(nearby, key=lambda image: (
                abs(image["timestamp"] - alert["timestamp"]), image["timestamp"], image["id"],
            ))
            key = anchor["id"]
        else:
            key = f"audio:{alert['timestamp']:.6f}"
        groups.setdefault(key, []).append(alert)

    stamp = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
    used: set[str] = set()
    destinations: dict[str, str] = {}
    for members in groups.values():
        ids = {alert["id"] for alert in members}
        candidates = [
            incident for incident in previous
            if incident["id"] not in used and incident["merged_into"] is None
            and any(evidence["id"] in ids for evidence in incident["evidence"])
        ]
        old = candidates[0] if candidates else None
        identifier = old["id"] if old else uuid.uuid4().hex
        used.add(identifier)
        destinations.update({alert["id"]: identifier for alert in members})
        evidence = []
        for alert in sorted(members, key=lambda item: (item["timestamp"], item["source"], item["kind"])):
            detail = {**alert, "text": old_evidence.get(alert["id"], {}).get("text")}
            if alert["source"] == "audio":
                segments = [
                    segment for segment in transcripts
                    if segment["start"] <= alert["timestamp"] <= segment["end"]
                ]
                segment = max(segments, key=lambda item: item["start"], default=None)
                if segment is not None and alert["status"] != "retracted":
                    detail["text"] = segment["text"]
            evidence.append(detail)
        active = [item for item in evidence if item["status"] != "retracted"]
        modalities = sorted({item["source"] for item in active})
        payload = {
            "id": identifier, "session_id": session_id, "video_id": members[0]["video_id"],
            "timestamp": min(item["timestamp"] for item in evidence),
            "severity": "critical", "modalities": modalities,
            "multimodal": modalities == ["audio", "image"],
            "status": (
                "retracted" if not active else
                "provisional" if any(item["status"] == "provisional" for item in active) else "confirmed"
            ),
            "acknowledged": bool(active) and all(item["acknowledged_at"] for item in active),
            "correlation_seconds": CORRELATION_SECONDS, "evidence": evidence,
            "created_at": old["created_at"] if old else stamp,
            "updated_at": old["updated_at"] if old else stamp,
            "version": old["version"] if old else 1, "merged_into": None,
        }
        _save(db, payload, old, stamp)

    for old in previous:
        if old["id"] in used or old["merged_into"] is not None:
            continue
        target = next(destinations[item["id"]] for item in old["evidence"] if item["id"] in destinations)
        payload = {**old, "merged_into": target}
        _save(db, payload, old, stamp)
    return session_incidents(db, session_id)


def _save(db: sqlite3.Connection, payload: dict, old: dict | None, stamp: str) -> None:
    if old == payload:
        return
    if old:
        payload.update(updated_at=stamp, version=old["version"] + 1)
    action = (
        "created" if old is None else "merged" if payload["merged_into"] else
        "updated"
    )
    serialized = json.dumps(payload, ensure_ascii=False)
    db.execute(
        "INSERT INTO monitor_incidents (id,session_id,payload) VALUES (?,?,?) "
        "ON CONFLICT(id) DO UPDATE SET payload=excluded.payload",
        (payload["id"], payload["session_id"], serialized),
    )
    db.execute(
        "INSERT INTO monitor_incident_log (incident_id,session_id,action,created_at,payload) "
        "VALUES (?,?,?,?,?)",
        (payload["id"], payload["session_id"], action, stamp, serialized),
    )
