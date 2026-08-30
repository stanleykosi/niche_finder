from __future__ import annotations

from typing import Protocol

from .schemas import (
    CandidateSynthesis,
    CriticAssessment,
    IdeaGeneration,
    NicheClassification,
    ReportSynthesis,
    VideoEvidenceAnalysis,
    ViralMechanism,
    VisualStructureAnalysis,
    WinnerLoserComparison,
)


class AIProvider(Protocol):
    name: str
    version: str
    supports_image_inputs: bool
    supports_semantic_image_validation: bool

    async def classify_niche(self, context: str, evidence_ids: list[str]) -> NicheClassification: ...
    async def viral_mechanism(self, context: str, evidence_ids: list[str]) -> ViralMechanism: ...
    async def compare_winner_loser(self, winner: dict, loser: dict, evidence_ids: list[str]) -> WinnerLoserComparison: ...
    async def analyze_visuals(self, context: str, frame_refs: list[str], evidence_ids: list[str]) -> VisualStructureAnalysis: ...
    async def analyze_video(self, context: str, evidence_ids: list[str]) -> VideoEvidenceAnalysis: ...
    async def generate_ideas(self, context: str, evidence_ids: list[str]) -> IdeaGeneration: ...
    async def synthesize_candidate(self, context: str, evidence_ids: list[str]) -> CandidateSynthesis: ...
    async def critique(self, context: str, evidence_ids: list[str]) -> CriticAssessment: ...
    async def synthesize_report(self, context: str, evidence_ids: list[str]) -> ReportSynthesis: ...
