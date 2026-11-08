import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.main import app


def test_websocket_status_accepts_connections_and_reconnects():
    client = TestClient(app)
    for _ in range(2):
        with client.websocket_connect("/api/ws") as websocket:
            assert websocket.receive_json() == {"status": "connected"}
            websocket.send_text("keep-alive")


def test_websocket_clients_can_connect_simultaneously():
    client = TestClient(app)
    with client.websocket_connect("/api/ws") as first:
        assert first.receive_json() == {"status": "connected"}
        with client.websocket_connect("/api/ws") as second:
            assert second.receive_json() == {"status": "connected"}
            first.send_text("keep-alive")
