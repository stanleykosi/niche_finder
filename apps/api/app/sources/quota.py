from __future__ import annotations

from datetime import date, datetime, timezone
from threading import RLock
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import Engine, and_, insert, select, update
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from ..core.errors import NicheIntelError, ErrorCode
from ..db.models import QuotaLedger, utc_now
from ..domain.contracts import QuotaStatus


YOUTUBE_QUOTA_TIMEZONE = ZoneInfo("America/Los_Angeles")
YOUTUBE_SEARCH_UNIT_COST = 100


def youtube_quota_day(observed_at: datetime | None = None) -> date:
    """Return YouTube's quota ledger day (midnight in Pacific Time)."""
    observed = observed_at or datetime.now(timezone.utc)
    if observed.tzinfo is None:
        observed = observed.replace(tzinfo=timezone.utc)
    return observed.astimezone(YOUTUBE_QUOTA_TIMEZONE).date()


class QuotaManager:
    """Daily quota ledger, persisted atomically when a database engine is supplied."""

    def __init__(
        self,
        daily_budget: int = 100,
        reserved_search_calls: int = 20,
        daily_unit_budget: int = 10000,
        reserved_units: int = 500,
        engine: Engine | None = None,
    ) -> None:
        if reserved_search_calls > daily_budget:
            raise ValueError("reserved search calls cannot exceed daily budget")
        self.daily_budget = daily_budget
        self.reserved_search_calls = reserved_search_calls
        self.used_search_calls = 0
        self.daily_unit_budget = daily_unit_budget
        self.reserved_units = reserved_units
        self.used_units = 0
        self._day = youtube_quota_day()
        self._lock = RLock()
        self._engine = engine

    def _reset_if_needed(self) -> None:
        today = youtube_quota_day()
        if today != self._day:
            self._day = today
            self.used_search_calls = 0
            self.used_units = 0

    def can_search(self, reserve: bool = False) -> bool:
        status = self.status()
        call_capacity = status.remaining_search_calls > 0 and (
            reserve or status.remaining_search_calls > self.reserved_search_calls
        )
        unit_floor = 0 if reserve else self.reserved_units
        unit_capacity = status.remaining_units >= YOUTUBE_SEARCH_UNIT_COST + unit_floor
        return call_capacity and unit_capacity

    def consume_search(self, reserve: bool = False) -> None:
        self.consume("search.list", YOUTUBE_SEARCH_UNIT_COST, reserve=reserve)

    def consume(self, operation: str, units: int, reserve: bool = False) -> None:
        """Account for every Data API operation in one shared daily unit ledger."""
        if operation == "search.list":
            # Callers cannot weaken YouTube's published search cost by passing
            # a smaller value into the shared ledger boundary.
            units = YOUTUBE_SEARCH_UNIT_COST
        if units < 0:
            raise NicheIntelError(f"YouTube quota unit floor reached before {operation}", ErrorCode.QUOTA_EXHAUSTED)
        if self._engine is not None:
            self._consume_persisted(operation, search_calls=int(operation == "search.list"), units=units, reserve=reserve)
            return
        with self._lock:
            self._reset_if_needed()
            remaining = self.daily_unit_budget - self.used_units
            if units < 0 or remaining < units or (not reserve and remaining - units < self.reserved_units):
                raise NicheIntelError(f"YouTube quota unit floor reached before {operation}", ErrorCode.QUOTA_EXHAUSTED)
            if operation == "search.list" and not self.can_search(reserve=reserve):
                raise NicheIntelError("YouTube search budget is at its reserved floor", ErrorCode.QUOTA_EXHAUSTED)
            self.used_units += units
            if operation == "search.list":
                self.used_search_calls += 1

    def status(self) -> QuotaStatus:
        if self._engine is not None:
            with self._engine.connect() as connection:
                row = connection.execute(
                    select(QuotaLedger.used_search_calls, QuotaLedger.used_units).where(QuotaLedger.ledger_date == youtube_quota_day())
                ).one_or_none()
            used_search_calls, used_units = row if row is not None else (0, 0)
            return self._status(int(used_search_calls), int(used_units))
        with self._lock:
            self._reset_if_needed()
            return self._status(self.used_search_calls, self.used_units)

    def _consume_persisted(self, operation: str, search_calls: int, units: int, reserve: bool) -> None:
        """Atomically reserve quota in the shared database before a source request."""
        assert self._engine is not None
        ledger_date = youtube_quota_day()
        table = QuotaLedger.__table__
        with self._engine.begin() as connection:
            values: dict[str, Any] = {
                "ledger_date": ledger_date,
                "used_search_calls": 0,
                "used_units": 0,
                "updated_at": utc_now(),
            }
            if connection.dialect.name == "postgresql":
                connection.execute(postgres_insert(table).values(**values).on_conflict_do_nothing(index_elements=["ledger_date"]))
            elif connection.dialect.name == "sqlite":
                connection.execute(sqlite_insert(table).values(**values).on_conflict_do_nothing(index_elements=["ledger_date"]))
            else:
                existing = connection.execute(select(table.c.ledger_date).where(table.c.ledger_date == ledger_date)).first()
                if existing is None:
                    connection.execute(insert(table).values(**values))

            conditions = [table.c.ledger_date == ledger_date]
            if search_calls:
                search_limit = self.daily_budget if reserve else self.daily_budget - self.reserved_search_calls
                conditions.append(table.c.used_search_calls + search_calls <= search_limit)
            if units:
                unit_limit = self.daily_unit_budget if reserve else self.daily_unit_budget - self.reserved_units
                conditions.append(table.c.used_units + units <= unit_limit)
            result = connection.execute(
                update(table)
                .where(and_(*conditions))
                .values(
                    used_search_calls=table.c.used_search_calls + search_calls,
                    used_units=table.c.used_units + units,
                    updated_at=utc_now(),
                )
            )
            if result.rowcount != 1:
                message = "YouTube search budget is at its reserved floor" if search_calls else f"YouTube quota unit floor reached before {operation}"
                raise NicheIntelError(message, ErrorCode.QUOTA_EXHAUSTED)

    def _status(self, used_search_calls: int, used_units: int) -> QuotaStatus:
        remaining = max(self.daily_budget - used_search_calls, 0)
        remaining_units = max(self.daily_unit_budget - used_units, 0)
        return QuotaStatus(
            daily_budget=self.daily_budget,
            reserved_search_calls=self.reserved_search_calls,
            used_search_calls=used_search_calls,
            remaining_search_calls=remaining,
            can_search=(
                remaining > self.reserved_search_calls
                and remaining_units >= YOUTUBE_SEARCH_UNIT_COST + self.reserved_units
            ),
            daily_unit_budget=self.daily_unit_budget,
            reserved_units=self.reserved_units,
            used_units=used_units,
            remaining_units=remaining_units,
        )
