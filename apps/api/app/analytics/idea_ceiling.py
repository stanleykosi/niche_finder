from __future__ import annotations

from typing import Any
from datetime import datetime, timezone

from ..ai.base import AIProvider
from ..ai.embeddings import EmbeddingsProvider
from ..research.dedup import deduplicate_ideas
from ..sources.base import VideoRecord


async def calculate_idea_ceiling(
    videos: list[VideoRecord],
    ai: AIProvider,
    evidence_ids: list[str],
    research_context: str = "",
    embeddings: EmbeddingsProvider | None = None,
) -> dict[str, Any]:
    video_lines: list[str] = []
    video_chars = 0
    for video in videos:
        line = (
            f"{video.title[:300]} | topic={video.topic[:200]} | format={video.format_label[:200]} "
            f"| channel={video.channel_id[:120]} | views={video.view_count}"
        )
        if video_lines and video_chars + len(line) + 1 > 8000:
            break
        video_lines.append(line)
        video_chars += len(line) + 1
    context = "\n".join(video_lines)
    if research_context:
        context += "\nResearch findings:\n" + research_context[:24000]
    context = context[:32000]
    generated = await ai.generate_ideas(context, evidence_ids)
    unique = deduplicate_ideas(generated.ideas, embeddings)
    topics = sorted({video.topic for video in videos if video.topic})
    now = datetime.now(timezone.utc)
    recent_topics = sorted({video.topic for video in videos if video.topic and (now - video.published_at).days <= 45})
    return {
        "generated_count": len(generated.ideas), "unique_count": len(unique),
        "duplicate_ratio": round(1 - len(unique) / max(len(generated.ideas), 1), 3),
        "topic_clusters": topics, "cluster_count": max(len(topics), 1),
        "recent_subject_clusters": recent_topics, "recent_subject_cluster_count": len(recent_topics),
        "fresh_subject_evidence": bool(recent_topics),
        "repeatable_formats": generated.repeatable_formats, "series_suggestions": generated.series_suggestions,
        "candidate_ideas": unique, "calculation_version": "idea-ceiling-v3-semantic", "evidence_ids": evidence_ids,
    }
