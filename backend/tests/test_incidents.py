import json
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import database
from app.routers import incidents as routes
from app.services import alert_log
from app.services.incidents import FENCE_EXIT, session_incidents


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATA_DIR", tmp_path)
    database.initialize()
    with database.connect() as connection:
        yield connection


def image(timestamp=10, kind=FENCE_EXIT):
    return {"timestamp": timestamp, "kind": kind, "severity": "critical", "source": "image"}


def speech(timestamp=12, provisional=False, kind="Fala: socorro"):
    return {
        "timestamp": timestamp, "kind": kind, "severity": "critical", "source": "audio",
        "provisional": provisional,
    }


def sync(db, events, session="session", transcripts=None):
    alert_log.sync_alerts(db, session, "bed", events, transcripts)
    return [item for item in session_incidents(db, session) if item["merged_into"] is None]


def test_empty_and_individual_alerts_remain_immediate(db):
    assert sync(db, []) == []
    first = sync(db, [image()])[0]
    assert first["modalities"] == ["image"]
    assert not first["multimodal"]
    assert first["status"] == "confirmed"
    assert not first["acknowledged"]
    assert len(alert_log.session_alerts(db, "session")) == 1
    sound = sync(db, [speech()], session="other")[0]
    assert sound["modalities"] == ["audio"]
    assert not sound["multimodal"]


@pytest.mark.parametrize("offset,count", [(-10, 1), (10, 1), (-10.001, 2), (10.001, 2)])
def test_exact_window_in_both_directions(db, offset, count):
    incidents = sync(db, [image(20), speech(20 + offset)])
    assert len(incidents) == count
    assert incidents[0]["multimodal"] == (count == 1)


@pytest.mark.parametrize("audio_first", [False, True])
def test_late_second_modality_keeps_identity_and_evidence_idempotently(db, audio_first):
    visual, audio = image(), speech()
    initial = sync(db, [audio if audio_first else visual])[0]
    combined = sync(db, [visual, audio], transcripts=[
        {"start": 12, "end": 13, "text": "Socorro, preciso de ajuda."},
    ])[0]
    assert combined["id"] == initial["id"]
    assert combined["multimodal"]
    assert combined["version"] == initial["version"] + 1
    assert len(combined["evidence"]) == 2
    assert combined["evidence"][1]["text"] == "Socorro, preciso de ajuda."
    log_count = db.execute("SELECT COUNT(*) FROM monitor_incident_log").fetchone()[0]
    assert sync(db, [visual, audio])[0] == combined
    assert db.execute("SELECT COUNT(*) FROM monitor_incident_log").fetchone()[0] == log_count
    assert len(alert_log.session_alerts(db, "session")) == 2


def test_fusion_uses_nearest_exit_not_transitive_chaining(db):
    items = sync(db, [image(0), image(15), speech(9), speech(24), speech(35)])
    assert len(items) == 3
    groups = {item["timestamp"]: item for item in items}
    assert groups[0]["modalities"] == ["image"]
    assert {e["timestamp"] for e in groups[9]["evidence"]} == {9, 15, 24}
    assert groups[35]["modalities"] == ["audio"]


def test_provisional_retraction_retains_visual_alert_and_audit(db):
    original = sync(db, [image(), speech(provisional=True)])[0]
    assert original["status"] == "provisional"
    assert original["multimodal"]
    corrected = sync(db, [image()])[0]
    assert corrected["id"] == original["id"]
    assert corrected["status"] == "confirmed"
    assert not corrected["multimodal"]
    assert corrected["modalities"] == ["image"]
    assert corrected["evidence"][1]["status"] == "retracted"
    history = [json.loads(row[0]) for row in db.execute(
        "SELECT payload FROM monitor_incident_log ORDER BY id",
    )]
    assert history[0]["evidence"][1]["status"] == "provisional"
    assert history[-1]["evidence"][1]["status"] == "retracted"


def test_audio_only_correction_and_confirmation(db):
    original = sync(db, [speech(provisional=True)])[0]
    corrected = sync(db, [speech(kind="Fala: ajuda")])[0]
    assert original["id"] == corrected["id"]
    assert len(corrected["evidence"]) == 2
    assert corrected["status"] == "confirmed"
    assert corrected["modalities"] == ["audio"]
    assert sync(db, [speech(kind="Fala: ajuda")])[0] == corrected


def test_audio_only_provisional_can_be_fully_withdrawn(db):
    original = sync(db, [speech(provisional=True)])[0]
    withdrawn = sync(db, [])[0]
    assert withdrawn["id"] == original["id"]
    assert withdrawn["status"] == "retracted"
    assert withdrawn["modalities"] == []
    assert not withdrawn["acknowledged"]


def test_acknowledgement_is_not_inherited_by_new_evidence(db):
    original = sync(db, [image()])[0]
    first = original["evidence"][0]["id"]
    alert_log.acknowledge(db, "session", [first])
    assert session_incidents(db, "session")[0]["acknowledged"]
    combined = sync(db, [image(), speech()])[0]
    assert combined["id"] == original["id"]
    assert not combined["acknowledged"]
    assert combined["evidence"][0]["acknowledged_at"]
    alert_log.acknowledge(db, "session", [item["id"] for item in combined["evidence"]])
    acknowledged = session_incidents(db, "session")[0]
    assert acknowledged["acknowledged"]
    alert_log.acknowledge(db, "session", [first])
    assert session_incidents(db, "session")[0] == acknowledged


def test_sessions_and_unrelated_critical_image_rules_are_not_correlated(db):
    sync(db, [image()], session="one")
    assert not sync(db, [speech()], session="two")[0]["multimodal"]
    assert len(sync(db, [image(kind="Outra regra"), speech()], session="three")) == 2


def test_late_bridge_merges_prior_incidents_without_erasing_audit(db):
    original = sync(db, [speech(0), speech(18)])
    assert len(original) == 2
    combined = sync(db, [speech(0), speech(18), image(9)])
    assert len(combined) == 1
    assert combined[0]["id"] == original[0]["id"]
    all_items = session_incidents(db, "session")
    assert len(all_items) == 2
    retired = next(item for item in all_items if item["merged_into"])
    assert retired["merged_into"] == combined[0]["id"]
    actions = [row[0] for row in db.execute(
        "SELECT action FROM monitor_incident_log WHERE incident_id=? ORDER BY id", (retired["id"],),
    )]
    assert actions == ["created", "merged"]
    _session(db, "session")
    db.commit()
    app = FastAPI()
    app.include_router(routes.router)
    with TestClient(app) as client:
        page = client.get("/api/incidents").json()
        assert len(page["items"]) == 1
        assert page["items"][0]["id"] == combined[0]["id"]
        audit = client.get(f"/api/incidents/{combined[0]['id']}/history?limit=1").json()
        assert audit["items"][0]["action"] == "merged"
        assert audit["items"][0]["payload"]["id"] == retired["id"]
        assert audit["next_cursor"]
        older = client.get(
            f"/api/incidents/{combined[0]['id']}/history?before={audit['next_cursor']}",
        ).json()
        assert {item["payload"]["id"] for item in older["items"]} == {
            combined[0]["id"], retired["id"],
        }


def test_warnings_do_not_become_incidents_and_same_utterance_terms_stay_together(db):
    assert sync(db, [{**speech(), "severity": "warning"}]) == []
    items = sync(db, [speech(kind="Fala: socorro"), speech(kind="Fala: ajuda")])
    assert len(items) == 1
    assert items[0]["modalities"] == ["audio"]
    assert len(items[0]["evidence"]) == 2


def test_transcript_boundary_uses_the_segment_starting_at_the_event(db):
    item = sync(db, [speech(12)], transcripts=[
        {"start": 10, "end": 12, "text": "Frase anterior."},
        {"start": 12, "end": 14, "text": "Socorro."},
    ])[0]
    assert item["evidence"][0]["text"] == "Socorro."


def _session(db, session_id, camera=False):
    db.execute("INSERT INTO monitor_sessions VALUES (?,?,?)", (session_id, "bed", '{"transcripts":[]}'))
    if camera:
        db.execute(
            "INSERT INTO camera_sessions VALUES (?,?,?,?,?,?,?)",
            (session_id, "{}", 0, "{}", 1, None, "2026-01-01"),
        )


def test_unified_api_pagination_audit_and_restart(db):
    _session(db, "recording")
    _session(db, "camera", camera=True)
    sync(db, [image()], session="recording")
    sync(db, [image(), speech()], session="camera")
    db.commit()
    app = FastAPI()
    app.include_router(routes.router)
    with TestClient(app) as client:
        first = client.get("/api/incidents?limit=1").json()
        assert first["items"][0]["origin"] == "camera"
        assert first["next_cursor"]
        second = client.get(f"/api/incidents?limit=1&before={first['next_cursor']}").json()
        assert second["items"][0]["origin"] == "recording"
        assert second["next_cursor"] is None
        identifier = first["items"][0]["id"]
        audit = client.get(f"/api/incidents/{identifier}/history?limit=1").json()
        assert audit["items"][0]["payload"]["multimodal"]
        assert client.get("/api/incidents/unknown/history").status_code == 404
        assert client.get("/api/incidents?limit=0").status_code == 422
        assert client.get("/api/incidents?before=-1").status_code == 422
        database.initialize()
        assert client.get("/api/incidents?limit=1").json() == first


def test_legacy_sessions_are_backfilled_once_from_alerts(db):
    _session(db, "legacy")
    sync(db, [image(), speech()], session="legacy")
    db.execute("DELETE FROM monitor_incidents WHERE session_id='legacy'")
    db.execute("DELETE FROM monitor_incident_log WHERE session_id='legacy'")
    db.commit()
    database.initialize()
    items = session_incidents(db, "legacy")
    assert len(items) == 1
    assert items[0]["multimodal"]
    database.initialize()
    assert session_incidents(db, "legacy") == items
