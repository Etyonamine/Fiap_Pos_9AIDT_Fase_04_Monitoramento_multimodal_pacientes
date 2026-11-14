import ipaddress
import os
import socket

import pytest


@pytest.fixture(autouse=True)
def isolate_cloud_and_external_network(monkeypatch):
    for name in list(os.environ):
        if name.startswith("AZURE_"):
            monkeypatch.delenv(name)
    original = socket.socket.connect

    def local_only(connection, address):
        if isinstance(address, tuple):
            host = address[0]
            try:
                allowed = ipaddress.ip_address(host).is_loopback
            except ValueError:
                allowed = host == "localhost"
            if not allowed:
                raise AssertionError("External network is forbidden in automated tests; use a fake transport.")
        return original(connection, address)

    monkeypatch.setattr(socket.socket, "connect", local_only)
