"""Share worker-owned runtime storage measurements with the API via Redis."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any


WORKER_STORAGE_STATUS_KEY = "nicheintel:worker:storage-status:v1"


async def publish_worker_storage_status(redis: Any, status: dict[str, Any]) -> dict[str, Any]:
    payload = {
        **status,
        "status_source": "worker",
        "observed_at": datetime.now(timezone.utc).isoformat(),
    }
    await redis.set(WORKER_STORAGE_STATUS_KEY, json.dumps(payload, sort_keys=True))
    return payload


async def read_worker_storage_status(
    redis_url: str,
    *,
    redis: Any | None = None,
) -> dict[str, Any] | None:
    owned_client = redis is None
    client = redis
    if client is None:
        from redis.asyncio import Redis

        client = Redis.from_url(
            redis_url,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
    try:
        raw = await client.get(WORKER_STORAGE_STATUS_KEY)
        if raw is None:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        payload = json.loads(raw)
        return payload if isinstance(payload, dict) else None
    finally:
        if owned_client:
            await client.aclose()
