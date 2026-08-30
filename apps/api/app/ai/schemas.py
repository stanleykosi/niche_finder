from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class NicheClassification(BaseModel):
    broad_market: str
    niche: str
    sub_niche: str
    repeatable_format: str
    confidence: float = Field(ge=0, le=1)


class ViralMechanism(BaseModel):
    primary_mechanism: str
    secondary_mechanisms: list[str]
    viewer_question: str
    hook_pattern: str
    payoff_pattern: str
    supporting_evidence_ids: list[str]
    alternative_explanation: str
    confidence: float = Field(ge=0, le=1)


class WinnerLoserComparison(BaseModel):
    winner_video_id: str
    loser_video_id: str
    topic_difference: str
    hook_difference: str
    opening_visual_difference: str
    structure_difference: str
    pacing_difference: str
    payoff_difference: str
    curiosity_question_difference: str = ""
    clip_count_difference: str = ""
    title_packaging_difference: str = ""
    control_quality: str = "matched within channel, format, duration and publication window"
    hypothesis: str
    causal_limit: str = "observational comparison; the difference is a testable hypothesis, not causal proof"
    confidence: float = Field(ge=0, le=1)


class VisualStructureAnalysis(BaseModel):
    hook_visual: str
    composition_pattern: str
    caption_pattern: str
    pacing_pattern: str
    reveal_pattern: str
    observable_features: list[str] = Field(default_factory=list)
    uncertainty: str
    confidence: float = Field(ge=0, le=1)


class IdeaGeneration(BaseModel):
    ideas: list[str] = Field(min_length=1, max_length=30)
    repeatable_formats: list[str] = Field(default_factory=list)
    series_suggestions: list[str] = Field(default_factory=list)


class VideoEvidenceAnalysis(BaseModel):
    video_id: str
    observed_hook: str
    audience_promise: str
    narrative_structure: list[str] = Field(default_factory=list)
    mechanism_signals: list[str] = Field(default_factory=list)
    transcript_evidence_ids: list[str] = Field(default_factory=list)
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    uncertainty: str
    confidence: float = Field(ge=0, le=1)


class CandidateSynthesis(BaseModel):
    executive_summary: str
    audience_demand_interpretation: str
    mechanism_thesis: str
    repeatability_thesis: str
    production_thesis: str
    differentiation: str
    risks: list[str] = Field(default_factory=list)
    recommendation_rationale: str
    first_test: list[str] = Field(default_factory=list)
    continue_criteria: list[str] = Field(default_factory=list)
    reject_criteria: list[str] = Field(default_factory=list)
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)


class CriticAssessment(BaseModel):
    challenges: list[str]
    confidence_adjustment: float = Field(ge=-1, le=0)
    unsupported_claims: list[str] = Field(default_factory=list)
    blocking_issues: list[str] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    supporting_evidence_ids: list[str] = Field(default_factory=list)


class ReportSynthesis(BaseModel):
    executive_summary: str
    portfolio_interpretation: str
    why_now: str
    primary_risk: str
    differentiation: str
    initial_shorts_test: str
    initial_long_form_test: str
    continue_if: str
    reject_if: str
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)


class AIEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    evidence_ids: list[str]
