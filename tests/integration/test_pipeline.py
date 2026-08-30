import asyncio

from apps.api.app.core.config import AppMode, Settings
from apps.api.app.db.session import Database
from apps.api.app.domain.contracts import ResearchRunCreate
from apps.api.app.repositories.store import ResearchRepository
from apps.api.app.reports.engine import ReportEngine
from apps.api.app.services.factory import create_orchestrator


def run_scenario(tmp_path, scenario: str):
    settings = Settings(app_mode=AppMode.CLOSED_TEST, ai_provider="fake", fixture_scenario=scenario, database_url=f"sqlite:///{tmp_path / (scenario + '.db')}")
    db = Database(settings); db.create_schema(); repository = ResearchRepository(db.session())
    orchestrator = create_orchestrator(settings, repository)
    request = ResearchRunCreate(seeds=["visual tests"], limits={"max_queries": 2, "max_results_per_query": 20, "max_channels": 10, "max_videos": 30, "max_expansion_depth": 1})
    run = repository.create_run(request); run.configuration = {**run.configuration, "fixture_mode": True}; repository.session.commit()
    asyncio.run(orchestrator.execute(run, request))
    browser_evidence = [
        item for item in repository.get_evidence(run.id)
        if item.evidence_type == "browser_media_observation"
    ]
    assert sum(bool(item.payload.get("frame_refs")) for item in browser_evidence) <= settings.media_max_videos_per_run
    return run, ReportEngine(repository).build(run.id)


def test_strong_niche_completes_with_lineage(tmp_path):
    run, report = run_scenario(tmp_path, "strong")
    assert run.status == "complete"
    assert report["candidates"]
    assert report["candidates"][0]["evidence_ids"]
    assert report["viral_mechanisms"]
    candidate = report["candidates"][0]
    assert candidate["idea_ceiling"]["validated_count"] >= 10
    assert candidate["clip_ceiling"]["validated_count"] >= 10
    assert candidate["clip_ceiling"]["search_bounds"]["maximum_new_ideas"] >= 10
    assert candidate["clip_ceiling"]["search_bounds"]["deferred_ideas"] == 0
    assert candidate["clip_ceiling"]["initial_preflight"]["stage"] == "pre_expansion_clip_preflight"
    assert (
        candidate["clip_ceiling"]["initial_preflight"]["passed"] is True
        or candidate["clip_ceiling"]["initial_preflight"].get("deferred_to_final_validation") is True
    )
    assert candidate["demand_assessment"]["successful_channels"] >= 3
    assert candidate["demand_assessment"]["winner_loser_pairs"] >= 3
    assert candidate["demand_assessment"]["mechanism_evidence_channels"] >= 2
    assert candidate["demand_assessment"]["shorts_summary"]["counts"]["confirmed_short"] >= 6
    assert candidate["demand_assessment"]["hard_gates"]["all_passed"] is True
    assert len(report["winner_loser_comparisons"]) >= 3
    assert report["evidence_summary"]["browser_observations"] >= 1
    assert report["research_synthesis"]["citation_validation"]["passed"] is True
    assert candidate["research_synthesis"]["citation_validation"]["passed"] is True
    assert candidate["critic_assessment"]["citation_validation"]["passed"] is True
    assert candidate["demand_assessment"]["llm_adjudication"]["final_verdict"] == candidate["verdict"]
    assert len(candidate["idea_ceiling"]["ideas_with_constraints"]) >= 10
    assert all(not item["gates_recommendation"] for item in candidate["idea_ceiling"]["ideas_with_constraints"])
    assert candidate["demand_assessment"]["competitor_30d_views_range"]["high"] > 0
    assert candidate["demand_assessment"]["revenue_potential"]["gates_recommendation"] is False
    assert candidate["momentum_assessment"]["trend_assessment"]["windows"]["30"]["uploads"] >= 1
    assert report["winner_loser_comparisons"][0]["causal_limit"].startswith("observational")


def test_one_hit_is_not_strongly_recommended(tmp_path):
    _, report = run_scenario(tmp_path, "one_hit")
    assert report["candidates"][0]["verdict"] == "Insufficient evidence"


def test_saturated_format_warns(tmp_path):
    _, report = run_scenario(tmp_path, "saturated")
    assert report["candidates"][0]["verdict"] == "Demand exists but oversaturated"


def test_stale_evidence_does_not_pass_current_gate(tmp_path):
    _, report = run_scenario(tmp_path, "stale")
    assert report["candidates"][0]["verdict"] == "Insufficient evidence"
