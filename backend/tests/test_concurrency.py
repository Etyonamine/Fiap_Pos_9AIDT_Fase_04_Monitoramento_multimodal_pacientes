import json
import statistics
import sqlite3
import sys
import threading
import time
import tracemalloc
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import database
from app.services import alert_log
from app.services.incidents import session_incidents
import pytest


@pytest.mark.parametrize("fail", [False, True])
def test_connection_context_closes_and_preserves_commit_or_rollback(tmp_path, monkeypatch, fail):
    monkeypatch.setattr(database, "DATA_DIR", tmp_path)
    database.initialize()
    connection = database.connect()
    try:
        with connection as db:
            db.execute("INSERT INTO monitor_sessions VALUES ('transaction','bed','{}')")
            if fail:
                raise ValueError("simulated transaction failure")
    except ValueError:
        assert fail
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        connection.execute("SELECT 1")
    with database.connect() as db:
        count = db.execute("SELECT COUNT(*) FROM monitor_sessions").fetchone()[0]
    assert count == (0 if fail else 1)


def test_concurrent_writers_preserve_unique_alerts_incidents_and_acknowledgements(
    tmp_path, monkeypatch, record_testsuite_property,
):
    monkeypatch.setattr(database, "DATA_DIR", tmp_path)
    database.initialize()
    events = [
        {"timestamp": index, "kind": "Saída da cerca virtual", "severity": "critical", "source": "image"}
        for index in range(12)
    ]
    barrier = threading.Barrier(4)

    def writer(worker):
        barrier.wait(timeout=10)
        elapsed = []
        for _ in range(12):
            start = time.perf_counter()
            with closing(database.connect()) as db, db:
                db.execute("BEGIN IMMEDIATE")
                alerts = alert_log.sync_alerts(db, "shared", "bed", events)
                alert_log.acknowledge(db, "shared", [alerts[worker]["id"]])
            elapsed.append(time.perf_counter() - start)
        return elapsed

    with ThreadPoolExecutor(max_workers=4) as executor:
        times = [duration for result in executor.map(writer, range(4)) for duration in result]
    with closing(database.connect()) as db:
        alerts = alert_log.session_alerts(db, "shared")
        incidents = session_incidents(db, "shared")
        assert len(alerts) == len(incidents) == 12
        assert len({item["id"] for item in alerts}) == 12
        assert sum(item["acknowledged_at"] is not None for item in alerts) == 4
        assert db.execute("SELECT COUNT(*) FROM monitor_alert_log WHERE action='detected'").fetchone()[0] == 12
        assert db.execute(
            "SELECT COUNT(*) FROM monitor_alert_log WHERE action='immediate_care_requested'",
        ).fetchone()[0] == 4
    # Budget applies only to local test transactions, not YOLO/cloud or clinical real-time claims.
    p95 = statistics.quantiles(times, n=100)[94]
    record_testsuite_property("sqlite_transaction_p95_seconds", p95)
    record_testsuite_property("sqlite_transaction_max_seconds", max(times))
    record_testsuite_property("sqlite_concurrent_transactions", len(times))
    assert p95 < 5
    assert max(times) < 10


def test_repeated_polling_does_not_grow_history_or_retain_unbounded_memory(
    tmp_path, monkeypatch, record_testsuite_property,
):
    monkeypatch.setattr(database, "DATA_DIR", tmp_path)
    database.initialize()
    event = {"timestamp": 1, "kind": "Fala: socorro", "severity": "critical", "source": "audio"}
    with closing(database.connect()) as db, db:
        alert_log.sync_alerts(db, "session", "bed", [event])
        first = session_incidents(db, "session")
    tracemalloc.start()
    try:
        for _ in range(250):
            with closing(database.connect()) as db, db:
                db.execute("BEGIN IMMEDIATE")
                alert_log.sync_alerts(db, "session", "bed", [event])
                assert session_incidents(db, "session") == first
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    record_testsuite_property("polling_peak_python_bytes", peak)
    record_testsuite_property("polling_iterations", 250)
    assert peak < 8 * 1024 * 1024
    with closing(database.connect()) as db:
        assert db.execute("SELECT COUNT(*) FROM monitor_alert_log").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM monitor_incident_log").fetchone()[0] == 1
        assert json.loads(db.execute("SELECT payload FROM monitor_incidents").fetchone()[0]) == first[0]
