"""A small opt-in network guard for closed tests and local fixture runs."""

from __future__ import annotations

import socket
from typing import Any


class ClosedNetworkError(OSError):
    pass


_original_connect = socket.socket.connect
_original_create_connection = socket.create_connection


def install_closed_network_guard() -> None:
    def blocked_connect(self: socket.socket, address: Any) -> Any:
        host = address[0] if isinstance(address, tuple) and address else address
        if host in {"127.0.0.1", "localhost", "::1"}:
            return _original_connect(self, address)
        raise ClosedNetworkError(f"external networking blocked in closed_test: {host}")

    def blocked_create_connection(address: Any, *args: Any, **kwargs: Any) -> Any:
        host = address[0] if isinstance(address, tuple) and address else address
        if host in {"127.0.0.1", "localhost", "::1"}:
            return _original_create_connection(address, *args, **kwargs)
        raise ClosedNetworkError(f"external networking blocked in closed_test: {host}")

    socket.socket.connect = blocked_connect  # type: ignore[method-assign]
    socket.create_connection = blocked_create_connection  # type: ignore[assignment]


def uninstall_closed_network_guard() -> None:
    socket.socket.connect = _original_connect  # type: ignore[method-assign]
    socket.create_connection = _original_create_connection  # type: ignore[assignment]

