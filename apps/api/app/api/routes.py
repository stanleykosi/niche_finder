from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status

from ..core.errors import NicheIntelError
from ..domain.contracts import (
    ChannelAnalysisRequest,
    NicheAnalysisRequest,
    NicheCandidateResponse,
    ReportResponse,
    ResearchRunCreate,
    ResearchRunSummary,
    SourceHealth,
    VideoAnalysisRequest,
)
from ..reports.engine import ReportEngine
from ..repositories.store import ResearchRepository
from ..services.jobs import abort_research_run, enqueue_research_run
from ..services.health import collect_source_health
from ..services.storage_status import read_worker_storage_status

router = APIRouter(prefix="/api")
TERMINAL_RUN_STATUSES = {"complete", "failed", "cancelled"}
logger = logging.getLogger(__name__)


async def repo(request: Request) -> AsyncGenerator[ResearchRepository, None]:
    if request.app.state.settings.is_closed:
        yield request.app.state.orchestrator.repository
        return
    session = request.app.state.db.session()
    try:
        yield ResearchRepository(session)
    finally:
        session.close()


RepositoryDependency = Annotated[ResearchRepository, Depends(repo)]


def summary(run: Any, request: Request) -> ResearchRunSummary:
    return ResearchRunSummary(
        id=UUID(run.id), status=run.status, requested_format=run.requested_format, language=run.language,
        seeds=run.seeds or [], started_at=run.started_at, completed_at=run.completed_at,
        failure_reason=run.failure_reason,
        fixture_mode=bool(run.configuration.get("fixture_mode", request.app.state.settings.uses_fixture_sources)),
        metadata_source=run.configuration.get("metadata_source", request.app.state.settings.metadata_source),
    )


@router.post("/research-runs", response_model=ResearchRunSummary, status_code=status.HTTP_201_CREATED)
async def create_research_run(payload: ResearchRunCreate, request: Request, repository: RepositoryDependency) -> ResearchRunSummary:
    run = repository.create_run(payload)
    run.configuration = {
        **run.configuration,
        "fixture_mode": request.app.state.settings.uses_fixture_sources,
        "metadata_source": request.app.state.settings.metadata_source,
    }
    repository.session.commit()
    if not request.app.state.settings.is_closed:
        task = repository.ensure_task_job(run.id)
        try:
            await enqueue_research_run(
                request.app.state.settings.redis_url,
                run.id,
                attempt=max(1, task.attempts + 1),
            )
        except NicheIntelError as exc:
            repository.update_task_job(run.id, "failed", exc.message)
            repository.transition(run, "failed", exc.message)
            raise HTTPException(status_code=503, detail={"code": exc.code.value, "message": exc.message}) from exc
        return summary(run, request)
    try:
        await request.app.state.orchestrator.execute(run, payload)
    except NicheIntelError as exc:
        raise HTTPException(status_code=422, detail={"code": exc.code.value, "message": exc.message}) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"code": "run_failed", "message": str(exc)}) from exc
    return summary(run, request)


@router.get("/research-runs", response_model=list[ResearchRunSummary])
async def list_research_runs(
    request: Request,
    response: Response,
    repository: RepositoryDependency,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> list[ResearchRunSummary]:
    total = repository.count_runs()
    runs = repository.list_runs(limit=limit, offset=offset)
    response.headers["X-Total-Count"] = str(total)
    response.headers["X-Pagination-Limit"] = str(limit)
    response.headers["X-Pagination-Offset"] = str(offset)
    links: list[str] = []
    if offset + len(runs) < total:
        next_url = request.url.include_query_params(limit=limit, offset=offset + limit)
        links.append(f'<{next_url}>; rel="next"')
    if offset > 0:
        previous_url = request.url.include_query_params(limit=limit, offset=max(0, offset - limit))
        links.append(f'<{previous_url}>; rel="prev"')
    if links:
        response.headers["Link"] = ", ".join(links)
    return [summary(run, request) for run in runs]


@router.get("/research-runs/{run_id}", response_model=ResearchRunSummary)
async def get_research_run(run_id: UUID, request: Request, repository: RepositoryDependency) -> ResearchRunSummary:
    run = repository.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="research run not found")
    return summary(run, request)


@router.post("/research-runs/{run_id}/cancel", response_model=ResearchRunSummary)
async def cancel_research_run(run_id: UUID, request: Request, repository: RepositoryDependency) -> ResearchRunSummary:
    run = repository.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="research run not found")
    if run.status in TERMINAL_RUN_STATUSES:
        return summary(run, request)
    if not request.app.state.settings.is_closed:
        task = repository.task_job(run.id)
        try:
            await abort_research_run(
                request.app.state.settings.redis_url,
                run.id,
                attempt=max(1, task.attempts if task is not None else 1),
            )
        except Exception:
            # The queue entry may already be gone after a container restart.
            # Database cancellation remains authoritative and the orchestrator
            # checks it between durable steps.
            logger.exception("queue abort failed; applying durable run cancellation")
        run, cancelled = repository.cancel_run_if_active(run.id, "research run cancelled by user")
        if cancelled:
            repository.update_task_job(run.id, "cancelled")
    else:
        request.app.state.orchestrator.cancel(run)
    return summary(run, request)


@router.post("/research-runs/{run_id}/resume", response_model=ResearchRunSummary)
async def resume_research_run(run_id: UUID, request: Request, repository: RepositoryDependency) -> ResearchRunSummary:
    run = repository.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="research run not found")
    if run.status in {"complete", "cancelled"}:
        raise HTTPException(status_code=409, detail=f"a {run.status} run cannot be resumed")
    if request.app.state.settings.is_closed:
        run = repository.prepare_run_for_resume(run.id)
        try:
            await request.app.state.orchestrator.execute(run)
        except NicheIntelError as exc:
            raise HTTPException(status_code=422, detail={"code": exc.code.value, "message": exc.message}) from exc
        return summary(run, request)

    task = repository.ensure_task_job(run.id)
    if run.status not in TERMINAL_RUN_STATUSES:
        try:
            await abort_research_run(
                request.app.state.settings.redis_url,
                run.id,
                attempt=max(1, task.attempts),
            )
        except Exception:
            logger.exception("stale queue entry could not be aborted before resume")
    run = repository.prepare_run_for_resume(run.id)
    repository.update_task_job(run.id, "queued")
    try:
        await enqueue_research_run(
            request.app.state.settings.redis_url,
            run.id,
            attempt=max(1, task.attempts + 1),
        )
    except NicheIntelError as exc:
        repository.update_task_job(run.id, "failed", exc.message)
        repository.transition(run, "failed", exc.message)
        raise HTTPException(status_code=503, detail={"code": exc.code.value, "message": exc.message}) from exc
    return summary(run, request)


@router.get("/research-runs/{run_id}/candidates", response_model=list[NicheCandidateResponse])
async def get_candidates(run_id: UUID, repository: RepositoryDependency) -> list[dict[str, Any]]:
    try:
        return ReportEngine(repository).build(str(run_id))["candidates"]
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="research run not found") from exc


@router.get("/research-runs/{run_id}/evidence")
async def get_evidence(run_id: UUID, repository: RepositoryDependency) -> list[dict[str, Any]]:
    if repository.get_run(run_id) is None:
        raise HTTPException(status_code=404, detail="research run not found")
    return [
        {"id": item.id, "evidence_type": item.evidence_type, "source_type": item.source_type,
         "observed_at": item.observed_at, "payload": item.payload, "confidence": item.confidence,
         "human_readable_summary": item.human_readable_summary}
        for item in repository.get_evidence(str(run_id))
    ]


@router.get("/research-runs/{run_id}/report", response_model=ReportResponse)
async def get_report(run_id: UUID, repository: RepositoryDependency) -> dict[str, Any]:
    try:
        return ReportEngine(repository).build(str(run_id))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="research run not found") from exc


async def _direct_analysis(seed: str, request: Request, repository: ResearchRepository, requested_format: str = "both") -> ResearchRunSummary:
    payload = ResearchRunCreate(seeds=[seed], requested_format=requested_format)
    return await create_research_run(payload, request, repository)


@router.post("/analyse/video", response_model=ResearchRunSummary)
async def analyse_video(payload: VideoAnalysisRequest, request: Request, repository: RepositoryDependency) -> ResearchRunSummary:
    return await _direct_analysis(payload.url, request, repository)


@router.post("/analyse/channel", response_model=ResearchRunSummary)
async def analyse_channel(payload: ChannelAnalysisRequest, request: Request, repository: RepositoryDependency) -> ResearchRunSummary:
    return await _direct_analysis(payload.url, request, repository)


@router.post("/analyse/niche", response_model=ResearchRunSummary)
async def analyse_niche(payload: NicheAnalysisRequest, request: Request, repository: RepositoryDependency) -> ResearchRunSummary:
    return await _direct_analysis(payload.niche, request, repository, payload.requested_format.value)


@router.get("/channels/{channel_id}")
async def get_channel(channel_id: str, repository: RepositoryDependency) -> dict[str, Any]:
    channel = repository.session.query(__import__("apps.api.app.db.models", fromlist=["Channel"]).Channel).filter_by(youtube_channel_id=channel_id).first()
    if channel is None:
        raise HTTPException(status_code=404, detail="channel not found")
    return {"id": channel.id, "youtube_channel_id": channel.youtube_channel_id, "title": channel.title, "description": channel.description, "canonical_url": channel.canonical_url}


@router.get("/videos/{video_id}")
async def get_video(video_id: str, repository: RepositoryDependency) -> dict[str, Any]:
    models = __import__("apps.api.app.db.models", fromlist=["Video"])
    video = repository.session.query(models.Video).filter_by(youtube_video_id=video_id).first()
    if video is None:
        raise HTTPException(status_code=404, detail="video not found")
    return {"id": video.id, "youtube_video_id": video.youtube_video_id, "title": video.title, "canonical_url": video.canonical_url, "published_at": video.published_at}


@router.get("/system/source-health", response_model=list[SourceHealth])
async def source_health(request: Request) -> list[SourceHealth]:
    return await collect_source_health(request.app.state.settings, request.app.state.orchestrator.ai)


@router.get("/system/quota")
async def quota(request: Request) -> dict[str, Any]:
    return request.app.state.orchestrator.quota.status().model_dump(mode="json")


@router.get("/system/storage")
async def storage_status(request: Request) -> dict[str, Any]:
    if request.app.state.settings.is_closed:
        return {
            **request.app.state.orchestrator.artifacts.status(),
            "status_source": "api_closed_test",
        }
    try:
        result = await read_worker_storage_status(request.app.state.settings.redis_url)
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="worker storage status is unavailable",
        ) from exc
    if result is None:
        raise HTTPException(status_code=503, detail="worker storage status has not been published")
    return result


@router.get("/research-runs/{run_id}/artifacts")
async def run_artifacts(run_id: UUID, repository: RepositoryDependency) -> list[dict[str, Any]]:
    if repository.get_run(run_id) is None:
        raise HTTPException(status_code=404, detail="research run not found")
    return [
        {
            "id": item.id, "artifact_type": item.artifact_type, "path": item.path,
            "sha256": item.sha256, "size_bytes": item.size_bytes, "state": item.state,
            "metadata": item.metadata_payload, "created_at": item.created_at,
            "expires_at": item.expires_at, "deleted_at": item.deleted_at,
        }
        for item in repository.runtime_artifacts(str(run_id))
    ]
