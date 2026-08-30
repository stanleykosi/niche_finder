"""Deterministic AI double used by closed tests and demo mode."""

from __future__ import annotations

import json

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


class FakeAIProvider:
    name = "fake"
    version = "fixture-ai-v1"
    supports_image_inputs = False
    supports_semantic_image_validation = False

    async def classify_niche(self, context: str, evidence_ids: list[str]) -> NicheClassification:
        lowered = context.lower()
        if "one-hit" in lowered or "one hit" in lowered:
            return NicheClassification(broad_market="Entertainment", niche="One-hit novelty clips", sub_niche="single viral moment", repeatable_format="isolated reveal", confidence=0.42)
        if "oversaturated" in lowered:
            return NicheClassification(broad_market="Education", niche="Fast visual explainers", sub_niche="common facts and tests", repeatable_format="ranked visual reveal", confidence=0.64)
        if "history" in lowered or "stale" in lowered:
            return NicheClassification(broad_market="Education", niche="Historical curiosity", sub_niche="archival mystery explainers", repeatable_format="mystery-evidence-reveal", confidence=0.55)
        return NicheClassification(broad_market="Education", niche="Visual impossibility explainers", sub_niche="everyday tests and puzzles", repeatable_format="failed attempts → correct attempt → explanation", confidence=0.91)

    async def viral_mechanism(self, context: str, evidence_ids: list[str]) -> ViralMechanism:
        lowered = context.lower()
        if "ranking" in lowered or "oversaturated" in lowered:
            primary = "Escalation ranking → final winner"
            secondary = ["open loop", "contrast"]
            question = "Which example will survive the escalation?"
            hook = "Show the hardest-looking matchup first, then promise a ranked winner."
            payoff = "The final result resolves the ranking with a visible proof."
        elif "mystery" in lowered or "stale" in lowered:
            primary = "Mystery → evidence → reveal"
            secondary = ["pattern recognition", "curiosity gap"]
            question = "What really caused the surprising result?"
            hook = "Present an anomalous visual and withhold the explanation."
            payoff = "The evidence-backed reveal reframes the opening mystery."
        else:
            primary = "Visual impossibility → failed attempts → correct attempt → explanation"
            secondary = ["open loop", "surprise correction"]
            question = "Can the impossible-looking result actually be repeated?"
            hook = "Open on the visual contradiction and ask the viewer to spot the trick."
            payoff = "A successful repeat followed by a compact explanation closes the loop."
        return ViralMechanism(primary_mechanism=primary, secondary_mechanisms=secondary, viewer_question=question, hook_pattern=hook, payoff_pattern=payoff, supporting_evidence_ids=evidence_ids, alternative_explanation="Topic novelty or packaging may explain part of the lift.", confidence=0.88 if len(evidence_ids) >= 3 else 0.62)

    async def compare_winner_loser(self, winner: dict, loser: dict, evidence_ids: list[str]) -> WinnerLoserComparison:
        return WinnerLoserComparison(
            winner_video_id=winner["id"], loser_video_id=loser["id"],
            topic_difference="Winner makes the same subject concrete with a visible test.",
            hook_difference="Winner opens on the contradiction within the first beat.",
            opening_visual_difference="Winner shows the result before the explanation.",
            structure_difference="Winner uses failed attempts before the correct attempt.",
            pacing_difference="Winner changes visual state every few seconds.",
            payoff_difference="Winner ends on proof plus a short explanation.",
            curiosity_question_difference="Winner asks one concrete, visibly resolvable question; loser begins with explanation.",
            clip_count_difference="Winner exposes several distinct attempt states; loser has fewer visual state changes.",
            title_packaging_difference="Winner promises a test and outcome while the loser labels a general explanation.",
            hypothesis="The repeatable mechanism and fast visual proof matter more than the broad topic.",
            confidence=0.82 if evidence_ids else 0.55,
        )

    async def analyze_visuals(self, context: str, frame_refs: list[str], evidence_ids: list[str]) -> VisualStructureAnalysis:
        return VisualStructureAnalysis(
            hook_visual="The outcome or contradiction is visible before explanation.",
            composition_pattern="One object and one test dominate a vertical, high-contrast frame.",
            caption_pattern="Short captions label attempts and emphasize the changed variable.",
            pacing_pattern="Visual state changes at each attempt, then slows briefly for proof.",
            reveal_pattern="The final successful result is held long enough to verify.",
            observable_features=["proof-first opening", "attempt progression", "visible final state"],
            uncertainty="Fixture frames are semantic references rather than decoded pixels.", confidence=.84 if frame_refs else .58,
        )

    async def analyze_video(self, context: str, evidence_ids: list[str]) -> VideoEvidenceAnalysis:
        try:
            packet = json.loads(context)
        except json.JSONDecodeError:
            packet = {}
        video_id = str(packet.get("video", {}).get("video_id", "unknown"))
        transcript_ids = [value for value in evidence_ids if value]
        return VideoEvidenceAnalysis(
            video_id=video_id,
            observed_hook="The opening presents the result or contradiction before explaining it.",
            audience_promise="A visible test will resolve a concrete curiosity question.",
            narrative_structure=["proof-first hook", "attempt progression", "held result", "compact explanation"],
            mechanism_signals=["curiosity gap", "failed-attempt contrast", "visual proof"],
            transcript_evidence_ids=transcript_ids[:1],
            supporting_evidence_ids=transcript_ids,
            uncertainty="Closed-mode interpretation is limited to fixture transcript and browser observations.",
            confidence=.83 if transcript_ids else .5,
        )

    async def generate_ideas(self, context: str, evidence_ids: list[str]) -> IdeaGeneration:
        ideas = [
            "Can a paper bridge hold a full mug after three folds?",
            "Which household surface makes a spinning coin stop fastest?",
            "What changes when the same balance test is done upside down?",
            "Three failed ways to stack a moving object before the stable solution",
            "Does the result change with weight, texture, or angle?",
            "A street-scale version of the same visual impossibility",
            "The simplest explanation for a result that looks edited",
            "One test, five escalating constraints, and a final winner",
            "Can two everyday materials create the same illusion?",
            "The most counterintuitive repeatable result in a kitchen drawer",
            "A beginner attempt versus a controlled repeat",
            "What viewers predict before the evidence changes their mind?",
            "Can temperature reverse the same everyday visual result?",
            "The cheapest object that survives an escalating strength test",
            "What happens when a familiar experiment is repeated at miniature scale?",
        ]
        return IdeaGeneration(ideas=ideas, repeatable_formats=["failed attempts → proof → explanation", "ranked escalation"], series_suggestions=["One mechanism, twenty everyday subjects", "Prediction before proof"])

    async def synthesize_candidate(self, context: str, evidence_ids: list[str]) -> CandidateSynthesis:
        lowered = context.lower()
        risks = ["Creator-specific execution may explain part of the observed lift."]
        if "oversaturated" in lowered or '"risk": "high"' in lowered:
            risks.append("Direct-format competition raises the entry burden.")
        return CandidateSynthesis(
            executive_summary="The opportunity is supported only where current multi-channel demand, repeatable packaging, and feasible visual supply agree.",
            audience_demand_interpretation="Recent same-format outliers show whether viewers are responding now, while channel baselines prevent raw view counts from carrying the claim.",
            mechanism_thesis="A proof-first curiosity loop uses failed attempts and a visible correction to hold attention through the payoff.",
            repeatability_thesis="The mechanism transfers across distinct everyday subjects and can support a recognizable series.",
            production_thesis="The validated ideas have rights-known source diversity and a reveal-capable asset path; unsupported ideas do not count.",
            differentiation="Lead with a verifiable result, expose the changed variable clearly, and use weak-copycat gaps to choose subjects.",
            risks=risks,
            recommendation_rationale="The deterministic gates remain the decision authority; this synthesis explains how the cited evidence fits together.",
            first_test=["Publish the first five highest-evidence ideas.", "Use one consistent proof-first structure.", "Compare completion and repeat-view behavior before scaling to twenty videos."],
            continue_criteria=["Current outliers continue across independent channels.", "The test reproduces the observed hook-to-payoff mechanism."],
            reject_criteria=["The mechanism fails to reproduce.", "Clip sourcing or subject diversity falls below the hard gates."],
            supporting_evidence_ids=evidence_ids,
            confidence=.88 if len(evidence_ids) >= 3 else .58,
        )

    async def critique(self, context: str, evidence_ids: list[str]) -> CriticAssessment:
        challenges = []
        if len(evidence_ids) < 3:
            challenges.append("Cross-channel evidence is still thin.")
        if "stale" in context.lower():
            challenges.append("Historical virality is not current momentum.")
        if "oversaturated" in context.lower():
            challenges.append("Direct-format upload density creates a high entry burden.")
        if not challenges:
            challenges.append("Creator-specific execution may explain part of the observed lift.")
        blocking = ["Insufficient cited cross-channel evidence."] if len(evidence_ids) < 2 else []
        return CriticAssessment(
            challenges=challenges,
            confidence_adjustment=-0.06 if len(evidence_ids) < 3 else -0.02,
            unsupported_claims=[],
            blocking_issues=blocking,
            missing_evidence=[] if evidence_ids else ["No ledger evidence was supplied."],
            supporting_evidence_ids=evidence_ids,
        )

    async def synthesize_report(self, context: str, evidence_ids: list[str]) -> ReportSynthesis:
        return ReportSynthesis(
            executive_summary="The report ranks opportunities by deterministic gates, then uses evidence-bound synthesis and criticism to explain the decision.",
            portfolio_interpretation="Prefer the first candidate whose current demand, replicated mechanism, idea supply, footage path, and saturation gates all survive criticism.",
            why_now="The decision is based on the current 45-day outlier window against a 90-day supporting baseline.",
            primary_risk="Public evidence can show repeated performance but cannot prove private retention or remove creator-specific advantage.",
            differentiation="Enter through the observed mechanism and an underserved subject family, not by copying competitor footage or titles.",
            initial_shorts_test="Produce five evidence-backed pilots, then extend to twenty only if the observed mechanism reproduces.",
            initial_long_form_test="Validate long-form depth separately with a small explanatory pilot; Shorts demand is not treated as proof.",
            continue_if="The candidate retains all hard gates and the pilot reproduces the hook-to-payoff behavior.",
            reject_if="Current outliers stop repeating, evidence concentrates in one creator, or production feasibility falls below threshold.",
            supporting_evidence_ids=evidence_ids,
            confidence=.86 if evidence_ids else .5,
        )
