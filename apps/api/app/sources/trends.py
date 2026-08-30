"""Optional external trend corroboration through a small HTTP/MCP bridge contract."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Protocol

import httpx

from ..core.config import AppMode
from ..core.errors import ClosedModeViolation


class TrendConnector(Protocol):
    async def assess(self, queries: list[str], regions: list[str], window_days: int) -> dict[str, Any]: ...


class DisabledTrendConnector:
    async def assess(self, queries: list[str], regions: list[str], window_days: int) -> dict[str, Any]:
        return {"enabled": False, "status": "not_configured", "score": None, "observations": [], "weight": 0}


class HttpTrendConnector:
    """Calls a user-controlled bridge that can front Google Trends alpha or an MCP server."""

    def __init__(self, mode: AppMode, url: str, api_key: str | None = None) -> None:
        if mode == AppMode.CLOSED_TEST:
            raise ClosedModeViolation("external trends are disabled in closed mode")
        self.url = url
        self.api_key = api_key

    async def assess(self, queries: list[str], regions: list[str], window_days: int) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        try:
            async with httpx.AsyncClient(timeout=25) as client:
                response = await client.post(self.url, json={"queries": queries, "regions": regions, "window_days": window_days}, headers=headers)
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise ValueError("external trend bridge payload must be an object")
            score = float(payload["score"])
            if not 0 <= score <= 1:
                raise ValueError("external trend bridge score must be between 0 and 1")
        except (httpx.HTTPError, ValueError, TypeError, KeyError) as exc:
            error: dict[str, Any] = {"type": type(exc).__name__}
            if isinstance(exc, httpx.HTTPStatusError):
                error["status_code"] = exc.response.status_code
            return {
                "enabled": True,
                "status": "unavailable",
                "score": None,
                "observations": [],
                "source": self.url,
                "observed_at": datetime.now(timezone.utc).isoformat(),
                "weight": 0,
                "error": error,
            }
        return {"enabled": True, "status": "observed", "score": score, "observations": payload.get("observations", []), "source": payload.get("source", self.url), "observed_at": payload.get("observed_at", datetime.now(timezone.utc).isoformat()), "weight": .15}
