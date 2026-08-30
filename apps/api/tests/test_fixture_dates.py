from datetime import date

from apps.api.app.sources.fixture_youtube import FixtureYoutubeSource


def test_fixture_dates_shift_with_the_run_date_instead_of_aging_forever():
    source = FixtureYoutubeSource("strong")
    anchor = date.fromisoformat(source.payload["fixture_anchor_date"])
    original = date.fromisoformat(source.videos["v-bridge-01"]["published_at"][:10])
    shifted = __import__("asyncio").run(source.enrich_videos(["v-bridge-01"]))[0].published_at.date()
    assert (date.today() - shifted).days == (anchor - original).days
