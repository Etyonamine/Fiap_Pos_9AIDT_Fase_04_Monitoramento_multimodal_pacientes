import os
import socket

import pytest


def test_tests_have_no_inherited_azure_credentials():
    assert not any(name.startswith("AZURE_") for name in os.environ)


def test_unmocked_external_network_is_rejected_before_connection():
    with socket.socket() as connection:
        with pytest.raises(AssertionError, match="External network is forbidden"):
            connection.connect(("example.invalid", 443))


def test_isolation_still_allows_local_test_servers():
    with socket.socket() as server:
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        with socket.socket() as client:
            client.settimeout(2)
            client.connect(server.getsockname())
            accepted, _ = server.accept()
            accepted.close()
