"""ARQ-compatible worker entry point; closed MVP runs synchronously through the API."""

import asyncio
import logging

from apps.api.app.core.config import load_settings
from apps.api.app.core.network import install_closed_network_guard
from apps.api.app.db.schema_gate import wait_for_migrations
from apps.api.app.db.session import Database
from apps.api.app.repositories.store import ResearchRepository
from apps.api.app.services.factory import create_orchestrator
from apps.api.app.services.jobs import research_job_id
from apps.api.app.services.storage_status import publish_worker_storage_status
from apps.api.app.storage.artifacts import RuntimeArtifactManager


logger = logging.getLogger(__name__)


async def run_research(ctx: dict, run_id: str) -> str:
    # ARQ may execute multiple coroutines in one worker. A synchronous
    # SQLAlchemy Session and a ResearchOrchestrator are strictly job-scoped.
    repository = ResearchRepository(ctx["database"].session())
    try:
        run = repository.get_run(run_id)
        if run is None:
            raise ValueError(f"unknown run {run_id}")
        if run.status in {"complete", "cancelled"}:
            repository.update_task_job(run_id, run.status, run.failure_reason)
            return run_id
        task = repository.task_job(run_id)
        retrying = run.status != "queued" or bool(task and task.attempts > 0)
        if retrying:
            run = repository.prepare_run_for_resume(run_id)
        repository.update_task_job(run_id, "running", increment_attempt=True)
        try:
            orchestrator = create_orchestrator(ctx["settings"], repository)
            if retrying:
                orchestrator.artifacts.cleanup_run_temporary(run_id)
            await orchestrator.execute(run)
        except asyncio.CancelledError:
            # ARQ uses cancellation both for an explicit abort and for normal
            # SIGTERM/redelivery during a Railway deploy. Only the API-written
            # database state proves user intent; a platform interruption must
            # leave the run recoverable for ARQ's retry or startup recovery.
            repository.session.expire_all()
            persisted = repository.get_run(run_id)
            if persisted is not None and persisted.status == "cancelled":
                repository.update_task_job(run_id, "cancelled")
            else:
                repository.update_task_job(
                    run_id,
                    "queued",
                    "worker interrupted; awaiting checkpoint redelivery",
                )
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
        if ctx.get("redis") is not None:
            try:
                await _publish_worker_storage(ctx, cleanup=False)
            except Exception:
                logger.exception("failed to publish worker storage status")


def create_worker_context() -> dict:
    settings = load_settings()
    if settings.is_closed and settings.closed_test_block_network:
        install_closed_network_guard()
    db = Database(settings)
    if settings.bootstrap_schema_on_startup:
        db.create_schema()
    return {"settings": settings, "database": db}


def _measure_worker_storage(ctx: dict, *, cleanup: bool) -> dict:
    repository = ResearchRepository(ctx["database"].session())
    try:
        manager = RuntimeArtifactManager(ctx["settings"], repository, storage_owner=True)
        if cleanup:
            manager.cleanup_expired()
        return manager.status()
    finally:
        repository.session.close()


async def _publish_worker_storage(ctx: dict, *, cleanup: bool) -> None:
    status = await asyncio.to_thread(_measure_worker_storage, ctx, cleanup=cleanup)
    redis = ctx.get("redis")
    if redis is None:
        return
    await publish_worker_storage_status(redis, status)


async def startup(ctx: dict) -> None:
    worker_context = create_worker_context()
    settings = worker_context["settings"]
    database = worker_context["database"]
    try:
        if not settings.bootstrap_schema_on_startup:
            await asyncio.to_thread(
                wait_for_migrations,
                database.engine,
                timeout_seconds=settings.migration_wait_timeout_seconds,
                poll_interval_seconds=settings.migration_poll_interval_seconds,
            )
    except Exception:
        database.engine.dispose()
        raise
    ctx.update(worker_context)
    await _publish_worker_storage(ctx, cleanup=True)
    await _recover_interrupted_runs(ctx)


async def _recover_interrupted_runs(ctx: dict) -> None:
    """Requeue work left active when the single Railway worker restarted."""
    redis = ctx.get("redis")
    if redis is None:
        return
    repository = ResearchRepository(ctx["database"].session())
    try:
        recoverable = repository.recoverable_runs()
        for run in recoverable:
            task = repository.ensure_task_job(run.id)
            next_attempt = max(1, task.attempts + 1)
            if run.status == "queued":
                from arq.jobs import Job

                current_attempt = max(1, task.attempts)
                job_ids = [research_job_id(run.id, current_attempt), f"research:{run.id}"]
                queued = False
                for job_id in job_ids:
                    try:
                        status = await Job(job_id, redis).status()
                    except Exception:
                        continue
                    status_value = getattr(status, "value", str(status)).lower()
                    if status_value in {"queued", "deferred"}:
                        queued = True
                        break
                if queued:
                    continue
            await redis.enqueue_job(
                "run_research",
                run.id,
                _job_id=research_job_id(run.id, next_attempt),
            )
            repository.update_task_job(run.id, "queued")
            logger.warning(
                "requeued interrupted research run",
                extra={
                    "research_run_id": run.id,
                    "stage": run.status,
                    "attempt": next_attempt,
                },
            )
    finally:
        repository.session.close()


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
    # Chromium, embeddings and video analysis are intentionally serialized in
    # this 2 GB worker. Parallel runs multiply memory, not throughput.
    max_jobs = 1
    max_tries = 5
    allow_abort_jobs = True
    job_timeout = 14400
    keep_result = 600


if __name__ == "__main__":
    print("run with: arq workers.research.worker.WorkerSettings")
