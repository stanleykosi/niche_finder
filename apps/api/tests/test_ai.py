import asyncio

import pytest
from pydantic import ValidationError

from apps.api.app.ai.fake import FakeAIProvider
from apps.api.app.ai.schemas import IdeaGeneration, NicheClassification
from apps.api.app.research.evidence_packets import adjudicate_llm_output, transcript_segments, validate_citations


def test_fake_ai_returns_structured_evidence_bound_output():
    result = asyncio.run(FakeAIProvider().viral_mechanism("paper proof", ["evidence-1"]))
    assert result.supporting_evidence_ids == ["evidence-1"]
    assert result.primary_mechanism


def test_invalid_structured_output_is_rejected():
    with pytest.raises(ValidationError):
        NicheClassification.model_validate({"niche": "missing fields"})


def test_model_generated_idea_fanout_is_schema_bounded():
    assert len(IdeaGeneration(ideas=[f"idea {index}" for index in range(30)]).ideas) == 30
    with pytest.raises(ValidationError):
        IdeaGeneration(ideas=[f"idea {index}" for index in range(31)])


def test_transcript_segments_preserve_missing_timestamp_provenance():
    segments = transcript_segments("First observed sentence. " * 100, max_segment_chars=120, max_segments=3)
    assert len(segments) == 3
    assert all(segment["timestamps_available"] is False for segment in segments)
    assert all(segment["start_seconds"] is None for segment in segments)


def test_unknown_ai_citations_are_rejected():
    result = validate_citations(["known", "invented"], ["known"])
    assert result["passed"] is False
    assert result["valid_evidence_ids"] == ["known"]
    assert result["invalid_evidence_ids"] == ["invented"]


def test_critic_can_block_but_never_promote_a_deterministic_verdict():
    gates = {"all_passed": False}
    result = adjudicate_llm_output(
        "Start now", .9, gates,
        {"passed": True}, {"confidence_adjustment": -.1, "blocking_issues": []}, {"passed": True},
    )
    assert result["final_verdict"] == "Insufficient evidence"
    assert result["final_confidence"] == .8
