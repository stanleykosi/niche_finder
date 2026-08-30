from apps.api.app.sources.fixture_browser import FixtureBrowserSource


def create_fixture_browser(scenario: str = "strong") -> FixtureBrowserSource:
    return FixtureBrowserSource(scenario)

