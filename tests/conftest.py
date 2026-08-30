from apps.api.app.core.network import install_closed_network_guard


def pytest_sessionstart(session):  # noqa: ARG001
    install_closed_network_guard()

