"""Evidence-driven, zero-key AI boundary for bounded live smoke research.

This provider is deliberately distinct from the closed fixture provider. Text
interpretation uses deterministic structured heuristics, while visual calls
must read actual bounded image inputs before returning any positive judgment.
It is a conservative availability fallback, not a substitute for a configured
multimodal model in higher-accuracy research.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

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


MAX_IMAGE_BYTES = 8 * 1024 * 1024


class DeterministicLiveAIProvider:
    """Local deterministic interpretation with real-image input validation."""

    name = "deterministic_live"
    version = "deterministic-live-evidence-v3-conservative-visuals"
    supports_image_inputs = True
    supports_semantic_image_validation = False

    def __init__(self, image_timeout: float = 20.0) -> None:
        self.image_timeout = image_timeout

    async def classify_niche(self, context: str, evidence_ids: list[str]) -> NicheClassification:
        subject, format_label = _subject_and_format(context)
        return NicheClassification(
            broad_market="Observed YouTube market",
            niche=subject,
            sub_niche=f"Repeatable {subject.lower()} formats",
            repeatable_format=format_label,
            confidence=.58 if subject != "Observed candidate topic" else .35,
        )

    async def viral_mechanism(self, context: str, evidence_ids: list[str]) -> ViralMechanism:
        lowered = context.lower()
        if any(marker in lowered for marker in ("reveal", "proof", "result")):
            mechanism = "Observed question or claim → visible proof → payoff"
            question = "Will the opening claim be resolved by visible evidence?"
            hook = "The supplied observations indicate a question, claim, or result-first opening."
            payoff = "The supplied observations indicate visible proof or a final state."
        else:
            mechanism = "Observed opening → development → payoff"
            question = "How does the observed opening resolve?"
            hook = "Only the opening signals present in the bounded dossier are retained."
            payoff = "Payoff detail remains a hypothesis unless the dossier contains a reveal observation."
        return ViralMechanism(
            primary_mechanism=mechanism,
            secondary_mechanisms=[],
            viewer_question=question,
            hook_pattern=hook,
            payoff_pattern=payoff,
            supporting_evidence_ids=list(dict.fromkeys(evidence_ids)),
            alternative_explanation="Packaging, creator familiarity, or topic timing may explain the observed performance.",
            confidence=.62 if len(set(evidence_ids)) >= 2 else .4,
        )

    async def compare_winner_loser(
        self, winner: dict, loser: dict, evidence_ids: list[str]
    ) -> WinnerLoserComparison:
        winner_structure = winner.get("structure") or []
        loser_structure = loser.get("structure") or []
        return WinnerLoserComparison(
            winner_video_id=str(winner.get("id") or "unknown"),
            loser_video_id=str(loser.get("id") or "unknown"),
            topic_difference=f"Observed topics: winner={winner.get('topic') or 'unknown'}; loser={loser.get('topic') or 'unknown'}.",
            hook_difference=f"Observed openings: winner={winner.get('first_spoken_line') or 'unknown'}; loser={loser.get('first_spoken_line') or 'unknown'}.",
            opening_visual_difference=f"Observed visuals: winner={winner.get('opening_visual') or 'unknown'}; loser={loser.get('opening_visual') or 'unknown'}.",
            structure_difference=f"Observed structures: winner={winner_structure}; loser={loser_structure}.",
            pacing_difference=f"Observed pacing scores: winner={winner.get('pacing_score')}; loser={loser.get('pacing_score')}.",
            payoff_difference=f"Observed reveal times: winner={winner.get('reveal_timestamp_seconds')}; loser={loser.get('reveal_timestamp_seconds')}.",
            curiosity_question_difference="No private retention or causal effect is inferred from the public comparison.",
            clip_count_difference=f"Observed state counts: winner={winner.get('estimated_visual_state_count', 0)}; loser={loser.get('estimated_visual_state_count', 0)}.",
            title_packaging_difference=f"Observed titles: winner={winner.get('title') or 'unknown'}; loser={loser.get('title') or 'unknown'}.",
            hypothesis="The observed public packaging and structure differences are bounded test hypotheses, not causal conclusions.",
            confidence=.62 if evidence_ids else .4,
        )

    async def analyze_visuals(
        self, context: str, frame_refs: list[str], evidence_ids: list[str]
    ) -> VisualStructureAnalysis:
        observations = await self._inspect_images(frame_refs[:8])
        if not observations:
            raise ValueError("deterministic live visual analysis requires at least one valid bounded image")
        portrait = sum(bool(item.get("portrait")) for item in observations)
        return VisualStructureAnalysis(
            hook_visual=f"{len(observations)} candidate image input(s) were structurally parsed from the supplied evidence references.",
            composition_pattern=(
                f"{portrait} of {len(observations)} parsed inputs are portrait-oriented. "
                "Container structure and dimensions do not establish what the image depicts."
            ),
            caption_pattern="Unknown without OCR; no caption content is inferred.",
            pacing_pattern="Unknown from still previews; temporal pacing is not inferred.",
            reveal_pattern="Semantic fit and reveal/payoff capability cannot be verified from image container structure.",
            observable_features=[
                "bounded image container and dimensions parsed",
                "asset-search query provenance retained separately from pixel semantics",
                "no object, action, final-state, or payoff claim established",
            ],
            uncertainty=(
                "Deterministic zero-key inspection confirms decodable image structure only; semantic match, "
                "object labels, motion, captions, temporal ordering, and reveal capability remain unknown."
            ),
            confidence=0.2,
        )

    async def analyze_video(self, context: str, evidence_ids: list[str]) -> VideoEvidenceAnalysis:
        payload = _json_object(context)
        video = payload.get("video") if isinstance(payload.get("video"), dict) else {}
        browser = payload.get("browser_observation") if isinstance(payload.get("browser_observation"), dict) else {}
        structure = [str(item) for item in browser.get("observable_structure", []) if item]
        hook = str(browser.get("opening_visual") or browser.get("first_spoken_line") or "No opening hook was available")
        title = str(video.get("title") or "No public title was available")
        return VideoEvidenceAnalysis(
            video_id=str(video.get("video_id") or "unknown"),
            observed_hook=hook,
            audience_promise=title,
            narrative_structure=structure,
            mechanism_signals=structure,
            transcript_evidence_ids=list(dict.fromkeys(evidence_ids))[:1] if browser.get("transcript_segments") else [],
            supporting_evidence_ids=list(dict.fromkeys(evidence_ids)),
            uncertainty="Deterministic live interpretation is limited to the supplied public packet and cited observations.",
            confidence=.62 if evidence_ids else .35,
        )

    async def generate_ideas(self, context: str, evidence_ids: list[str]) -> IdeaGeneration:
        subject, format_label = _subject_and_format(context)
        ideas = [
            f"Test the cheapest workable version of {subject}",
            f"Compare beginner and expert approaches to {subject}",
            f"Rank five materials used for {subject}",
            f"Measure how scale changes {subject}",
            f"Find the fastest repeatable method for {subject}",
            f"Stress-test the durability of {subject}",
            f"Check whether temperature changes {subject}",
            f"Repeat {subject} in three different locations",
            f"Test the most common myth about {subject}",
            f"Show three failed attempts before a successful {subject}",
            f"Build an escalating difficulty challenge around {subject}",
            f"Explain the most common mistake in {subject}",
            f"Compare a standard tool with a household alternative for {subject}",
            f"Ask viewers to predict the outcome of {subject} before the proof",
            f"Reproduce the strongest observed {subject} result under one changed variable",
        ]
        return IdeaGeneration(
            ideas=ideas,
            repeatable_formats=[format_label],
            series_suggestions=[f"One observed mechanism, multiple {subject.lower()} variables"],
        )

    async def synthesize_candidate(self, context: str, evidence_ids: list[str]) -> CandidateSynthesis:
        payload = _json_object(context)
        decision = payload.get("deterministic_decision") if isinstance(payload.get("deterministic_decision"), dict) else {}
        cluster = payload.get("cluster") if isinstance(payload.get("cluster"), dict) else {}
        constraints = payload.get("production_constraints") if isinstance(payload.get("production_constraints"), list) else []
        label = str(cluster.get("label") or "candidate")
        verdict = str(decision.get("verdict") or "Insufficient evidence")
        return CandidateSynthesis(
            executive_summary=f"{label} retains the deterministic verdict {verdict}.",
            audience_demand_interpretation="Demand is represented only by the deterministic current-outlier and channel-cohort fields in the packet.",
            mechanism_thesis="The mechanism remains the evidence-cited hypothesis in the packet; no additional mechanism is invented.",
            repeatability_thesis="Repeatability depends on the immutable comparison, channel, and idea gates.",
            production_thesis=f"Submitted production constraints: {constraints or ['none specified']}.",
            differentiation="Test one observable packaging or structure difference while keeping the matched controls fixed.",
            risks=["Public observations cannot establish private retention or causal creator effects."],
            recommendation_rationale="The deterministic gates remain the sole decision authority.",
            first_test=["Run the smallest test allowed by the submitted production constraints."],
            continue_criteria=["Continue only if the observed mechanism reproduces without weakening any hard gate."],
            reject_criteria=["Reject if current replication, idea supply, footage feasibility, or saturation falls outside its gate."],
            supporting_evidence_ids=list(dict.fromkeys(evidence_ids)),
            confidence=min(.72, .4 + .02 * len(set(evidence_ids))),
        )

    async def critique(self, context: str, evidence_ids: list[str]) -> CriticAssessment:
        payload = _json_object(context)
        candidate_packet = payload.get("candidate_packet")
        if not isinstance(candidate_packet, dict):
            candidate_packet = payload
        deterministic = (
            candidate_packet.get("deterministic_decision")
            if isinstance(candidate_packet.get("deterministic_decision"), dict)
            else {}
        )
        gates = deterministic.get("hard_gates") if isinstance(deterministic.get("hard_gates"), dict) else {}
        blocking = [] if gates.get("all_passed") else ["One or more deterministic recommendation gates did not pass."]
        return CriticAssessment(
            challenges=["Creator-specific advantage, topic timing, and unobserved private retention remain alternative explanations."],
            confidence_adjustment=-.05,
            unsupported_claims=[],
            blocking_issues=blocking,
            missing_evidence=[] if evidence_ids else ["No evidence ledger IDs were supplied."],
            supporting_evidence_ids=list(dict.fromkeys(evidence_ids)),
        )

    async def synthesize_report(self, context: str, evidence_ids: list[str]) -> ReportSynthesis:
        payload = _json_object(context)
        candidates = payload.get("candidates") if isinstance(payload.get("candidates"), list) else []
        top = candidates[0] if candidates and isinstance(candidates[0], dict) else {}
        label = str(top.get("niche") or "No qualifying candidate")
        verdict = str(top.get("verdict") or "Insufficient evidence")
        return ReportSynthesis(
            executive_summary=f"The top adjudicated opportunity is {label}: {verdict}.",
            portfolio_interpretation="Ordering and verdicts are copied from post-adjudication deterministic candidate output.",
            why_now="Current-window YouTube evidence, not an invented external trend, supplies the timing claim.",
            primary_risk="Public evidence cannot prove retention, revenue, or causal creator advantage.",
            differentiation="Test an observed mechanism gap without copying source footage.",
            initial_shorts_test="Use the selected Shorts candidate's bounded first-test criteria when present.",
            initial_long_form_test="Use the selected long-form candidate's bounded first-test criteria when present.",
            continue_if="Continue only while all immutable hard gates and the candidate-specific criteria remain satisfied.",
            reject_if="Reject when a hard gate fails or the mechanism does not reproduce.",
            supporting_evidence_ids=list(dict.fromkeys(evidence_ids)),
            confidence=min(.7, .4 + .01 * len(set(evidence_ids))),
        )

    async def _inspect_images(self, refs: list[str]) -> list[dict[str, Any]]:
        observations: list[dict[str, Any]] = []
        async with httpx.AsyncClient(timeout=self.image_timeout, follow_redirects=True) as client:
            for ref in refs:
                parsed = urlparse(ref)
                raw: bytes | None = None
                if parsed.scheme == "https":
                    try:
                        async with client.stream("GET", ref, headers={"Accept": "image/*"}) as response:
                            response.raise_for_status()
                            content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
                            if not content_type.startswith("image/"):
                                continue
                            chunks: list[bytes] = []
                            total = 0
                            async for chunk in response.aiter_bytes():
                                total += len(chunk)
                                if total > MAX_IMAGE_BYTES:
                                    chunks = []
                                    break
                                chunks.append(chunk)
                            raw = b"".join(chunks) if chunks else None
                    except httpx.HTTPError:
                        continue
                elif not parsed.scheme:
                    path = Path(ref)
                    if path.is_file() and path.stat().st_size <= MAX_IMAGE_BYTES:
                        raw = path.read_bytes()
                image = _image_observation(raw)
                if image is not None:
                    observations.append(image)
        return observations


def _image_observation(raw: bytes | None) -> dict[str, Any] | None:
    """Validate common image containers and retain only non-semantic facts."""
    if not raw or len(raw) < 10:
        return None
    parsed = _parse_image_container(raw)
    if parsed is None:
        return None
    kind, width, height = parsed
    return {
        "container": kind,
        "size_bytes": len(raw),
        "width": width,
        "height": height,
        "portrait": bool(width and height and height > width),
    }


def _parse_image_container(raw: bytes) -> tuple[str, int, int] | None:
    if raw.startswith(b"\x89PNG\r\n\x1a\n"):
        dimensions = _parse_png(raw)
        return ("png", *dimensions) if dimensions else None
    if raw.startswith((b"GIF87a", b"GIF89a")):
        dimensions = _parse_gif(raw)
        return ("gif", *dimensions) if dimensions else None
    if raw.startswith(b"\xff\xd8\xff"):
        dimensions = _parse_jpeg(raw)
        return ("jpeg", *dimensions) if dimensions else None
    if raw.startswith(b"RIFF") and len(raw) >= 12 and raw[8:12] == b"WEBP":
        dimensions = _parse_webp(raw)
        return ("webp", *dimensions) if dimensions else None
    return None


def _parse_png(raw: bytes) -> tuple[int, int] | None:
    offset = 8
    width = height = 0
    saw_idat = False
    while offset + 12 <= len(raw):
        chunk_size = int.from_bytes(raw[offset : offset + 4], "big")
        chunk_type = raw[offset + 4 : offset + 8]
        data_start = offset + 8
        chunk_end = data_start + chunk_size
        next_offset = chunk_end + 4  # include CRC
        if chunk_end < data_start or next_offset > len(raw):
            return None
        if chunk_type == b"IHDR":
            if offset != 8 or chunk_size != 13:
                return None
            width = int.from_bytes(raw[data_start : data_start + 4], "big")
            height = int.from_bytes(raw[data_start + 4 : data_start + 8], "big")
        elif chunk_type == b"IDAT":
            saw_idat = saw_idat or chunk_size > 0
        elif chunk_type == b"IEND":
            if chunk_size != 0 or next_offset != len(raw):
                return None
            return (width, height) if width > 0 and height > 0 and saw_idat else None
        offset = next_offset
    return None


def _parse_gif(raw: bytes) -> tuple[int, int] | None:
    if len(raw) < 14 or raw[-1] != 0x3B or b"\x2c" not in raw[13:-1]:
        return None
    width = int.from_bytes(raw[6:8], "little")
    height = int.from_bytes(raw[8:10], "little")
    return (width, height) if width > 0 and height > 0 else None


def _parse_jpeg(raw: bytes) -> tuple[int, int] | None:
    if len(raw) < 12 or not raw.endswith(b"\xff\xd9"):
        return None
    sof_markers = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}
    offset = 2
    width = height = 0
    while offset < len(raw) - 2:
        if raw[offset] != 0xFF:
            return None
        while offset < len(raw) and raw[offset] == 0xFF:
            offset += 1
        if offset >= len(raw):
            return None
        marker = raw[offset]
        offset += 1
        if marker == 0xD9:
            break
        if marker in {0x01, *range(0xD0, 0xD8)}:
            continue
        if offset + 2 > len(raw):
            return None
        segment_size = int.from_bytes(raw[offset : offset + 2], "big")
        if segment_size < 2 or offset + segment_size > len(raw):
            return None
        data_start = offset + 2
        segment_end = offset + segment_size
        if marker in sof_markers:
            if segment_size < 7:
                return None
            height = int.from_bytes(raw[data_start + 1 : data_start + 3], "big")
            width = int.from_bytes(raw[data_start + 3 : data_start + 5], "big")
        if marker == 0xDA:
            scan_end = raw.rfind(b"\xff\xd9")
            if width <= 0 or height <= 0 or scan_end <= segment_end:
                return None
            return width, height
        offset = segment_end
    return None


def _parse_webp(raw: bytes) -> tuple[int, int] | None:
    if len(raw) < 30 or int.from_bytes(raw[4:8], "little") + 8 != len(raw):
        return None
    offset = 12
    while offset + 8 <= len(raw):
        chunk_type = raw[offset : offset + 4]
        chunk_size = int.from_bytes(raw[offset + 4 : offset + 8], "little")
        data_start = offset + 8
        chunk_end = data_start + chunk_size
        next_offset = chunk_end + (chunk_size % 2)
        if chunk_end < data_start or next_offset > len(raw):
            return None
        chunk = raw[data_start:chunk_end]
        if chunk_type == b"VP8 " and len(chunk) >= 10 and chunk[3:6] == b"\x9d\x01\x2a":
            width = int.from_bytes(chunk[6:8], "little") & 0x3FFF
            height = int.from_bytes(chunk[8:10], "little") & 0x3FFF
            return (width, height) if width > 0 and height > 0 else None
        if chunk_type == b"VP8L" and len(chunk) >= 5 and chunk[0] == 0x2F:
            width = 1 + chunk[1] + ((chunk[2] & 0x3F) << 8)
            height = 1 + ((chunk[2] >> 6) | (chunk[3] << 2) | ((chunk[4] & 0x0F) << 10))
            return width, height
        offset = next_offset
    return None


def _json_object(value: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _subject_and_format(context: str) -> tuple[str, str]:
    payload = _json_object(context)
    cluster = payload.get("cluster") if isinstance(payload.get("cluster"), dict) else {}
    classification = payload.get("classification") if isinstance(payload.get("classification"), dict) else {}
    subject = str(classification.get("niche") or cluster.get("label") or "").strip()
    format_label = str(classification.get("repeatable_format") or "").strip()
    observed_videos = payload.get("observed_videos") if isinstance(payload.get("observed_videos"), list) else []
    first_observed = observed_videos[0] if observed_videos and isinstance(observed_videos[0], dict) else {}
    if not subject:
        subject = str(first_observed.get("topic") or first_observed.get("title") or "").strip()[:120]
    if not format_label:
        format_label = str(first_observed.get("format") or "").strip()[:120]
    if not subject:
        first_line = next((line.strip() for line in context.splitlines() if line.strip()), "")
        subject = first_line.split(" |", 1)[0].strip()[:120]
        format_match = re.search(r"\bformat=([^|\n]+)", first_line)
        if format_match:
            format_label = format_match.group(1).strip()[:120]
    return subject or "Observed candidate topic", format_label or "Observed repeatable format"
