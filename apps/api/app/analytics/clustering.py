from __future__ import annotations

from dataclasses import dataclass
import re

from ..ai.embeddings import EmbeddingsProvider, FakeEmbeddingsProvider
from ..sources.base import VideoRecord


@dataclass(frozen=True)
class Cluster:
    label: str
    description: str
    video_ids: list[str]
    representative_video_ids: list[str]
    centroid: list[float]
    confidence: float


def _label(video: VideoRecord) -> str:
    if video.format_label:
        return video.format_label
    title = video.title.lower()
    if "rank" in title or "winner" in title:
        return "escalation ranking"
    if "mystery" in title or "unknown" in title:
        return "mystery evidence reveal"
    return "failed attempts proof explanation"


def cluster_videos(
    videos: list[VideoRecord],
    provider: EmbeddingsProvider | None = None,
    similarity_threshold: float = 0.55,
) -> list[Cluster]:
    if not videos:
        return []
    embedding_provider = provider or FakeEmbeddingsProvider()
    format_groups: dict[str, list[VideoRecord]] = {}
    for video in videos:
        format_groups.setdefault(_label(video), []).append(video)
    clusters: list[Cluster] = []
    for format_label, items in format_groups.items():
        ordered = sorted(items, key=lambda item: item.youtube_video_id)
        semantic_texts = [f"{item.topic}. {item.title}" for item in ordered]
        vectors = embedding_provider.embed(semantic_texts)
        topic_groups: list[list[tuple[VideoRecord, list[float]]]] = []
        for item, vector in zip(ordered, vectors, strict=True):
            similarities = [_cosine(vector, _centroid([member_vector for _, member_vector in group])) for group in topic_groups]
            best = max(range(len(similarities)), key=similarities.__getitem__) if similarities else None
            if best is not None and similarities[best] >= similarity_threshold:
                topic_groups[best].append((item, vector))
            else:
                topic_groups.append([(item, vector)])
        for group in topic_groups:
            group_items = [item for item, _ in group]
            centroid = _centroid([vector for _, vector in group])
            topic_label = _topic_label(group_items)
            label = f"{format_label}: {topic_label}"
            representatives = [item.youtube_video_id for item in sorted(group_items, key=lambda item: item.view_count, reverse=True)[:3]]
            clusters.append(Cluster(
                label,
                f"A semantic {topic_label} topic cluster using the repeated {format_label} format with {len(group_items)} observed uploads.",
                [item.youtube_video_id for item in group_items],
                representatives,
                centroid,
                min(0.98, 0.64 + len(group_items) * 0.06),
            ))
    return clusters


def representative_video(videos: list[VideoRecord]) -> VideoRecord | None:
    return max(videos, key=lambda video: video.view_count, default=None)


def _centroid(vectors: list[list[float]]) -> list[float]:
    if not vectors:
        return []
    averaged = [sum(vector[index] for vector in vectors) / len(vectors) for index in range(len(vectors[0]))]
    norm = sum(value * value for value in averaged) ** .5 or 1.0
    return [round(value / norm, 6) for value in averaged]


def _cosine(left: list[float], right: list[float]) -> float:
    if not left or len(left) != len(right):
        return 0.0
    return sum(a * b for a, b in zip(left, right, strict=True))


def _topic_label(videos: list[VideoRecord]) -> str:
    topics = [video.topic.strip().lower() for video in videos if video.topic.strip()]
    if topics:
        return max(topics, key=lambda topic: (sum(topic == candidate for candidate in topics), -len(topic), topic))
    words = [word for video in videos for word in re.findall(r"[a-z0-9]+", video.title.lower())]
    stop = {"a", "an", "and", "for", "how", "of", "the", "to", "what", "why", "with"}
    frequent = sorted({word for word in words if word not in stop}, key=lambda word: (-words.count(word), word))
    return " ".join(frequent[:3]) or "unclassified topic"
