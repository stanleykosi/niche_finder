"""Evidence packet construction and deterministic LLM-output adjudication.

The AI layer receives bounded, source-labelled packets. It may interpret those
facts, but it cannot create metrics, pass hard gates, or cite records outside the
run ledger.
"""

from __future__ import annotations

import re
from typing import Any

from ..domain.enums import Verdict


POSITIVE_VERDICTS = {
    Verdict.START_NOW.value,
    Verdict.RUN_TEST.value,
    Verdict.SHORTS_ONLY.value,
    Verdict.LONG_FORM_ONLY.value,
}


def transcript_segments(text: str | None, *, max_segment_chars: int = 700, max_segments: int = 8) -> list[dict[str, Any]]:
    """Create bounded transcript excerpts without inventing unavailable timing."""
    if not text or not text.strip():
        return []
    normalized = re.sub(r"\s+", " ", text).strip()
    segments: list[dict[str, Any]] = []
    cursor = 0
    while cursor < len(normalized) and len(segments) < max_segments:
        end = min(len(normalized), cursor + max_segment_chars)
        if end < len(normalized):
            boundary = normalized.rfind(" ", cursor, end)
            if boundary > cursor:
                end = boundary
        excerpt = normalized[cursor:end].strip()
        if excerpt:
            segments.append({
                "index": len(segments),
                "text": excerpt,
                "character_start": cursor,
                "character_end": end,
                "start_seconds": None,
                "end_seconds": None,
                "timestamps_available": False,
            })
        cursor = end + 1
    return segments


def validate_citations(referenced_ids: list[str], allowed_ids: list[str]) -> dict[str, Any]:
    """Reject unknown evidence references while retaining a complete audit."""
    allowed = set(allowed_ids)
    unique = list(dict.fromkeys(str(value) for value in referenced_ids))
    valid = [value for value in unique if value in allowed]
    invalid = [value for value in unique if value not in allowed]
    return {
        "passed": bool(valid) and not invalid,
        "valid_evidence_ids": valid,
        "invalid_evidence_ids": invalid,
        "referenced_count": len(unique),
        "allowed_count": len(allowed),
    }


def adjudicate_llm_output(
    verdict: str,
    confidence: float,
    hard_gates: dict[str, Any],
    synthesis_citations: dict[str, Any],
    critic: dict[str, Any],
    critic_citations: dict[str, Any],
) -> dict[str, Any]:
    """Allow AI to lower confidence, never to override deterministic gates."""
    all_gates_pass = bool(hard_gates.get("all_passed"))
    citation_pass = bool(synthesis_citations.get("passed")) and bool(critic_citations.get("passed"))
    blocking_issues = list(critic.get("blocking_issues", []))
    final_verdict = verdict
    reasons: list[str] = []
    if not all_gates_pass and verdict in POSITIVE_VERDICTS:
        final_verdict = Verdict.INSUFFICIENT.value
        reasons.append("One or more deterministic recommendation gates failed.")
    if not citation_pass and final_verdict in POSITIVE_VERDICTS:
        final_verdict = Verdict.INSUFFICIENT.value
        reasons.append("The synthesis or critic cited evidence outside the run ledger.")
    if blocking_issues and final_verdict in POSITIVE_VERDICTS:
        final_verdict = Verdict.INSUFFICIENT.value
        reasons.append("The independent critic identified an unresolved blocking issue.")
    adjustment = min(0.0, float(critic.get("confidence_adjustment", 0)))
    final_confidence = round(max(0.0, min(1.0, confidence + adjustment)), 3)
    return {
        "input_verdict": verdict,
        "final_verdict": final_verdict,
        "input_confidence": confidence,
        "final_confidence": final_confidence,
        "deterministic_gates_passed": all_gates_pass,
        "citation_validation_passed": citation_pass,
        "critic_blocking_issues": blocking_issues,
        "reasons": reasons or ["Deterministic gates and evidence-reference validation were preserved."],
    }
