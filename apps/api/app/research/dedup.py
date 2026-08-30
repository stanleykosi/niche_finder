from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

from ..ai.embeddings import EmbeddingsProvider, FakeEmbeddingsProvider


def canonical_video_id(value: str) -> str:
    if "youtube.com" in value or "youtu.be" in value:
        parsed = urlparse(value)
        if parsed.netloc.endswith("youtu.be"):
            return parsed.path.strip("/").split("/")[0]
        query_id = parse_qs(parsed.query).get("v", [""])[0]
        if query_id:
            return query_id
        match = re.search(r"/(?:shorts|embed)/([^/?]+)", parsed.path)
        if match:
            return match.group(1)
    return value.strip()


def canonical_channel_id(value: str) -> str:
    if "/channel/" in value:
        return value.split("/channel/", 1)[1].split("/", 1)[0]
    return value.strip()


def semantic_key(text: str) -> str:
    stop = {"the", "a", "an", "and", "or", "with", "how", "can", "to", "of"}
    words = re.findall(r"[a-z0-9]+", text.lower())
    return " ".join(sorted(set(word for word in words if word not in stop)))


def deduplicate_ideas(
    ideas: list[str],
    provider: EmbeddingsProvider | None = None,
    similarity_threshold: float = 0.78,
) -> list[str]:
    """Keep the first representative of each semantic idea.

    Exact normalized keys are a fast path.  Embedding cosine similarity catches
    paraphrases whose nouns or verbs differ (for example cup/mug and
    hold/support) so AI wording cannot inflate the hard idea-ceiling gate.
    """
    if not ideas:
        return []
    vectors = (provider or FakeEmbeddingsProvider()).embed(ideas)
    seen: set[str] = set()
    retained_vectors: list[list[float]] = []
    unique: list[str] = []
    for idea, vector in zip(ideas, vectors, strict=True):
        key = semantic_key(idea)
        if not key or key in seen:
            continue
        if any(_cosine(vector, retained) >= similarity_threshold for retained in retained_vectors):
            continue
        seen.add(key)
        retained_vectors.append(vector)
        unique.append(idea)
    return unique


def _cosine(left: list[float], right: list[float]) -> float:
    if not left or len(left) != len(right):
        return 0.0
    return sum(a * b for a, b in zip(left, right, strict=True))
