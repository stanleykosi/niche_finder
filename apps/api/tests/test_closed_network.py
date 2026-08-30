import socket

import pytest

from apps.api.app.core.network import ClosedNetworkError


def test_external_connection_is_blocked_in_closed_suite():
    with pytest.raises(ClosedNetworkError):
        socket.create_connection(("example.com", 80), timeout=0.1)

