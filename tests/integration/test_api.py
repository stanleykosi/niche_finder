import asyncio
import inspect
from datetime import datetime, timezone

import httpx

from apps.api.app.core.config import AppMode, Settings
from apps.api.app.db.session import Database
from apps.api.app.main import create_app
from apps.api.app.api import routes
from apps.api.app.repositories.store import ResearchRepository
from apps.api.app.storage.artifacts import RuntimeArtifactManager


def test_api_boundary_creates_and_reads_closed_run(tmp_path):
    settings = Settings(app_mode=AppMode.CLOSED_TEST, ai_provider="fake", database_url=f"sqlite:///{tmp_path / 'api.db'}")
    app = create_app(settings)

    async def exercise():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            created = await client.post("/api/research-runs", json={"requested_format":"both","language":"English","regions":["US"],"seeds":["paper bridge"],"broad_discovery":False,"recency_days":90,"production_constraints":[],"minimum_idea_ceiling":12,"maximum_saturation":.75,"limits":{"max_queries":2,"max_results_per_query":12,"max_channels":6,"max_videos":12,"max_expansion_depth":0,"deep_research":False}})
            assert created.status_code == 201, created.text
            assert created.json()["metadata_source"] == "fixture_api"
            run_id = created.json()["id"]
            report = await client.get(f"/api/research-runs/{run_id}/report")
            assert report.status_code == 200
            assert report.json()["fixture_mode"] is True
            assert report.json()["metadata_source"] == "fixture_api"
            evidence = await client.get(f"/api/research-runs/{run_id}/evidence")
            assert evidence.status_code == 200 and evidence.json()
            assert (await client.get("/api/system/source-health")).status_code == 200
            missing = await client.get("/api/research-runs/00000000-0000-0000-0000-000000000000/candidates")
            assert missing.status_code == 404
    asyncio.run(exercise())


def test_direct_analysis_endpoints_reject_wrong_resource_types(tmp_path):
    app = create_app(Settings(
        app_mode=AppMode.CLOSED_TEST,
        ai_provider="fake",
        database_url=f"sqlite:///{tmp_path / 'direct-validation.db'}",
    ))

    async def exercise():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            cases = [
                ("/api/analyse/video", {"url": "https://www.youtube.com/@channel"}),
                ("/api/analyse/video", {"url": "https://example.com/watch?v=abc123"}),
                ("/api/analyse/channel", {"url": "https://www.youtube.com/watch?v=abc123"}),
                ("/api/analyse/channel", {"url": "   "}),
            ]
            for endpoint, payload in cases:
                response = await client.post(endpoint, json=payload)
                assert response.status_code == 422, response.text

    asyncio.run(exercise())
    assert app.state.orchestrator.repository.count_runs() == 0


def test_non_closed_api_returns_queued_run_without_executing_pipeline(tmp_path, monkeypatch):
    queued = []

    async def fake_enqueue(redis_url, run_id, **kwargs):
        queued.append((redis_url, run_id))
        return f"research:{run_id}"

    monkeypatch.setattr(routes, "enqueue_research_run", fake_enqueue)
    settings = Settings(app_mode=AppMode.DEVELOPMENT, ai_provider="fake", redis_url="redis://fixture", database_url=f"sqlite:///{tmp_path / 'queued.db'}")
    app = create_app(settings)

    async def exercise():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.post("/api/research-runs", json={"seeds": ["paper bridge"]})
            assert response.status_code == 201
            assert response.json()["status"] == "queued"
            assert response.json()["fixture_mode"] is True
            assert response.json()["metadata_source"] == "fixture_api"
            run_id = response.json()["id"]
            assert queued == [("redis://fixture", run_id)]
            session = app.state.db.session()
            try:
                repository = routes.ResearchRepository(session)
                assert repository.get_run(run_id).status == "queued"
                assert repository.get_candidates(run_id) == []
            finally:
                session.close()

            health = await client.get("/api/system/source-health")
            assert [item["source"] for item in health.json()[:2]] == ["fixture_browser", "fixture_api"]

    asyncio.run(exercise())


def test_closed_service_installs_network_guard(tmp_path, monkeypatch):
    installed = []
    monkeypatch.setattr("apps.api.app.main.install_closed_network_guard", lambda: installed.append(True))
    create_app(Settings(app_mode=AppMode.CLOSED_TEST, database_url=f"sqlite:///{tmp_path / 'guard.db'}"))
    assert installed == [True]


def test_configured_vercel_origin_passes_cors_preflight(tmp_path):
    origin = "https://niche-intel.vercel.app"
    app = create_app(Settings(
        app_mode=AppMode.CLOSED_TEST,
        database_url=f"sqlite:///{tmp_path / 'cors.db'}",
        cors_allowed_origins=(origin,),
    ))

    async def exercise():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.options(
                "/api/research-runs",
                headers={
                    "Origin": origin,
                    "Access-Control-Request-Method": "GET",
                },
            )
            assert response.status_code == 200
            assert response.headers["access-control-allow-origin"] == origin

    asyncio.run(exercise())


def test_non_closed_api_reports_worker_storage_without_touching_local_artifact_roots(
    tmp_path,
    monkeypatch,
):
    media_root = tmp_path / "runtime" / "worker_media"
    browser_root = tmp_path / "runtime" / "worker_browser"
    expected = {
        "status_source": "worker",
        "observed_at": "2026-08-31T12:00:00+00:00",
        "usage_bytes": 321,
    }

    async def worker_status(redis_url):
        assert redis_url == "redis://shared/0"
        return expected

    monkeypatch.setattr(routes, "read_worker_storage_status", worker_status)
    app = create_app(Settings(
        app_mode=AppMode.DEVELOPMENT,
        database_url=f"sqlite:///{tmp_path / 'storage-control.db'}",
        redis_url="redis://shared/0",
        media_work_root=str(media_root),
        browser_profile_root=str(browser_root),
    ))
    assert not media_root.exists()
    assert not browser_root.exists()

    async def exercise():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.get("/api/system/storage")
            assert response.status_code == 200
            assert response.json() == expected

    asyncio.run(exercise())
    assert not media_root.exists()
    assert not browser_root.exists()


def test_worker_cleanup_removes_legacy_browser_state_but_retains_fresh_evidence_images(
    tmp_path,
):
    runtime_root = tmp_path / "runtime"
    settings = Settings(
        app_mode=AppMode.CLOSED_TEST,
        ai_provider="fake",
        database_url=f"sqlite:///{tmp_path / 'artifact-cleanup.db'}",
        media_work_root=str(runtime_root / "media"),
        browser_profile_root=str(runtime_root / "browser"),
    )
    database = Database(settings)
    database.create_schema()
    repository = ResearchRepository(database.session())
    manager = RuntimeArtifactManager(settings, repository)
    legacy_profile = manager.browser_root / "research-interrupted-3"
    legacy_profile.mkdir(parents=True)
    (legacy_profile / "Cookies").write_text("browser cache", encoding="utf-8")
    (legacy_profile / "SingletonLock").symlink_to("stale-container-3225")
    screenshot = legacy_profile / "video-example-0.png"
    screenshot.write_bytes(b"retained evidence")

    result = manager.cleanup_expired(datetime.now(timezone.utc))

    assert result.files_deleted == 2
    assert not (legacy_profile / "Cookies").exists()
    assert not (legacy_profile / "SingletonLock").exists()
    assert screenshot.read_bytes() == b"retained evidence"
    repository.session.close()
    database.engine.dispose()


def test_non_closed_request_repository_session_is_closed(tmp_path):
    assert inspect.isasyncgenfunction(routes.repo)
    app = create_app(Settings(app_mode=AppMode.DEVELOPMENT, ai_provider="fake", database_url=f"sqlite:///{tmp_path / 'sessions.db'}"))
    session_factory = app.state.db.session
    closed_sessions = []

    def tracked_session():
        session = session_factory()
        original_close = session.close

        def close():
            closed_sessions.append(session)
            original_close()

        session.close = close
        return session

    app.state.db.session = tracked_session

    async def exercise():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.get("/api/research-runs")
            assert response.status_code == 200

    asyncio.run(asyncio.wait_for(exercise(), timeout=10))
    assert len(closed_sessions) == 1


def test_run_listing_exposes_stable_limit_offset_pagination(tmp_path):
    app = create_app(Settings(
        app_mode=AppMode.CLOSED_TEST,
        ai_provider="fake",
        database_url=f"sqlite:///{tmp_path / 'pagination.db'}",
    ))
    repository = app.state.orchestrator.repository
    for index in range(55):
        repository.create_run(routes.ResearchRunCreate(seeds=[f"run {index:02d}"]))

    async def exercise():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            first = await client.get("/api/research-runs?limit=10&offset=0")
            last = await client.get("/api/research-runs?limit=10&offset=50")
            invalid = await client.get("/api/research-runs?limit=0")

            assert first.status_code == 200
            assert len(first.json()) == 10
            assert first.headers["x-total-count"] == "55"
            assert first.headers["x-pagination-limit"] == "10"
            assert first.headers["x-pagination-offset"] == "0"
            assert 'rel="next"' in first.headers["link"]

            assert last.status_code == 200
            assert len(last.json()) == 5
            assert last.headers["x-total-count"] == "55"
            assert 'rel="prev"' in last.headers["link"]
            assert 'rel="next"' not in last.headers["link"]
            assert {item["id"] for item in first.json()}.isdisjoint(
                {item["id"] for item in last.json()}
            )
            assert invalid.status_code == 422

    asyncio.run(exercise())


def test_cancelling_terminal_non_closed_run_preserves_history(tmp_path, monkeypatch):
    app = create_app(Settings(app_mode=AppMode.DEVELOPMENT, ai_provider="fake", database_url=f"sqlite:///{tmp_path / 'terminal-cancel.db'}"))
    session = app.state.db.session()
    repository = routes.ResearchRepository(session)
    complete = repository.create_run(routes.ResearchRunCreate(seeds=["complete run"]))
    repository.transition(complete, "complete")
    failed = repository.create_run(routes.ResearchRunCreate(seeds=["failed run"]))
    repository.transition(failed, "failed", "fixture failure")
    session.close()
    aborts = []

    async def fake_abort(redis_url, run_id, **kwargs):
        aborts.append(run_id)
        return False

    monkeypatch.setattr(routes, "abort_research_run", fake_abort)

    async def exercise():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            complete_response = await client.post(f"/api/research-runs/{complete.id}/cancel")
            failed_response = await client.post(f"/api/research-runs/{failed.id}/cancel")
            assert complete_response.status_code == 200
            assert complete_response.json()["status"] == "complete"
            assert failed_response.status_code == 200
            assert failed_response.json()["status"] == "failed"
            assert failed_response.json()["failure_reason"] == "fixture failure"

    asyncio.run(exercise())
    assert aborts == []


def test_cancellation_race_preserves_worker_terminal_commit(tmp_path, monkeypatch):
    settings = Settings(
        app_mode=AppMode.DEVELOPMENT,
        ai_provider="fake",
        database_url=f"sqlite:///{tmp_path / 'cancel-race.db'}",
    )
    app = create_app(settings)
    setup_session = app.state.db.session()
    setup_repository = routes.ResearchRepository(setup_session)
    run = setup_repository.create_run(routes.ResearchRunCreate(seeds=["race run"]))
    setup_repository.ensure_task_job(run.id)
    run_id = run.id
    setup_session.close()

    async def finish_during_abort(redis_url, abort_run_id, **kwargs):
        assert redis_url == settings.redis_url
        assert abort_run_id == run_id
        worker_session = app.state.db.session()
        try:
            worker_repository = routes.ResearchRepository(worker_session)
            worker_run = worker_repository.get_run(run_id)
            worker_repository.transition(worker_run, "complete")
            worker_repository.update_task_job(run_id, "complete")
        finally:
            worker_session.close()
        return False

    monkeypatch.setattr(routes, "abort_research_run", finish_during_abort)

    async def exercise():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.post(f"/api/research-runs/{run_id}/cancel")
            assert response.status_code == 200
            assert response.json()["status"] == "complete"
            assert response.json()["failure_reason"] is None

    asyncio.run(exercise())
    verification_session = app.state.db.session()
    try:
        verification_repository = routes.ResearchRepository(verification_session)
        assert verification_repository.get_run(run_id).status == "complete"
        assert verification_repository.ensure_task_job(run_id).status == "complete"
    finally:
        verification_session.close()


def test_failed_non_closed_run_resumes_same_id_and_preserves_evidence(tmp_path, monkeypatch):
    settings = Settings(
        app_mode=AppMode.DEVELOPMENT,
        ai_provider="fake",
        redis_url="redis://fixture",
        database_url=f"sqlite:///{tmp_path / 'resume.db'}",
    )
    app = create_app(settings)
    setup_session = app.state.db.session()
    setup_repository = routes.ResearchRepository(setup_session)
    run = setup_repository.create_run(routes.ResearchRunCreate(seeds=["storytelling"]))
    setup_repository.ensure_task_job(run.id)
    setup_repository.update_task_job(run.id, "running", increment_attempt=True)
    setup_repository.add_evidence(run.id, {
        "evidence_type": "video_enrichment",
        "source_type": "youtube_api",
        "source_entity_id": "video-1",
        "payload": {"video_id": "video-1"},
        "confidence": .9,
        "human_readable_summary": "durable completed video",
    })
    setup_repository.transition(run, "failed", "fixture bug")
    run_id = run.id
    setup_session.close()
    submissions = []

    async def fake_abort(redis_url, abort_run_id, **kwargs):
        assert abort_run_id == run_id
        return False

    async def fake_enqueue(redis_url, enqueue_run_id, **kwargs):
        submissions.append((enqueue_run_id, kwargs["attempt"]))
        return f"research:{enqueue_run_id}:attempt:{kwargs['attempt']}"

    monkeypatch.setattr(routes, "abort_research_run", fake_abort)
    monkeypatch.setattr(routes, "enqueue_research_run", fake_enqueue)

    async def exercise():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.post(f"/api/research-runs/{run_id}/resume")
            assert response.status_code == 200
            assert response.json()["id"] == run_id
            assert response.json()["status"] == "queued"

    asyncio.run(exercise())
    assert submissions == [(run_id, 2)]
    verification_session = app.state.db.session()
    try:
        repository = routes.ResearchRepository(verification_session)
        evidence = repository.get_evidence(run_id)
        assert [(item.evidence_type, item.source_entity_id) for item in evidence] == [
            ("video_enrichment", "video-1")
        ]
    finally:
        verification_session.close()


def test_cancelled_non_closed_run_can_be_explicitly_resumed(tmp_path, monkeypatch):
    settings = Settings(
        app_mode=AppMode.DEVELOPMENT,
        ai_provider="fake",
        redis_url="redis://fixture",
        database_url=f"sqlite:///{tmp_path / 'resume-cancelled.db'}",
    )
    app = create_app(settings)
    setup_session = app.state.db.session()
    repository = routes.ResearchRepository(setup_session)
    run = repository.create_run(routes.ResearchRunCreate(seeds=["storytelling"]))
    repository.ensure_task_job(run.id)
    repository.update_task_job(run.id, "cancelled", increment_attempt=True)
    repository.transition(
        run,
        "cancelled",
        "platform interruption misclassified by an old worker",
    )
    run_id = run.id
    setup_session.close()
    submissions = []

    async def fake_enqueue(redis_url, enqueue_run_id, **kwargs):
        submissions.append((enqueue_run_id, kwargs["attempt"]))
        return f"research:{enqueue_run_id}:attempt:{kwargs['attempt']}"

    monkeypatch.setattr(routes, "enqueue_research_run", fake_enqueue)

    async def exercise():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.post(f"/api/research-runs/{run_id}/resume")
            assert response.status_code == 200
            assert response.json()["id"] == run_id
            assert response.json()["status"] == "queued"

    asyncio.run(exercise())
    assert submissions == [(run_id, 2)]
