"""ARQ submission boundary for non-closed research runs."""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from ..core.errors import ErrorCode, NicheIntelError


async def enqueue_research_run(
    redis_url: str,
    run_id: str,
    pool_factory: Callable[[str], Awaitable[Any]] | None = None,
    *,
    attempt: int = 1,
) -> str:
    factory = pool_factory or _create_pool
    pool = await factory(redis_url)
    job_id = research_job_id(run_id, attempt)
    try:
        job = await pool.enqueue_job("run_research", run_id, _job_id=job_id)
        # ARQ returns None when the idempotency key already exists. The run is
        # still queued/running in that case, so duplicate submission is safe.
        return getattr(job, "job_id", None) or job_id
    except Exception as exc:
        raise NicheIntelError(f"research queue submission failed: {exc}", ErrorCode.SOURCE_UNAVAILABLE) from exc
    finally:
        close = getattr(pool, "aclose", None)
        if close is not None:
            await close()
        else:  # ARQ/redis compatibility for older deployments
            await pool.close(close_connection_pool=True)


async def _create_pool(redis_url: str) -> Any:
    from arq import create_pool
    from arq.connections import RedisSettings

    return await create_pool(RedisSettings.from_dsn(redis_url))


async def abort_research_run(
    redis_url: str,
    run_id: str,
    pool_factory: Callable[[str], Awaitable[Any]] | None = None,
    *,
    attempt: int = 1,
) -> bool:
    factory = pool_factory or _create_pool
    pool = await factory(redis_url)
    try:
        from arq.jobs import Job

        aborted = False
        for job_id in (research_job_id(run_id, attempt), f"research:{run_id}"):
            try:
                aborted = bool(await Job(job_id, pool).abort(timeout=5)) or aborted
            except Exception:
                # Missing/stale queue keys are expected after a container
                # restart; continue so the legacy ID still gets a chance.
                continue
        return aborted
    finally:
        close = getattr(pool, "aclose", None)
        if close is not None:
            await close()
        else:
            await pool.close(close_connection_pool=True)


def research_job_id(run_id: str, attempt: int) -> str:
    return f"research:{run_id}:attempt:{max(1, int(attempt))}"
