from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..domain.enums import RequestedFormat, Verdict
from .saturation import SaturationResult


@dataclass(frozen=True)
class Recommendation:
    shorts: dict[str, Any]
    longform: dict[str, Any]
    verdict: Verdict
    confidence: float
    hard_gates: dict[str, Any]


def recommend(
    requested_format: RequestedFormat,
    channel_count: int,
    recent_outlier_count: int,
    idea_ceiling: dict[str, Any],
    clip_ceiling: dict[str, Any],
    saturation: SaturationResult,
    mechanism_confidence: float,
    evidence_confidence: float,
    *,
    successful_channel_count: int | None = None,
    outlier_channel_count: int = 0,
    comparison_count: int = 0,
    mechanism_channel_count: int = 0,
    minimum_ideas: int = 10,
    minimum_clip_coverage: float = .7,
    minimum_channels: int = 3,
    minimum_outliers: int = 3,
    minimum_outlier_channels: int = 2,
    minimum_comparisons: int = 3,
    maximum_saturation: float = .75,
) -> Recommendation:
    if requested_format == RequestedFormat.BOTH:
        raise ValueError("combined recommendations require independently computed Shorts and long-form assessments")
    # Caller preferences may demand stronger proof, but can never weaken the
    # canonical positive-recommendation floor.
    minimum_ideas = max(10, minimum_ideas)
    minimum_clip_coverage = max(.7, minimum_clip_coverage)
    minimum_channels = max(3, minimum_channels)
    minimum_outliers = max(3, minimum_outliers)
    minimum_outlier_channels = max(2, minimum_outlier_channels)
    minimum_comparisons = max(3, minimum_comparisons)
    maximum_saturation = min(.75, maximum_saturation)
    successful = successful_channel_count if successful_channel_count is not None else channel_count
    validated_ideas = int(clip_ceiling.get("validated_count", idea_ceiling.get("unique_count", 0)))
    idea_score = min(1.0, validated_ideas / max(minimum_ideas, 1))
    clip_score = float(clip_ceiling.get("asset_coverage", 0))
    clip_gate_passed = (
        clip_score >= minimum_clip_coverage
        and int(clip_ceiling.get("source_diversity", 0)) >= 2
        and float(clip_ceiling.get("reveal_coverage", 0)) >= .6
        and float(clip_ceiling.get("semantic_fit_share", 0)) >= minimum_clip_coverage
    )
    gates = {
        "idea_ceiling": _gate(validated_ideas >= minimum_ideas, validated_ideas, minimum_ideas, "validated ideas"),
        "clip_availability": {**_gate(clip_gate_passed, clip_score, minimum_clip_coverage, "coverage"), "details": {"source_diversity": clip_ceiling.get("source_diversity", 0), "minimum_sources": 2, "rights_metadata_share": clip_ceiling.get("rights_metadata_share", 0), "rights_gates_discovery": False, "reveal_coverage": clip_ceiling.get("reveal_coverage", 0), "minimum_reveal_coverage": .6, "semantic_fit_share": clip_ceiling.get("semantic_fit_share", 0), "minimum_semantic_fit_share": minimum_clip_coverage}},
        "successful_channels": _gate(successful >= minimum_channels, successful, minimum_channels, "channels"),
        "recent_outliers": _gate(recent_outlier_count >= minimum_outliers, recent_outlier_count, minimum_outliers, "videos"),
        "outlier_channels": _gate(outlier_channel_count >= minimum_outlier_channels, outlier_channel_count, minimum_outlier_channels, "channels"),
        "winner_loser_pairs": _gate(comparison_count >= minimum_comparisons, comparison_count, minimum_comparisons, "pairs"),
        "mechanism_replication": _gate(mechanism_channel_count >= 2, mechanism_channel_count, 2, "channels"),
        "saturation": _gate(saturation.risk_score <= maximum_saturation, saturation.risk_score, maximum_saturation, "maximum risk", inverse=True),
    }
    gate_total = len(gates)
    gates["passed"] = sum(bool(value["passed"]) for value in gates.values())
    gates["total"] = gate_total
    gates["all_passed"] = gates["passed"] == gates["total"]
    demand = min(1.0, successful / max(minimum_channels, 1)) * .45 + min(1.0, recent_outlier_count / max(minimum_outliers, 1)) * .55
    saturation_headroom = max(0.0, 1 - saturation.risk_score)
    shorts_score = round(demand * .28 + idea_score * .2 + clip_score * .2 + saturation_headroom * .12 + mechanism_confidence * .1 + min(1, comparison_count / max(minimum_comparisons, 1)) * .1, 3)
    long_score = round(demand * .3 + idea_score * .28 + saturation_headroom * .2 + mechanism_confidence * .12 + evidence_confidence * .1, 3)
    confidence = round(min(1.0, evidence_confidence * .35 + mechanism_confidence * .2 + idea_score * .2 + min(1, comparison_count / max(minimum_comparisons, 1)) * .15 + saturation_headroom * .1), 3)
    not_assessed = {"fit": "not_assessed", "score": None, "reason": "No evidence from this media class was used in this assessment."}
    shorts = {"fit": "promising" if shorts_score >= .65 and gates["all_passed"] else "watch", "score": shorts_score, "reason": "Shorts fit requires repeatable Shorts demand, matched performance differences, ten clip-supported ideas, and manageable saturation."} if requested_format == RequestedFormat.SHORTS else not_assessed
    longform = {"fit": "promising" if long_score >= .65 and gates["all_passed"] else "watch", "score": long_score, "reason": "Long-form fit uses only long-form demand evidence and requires topic depth, durable ideas, and a reproducible production path."} if requested_format == RequestedFormat.LONG_FORM else not_assessed
    if saturation.risk_score > maximum_saturation:
        verdict = Verdict.OVERSATURATED
    elif not clip_gate_passed and requested_format in {RequestedFormat.SHORTS, RequestedFormat.BOTH}:
        verdict = Verdict.FOOTAGE_CONSTRAINED
    elif not gates["all_passed"]:
        verdict = Verdict.INSUFFICIENT
    elif requested_format == RequestedFormat.SHORTS:
        verdict = Verdict.SHORTS_ONLY
    else:
        verdict = Verdict.LONG_FORM_ONLY
    return Recommendation(shorts, longform, verdict, confidence, gates)


def _gate(passed: bool, observed: int | float, required: int | float, unit: str, inverse: bool = False) -> dict[str, Any]:
    return {"passed": passed, "observed": observed, "required": required, "unit": unit, "comparison": "at_most" if inverse else "at_least"}
