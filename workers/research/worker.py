"""ARQ-compatible worker entry point; closed MVP runs synchronously through the API."""

import asyncio

from apps.api.app.core.config import load_settings
from apps.api.app.core.network import install_closed_network_guard
from apps.api.app.db.session import Database
from apps.api.app.repositories.store import ResearchRepository
from apps.api.app.services.factory import create_orchestrator


async def run_research(ctx: dict, run_id: str) -> str:
    # ARQ may execute multiple coroutines in one worker. A synchronous
    # SQLAlchemy Session and a ResearchOrchestrator are strictly job-scoped.
    repository = ResearchRepository(ctx["database"].session())
    try:
        run = repository.get_run(run_id)
        if run is None:
            raise ValueError(f"unknown run {run_id}")
        if run.status in {"complete", "failed", "cancelled"}:
            repository.update_task_job(run_id, run.status, run.failure_reason)
            return run_id
        retrying = run.status != "queued"
        if retrying:
            run = repository.reset_run_outputs_for_retry(run_id)
        repository.update_task_job(run_id, "running", increment_attempt=True)
        try:
            orchestrator = create_orchestrator(ctx["settings"], repository)
            if retrying:
                orchestrator.artifacts.cleanup_run_temporary(run_id)
            await orchestrator.execute(run)
        except asyncio.CancelledError:
            if run.status != "cancelled":
                repository.transition(run, "cancelled", "research job aborted")
            repository.update_task_job(run_id, "cancelled")
            raise
        except Exception as exc:
            if run.status not in {"failed", "cancelled"}:
                repository.transition(run, "failed", str(exc))
            repository.update_task_job(run_id, "failed", str(exc))
            raise
        repository.update_task_job(run_id, "complete")
        return run_id
    finally:
        repository.session.close()


def create_worker_context() -> dict:
    settings = load_settings()
    if settings.is_closed and settings.closed_test_block_network:
        install_closed_network_guard()
    db = Database(settings)
    db.create_schema()
    return {"settings": settings, "database": db}


async def startup(ctx: dict) -> None:
    ctx.update(create_worker_context())


async def shutdown(ctx: dict) -> None:
    database = ctx.get("database")
    if database is not None:
        database.engine.dispose()


class WorkerSettings:
    from arq.connections import RedisSettings

    functions = [run_research]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(load_settings().redis_url)
    max_jobs = 2
    allow_abort_jobs = True
    job_timeout = 3600
    keep_result = 300


if __name__ == "__main__":
    print("run with: arq workers.research.worker.WorkerSettings")
