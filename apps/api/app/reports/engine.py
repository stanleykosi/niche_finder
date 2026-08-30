from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select

from ..db.models import EvidenceRecord, FormatCluster, ResearchRun, ViralMechanismAnalysis, WinnerLoserComparison
from ..domain.contracts import ReportResponse
from ..repositories.store import ResearchRepository


class ReportEngine:
    def __init__(self, repository: ResearchRepository) -> None:
        self.repository = repository

    def build(self, run_id: str) -> dict[str, Any]:
        run = self.repository.get_run(run_id)
        if run is None:
            raise KeyError(run_id)
        candidates = self.repository.get_candidates(run_id)
        evidence = self.repository.get_evidence(run_id)
        clusters = list(self.repository.session.scalars(select(FormatCluster).where(FormatCluster.research_run_id == run_id)))
        mechanisms = []
        for cluster in clusters:
            mechanism = self.repository.session.scalar(select(ViralMechanismAnalysis).where(ViralMechanismAnalysis.format_cluster_id == cluster.id))
            if mechanism:
                mechanisms.append({
                    "cluster_id": cluster.id, "label": cluster.label, "primary_mechanism": mechanism.primary_mechanism,
                    "secondary_mechanisms": mechanism.secondary_mechanisms, "viewer_question": mechanism.viewer_question,
                    "hook_pattern": mechanism.hook_pattern, "payoff_pattern": mechanism.payoff_pattern,
                    "evidence_refs": mechanism.evidence_refs, "alternative_explanation": mechanism.alternative_explanation,
                    "confidence": mechanism.confidence, "provider": mechanism.provider,
                })
        comparisons = list(self.repository.session.scalars(select(WinnerLoserComparison).where(WinnerLoserComparison.research_run_id == run_id)))
        report_record = next((item for item in reversed(evidence) if item.evidence_type == "report_synthesis"), None)
        report_synthesis = report_record.payload if report_record and report_record.payload.get("citation_validation", {}).get("passed") else {}
        top = candidates[0] if candidates else None
        why_now = "No niche passed the current evidence gates."
        if top:
            demand = top.demand_assessment
            media_assessments = demand.get("media_assessments")
            if isinstance(media_assessments, dict):
                parts = []
                for key, label in (("shorts", "Shorts"), ("long_form", "Long-form")):
                    media_demand = media_assessments.get(key, {})
                    media_momentum = top.momentum_assessment.get(key, {})
                    media_clip = top.clip_ceiling.get(key, {})
                    trend = media_momentum.get("trend_assessment", {})
                    parts.append(
                        f"{label}: {media_demand.get('recent_outliers', 0)} current outliers across "
                        f"{media_demand.get('outlier_channels', 0)} channels, YouTube trend score "
                        f"{round(trend.get('score', 0) * 100)}%, {media_clip.get('validated_count', 0)} clip-validated ideas"
                    )
                why_now = "; ".join(parts) + "."
            else:
                trend = top.momentum_assessment.get("trend_assessment", {})
                why_now = f"{demand.get('recent_outliers', 0)} current outliers across {demand.get('outlier_channels', 0)} channels; YouTube trend score {round(trend.get('score', 0) * 100)}%; {top.clip_ceiling.get('validated_count', 0)} clip-validated ideas."
        action_plan = {
            "why_now": "Re-check current evidence before it ages beyond the 45-day decision window.",
            "primary_risk": "A mechanism may be creator-specific even when public performance repeats.",
            "differentiation": "Inspect weak-copycat gaps and choose a subject family with validated clip supply.",
            "initial_shorts_test": "Research the top ten validated ideas and retain only those with three semantically matching clips plus a visible reveal.",
            "initial_long_form_test": "Treat long-form as a separate assessment; do not infer it from Shorts demand.",
            "continue_if": "All hard gates pass across at least three channels and three matched winner/loser pairs.",
            "reject_if": "Current outliers do not repeat, evidence is concentrated in one channel, or fewer than ten ideas pass clip preflight.",
        }
        if report_synthesis:
            why_now = report_synthesis["why_now"]
            action_plan = {key: report_synthesis[key] for key in action_plan}
        observed_metadata_sources = sorted({
            item.source_type
            for item in evidence
            if item.evidence_type == "video_enrichment"
            and item.source_type in {"fixture_api", "youtube_api", "keyless_ytdlp"}
        })
        metadata_source = run.configuration.get("metadata_source")
        if metadata_source not in {"fixture_api", "youtube_api", "keyless_ytdlp"}:
            metadata_source = observed_metadata_sources[0] if observed_metadata_sources else (
                "fixture_api" if run.configuration.get("fixture_mode", False) else "keyless_ytdlp"
            )
        return {
            "research_run_id": UUID(run_id),
            "generated_at": datetime.now(timezone.utc),
            "why_now": why_now,
            "evidence_summary": {
                "evidence_count": len(evidence), "channels_examined": len({item.payload.get("channel_id") for item in evidence if item.payload.get("channel_id")}),
                "videos_examined": len({item.payload.get("video_id") for item in evidence if item.payload.get("video_id")}),
                "browser_observations": sum(1 for item in evidence if item.source_type == "fixture_browser" or item.source_type == "browser"),
                "api_observations": sum(1 for item in evidence if item.source_type in {"fixture_api", "youtube_api", "keyless_ytdlp", "deterministic"} and item.evidence_type == "video_enrichment"),
                "metadata_sources": observed_metadata_sources,
                "last_observed_at": max((item.observed_at for item in evidence), default=datetime.now(timezone.utc)),
            },
            "candidates": [_candidate_dict(item) for item in candidates],
            "viral_mechanisms": mechanisms,
            "winner_loser_comparisons": [
                {"id": item.id, "winner_video_id": item.winner_video_id, "loser_video_id": item.loser_video_id, **item.payload, "confidence": item.confidence, "provider": item.provider}
                for item in comparisons
            ],
            "research_synthesis": report_synthesis,
            "action_plan": action_plan,
            "fixture_mode": run.configuration.get("fixture_mode", False),
            "metadata_source": metadata_source,
        }


def _candidate_dict(item: Any) -> dict[str, Any]:
    return {
        "id": UUID(item.id), "rank": item.rank, "broad_market": item.broad_market, "niche": item.niche,
        "sub_niche": item.sub_niche, "repeatable_format": item.repeatable_format,
        "primary_viral_mechanism": item.primary_viral_mechanism,
        "shorts_assessment": item.shorts_assessment, "longform_assessment": item.longform_assessment,
        "bridge_assessment": item.bridge_assessment,
        "idea_ceiling": item.idea_ceiling, "clip_ceiling": item.clip_ceiling,
        "saturation_assessment": item.saturation_assessment, "demand_assessment": item.demand_assessment,
        "momentum_assessment": item.momentum_assessment, "research_synthesis": item.research_synthesis,
        "critic_assessment": item.critic_assessment, "confidence": item.confidence,
        "verdict": item.verdict, "evidence_ids": [UUID(value) for value in item.evidence_ids],
    }
