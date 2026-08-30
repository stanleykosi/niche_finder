from datetime import datetime, timezone

import pytest

from apps.api.app.core.errors import ErrorCode, NicheIntelError
from apps.api.app.sources.quota import QuotaManager, youtube_quota_day
from apps.api.app.core.config import AppMode, Settings
from apps.api.app.db.session import Database


def test_quota_respects_reserved_floor():
    quota = QuotaManager(3, 1)
    quota.consume_search()
    quota.consume_search()
    assert quota.status().remaining_search_calls == 1
    with pytest.raises(NicheIntelError) as error:
        quota.consume_search()
    assert error.value.code == ErrorCode.QUOTA_EXHAUSTED


def test_reserved_call_can_be_consumed_explicitly():
    quota = QuotaManager(2, 1)
    quota.consume_search()
    quota.consume_search(reserve=True)
    assert quota.status().used_search_calls == 2


def test_all_youtube_operations_share_one_unit_ledger():
    quota = QuotaManager(10, 1, daily_unit_budget=110, reserved_units=5)
    quota.consume("search.list", 100)
    quota.consume("videos.list", 1)
    quota.consume("channels.list", 1)
    status = quota.status()
    assert status.used_search_calls == 1
    assert status.used_units == 102
    assert status.remaining_units == 8
    with pytest.raises(NicheIntelError):
        quota.consume("commentThreads.list", 4)


def test_search_availability_includes_search_cost_and_reserved_unit_floor():
    quota = QuotaManager(10, 1, daily_unit_budget=205, reserved_units=100)
    quota.consume("videos.list", 5)
    assert quota.status().remaining_search_calls == 10
    assert quota.status().remaining_units == 200
    assert quota.can_search() is True
    quota.consume("videos.list", 1)
    assert quota.status().remaining_units == 199
    assert quota.can_search() is False
    assert quota.status().can_search is False
    assert quota.can_search(reserve=True) is True


def test_consume_search_accounts_for_the_full_youtube_search_unit_cost():
    quota = QuotaManager(2, 0, daily_unit_budget=200, reserved_units=0)
    quota.consume_search()
    assert quota.status().used_search_calls == 1
    assert quota.status().used_units == 100


def test_database_quota_ledger_is_shared_across_process_managers(tmp_path):
    database = Database(Settings(app_mode=AppMode.DEVELOPMENT, database_url=f"sqlite:///{tmp_path / 'quota.db'}"))
    database.create_schema()
    api_manager = QuotaManager(3, 1, daily_unit_budget=1000, reserved_units=5, engine=database.engine)
    worker_manager = QuotaManager(3, 1, daily_unit_budget=1000, reserved_units=5, engine=database.engine)
    api_manager.consume("search.list", 100)
    worker_manager.consume("videos.list", 1)
    assert api_manager.status().used_search_calls == 1
    assert api_manager.status().used_units == 101
    assert worker_manager.status().used_search_calls == 1
    assert worker_manager.status().remaining_units == 899
    worker_manager.consume("search.list", 1)
    with pytest.raises(NicheIntelError):
        api_manager.consume("search.list", 1)


def test_quota_day_rolls_over_at_pacific_midnight_across_dst():
    assert youtube_quota_day(datetime(2026, 1, 2, 7, 59, tzinfo=timezone.utc)).isoformat() == "2026-01-01"
    assert youtube_quota_day(datetime(2026, 1, 2, 8, 0, tzinfo=timezone.utc)).isoformat() == "2026-01-02"
    assert youtube_quota_day(datetime(2026, 7, 2, 6, 59, tzinfo=timezone.utc)).isoformat() == "2026-07-01"
    assert youtube_quota_day(datetime(2026, 7, 2, 7, 0, tzinfo=timezone.utc)).isoformat() == "2026-07-02"
