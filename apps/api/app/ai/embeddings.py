from __future__ import annotations

import math
import re
from typing import Protocol


class EmbeddingsProvider(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...


class DeterministicEmbeddingsProvider:
    """Small deterministic lexical-semantic vectors for every runtime mode.

    The provider has no learned weights, but unlike a digest of the complete
    string it preserves token overlap, character fragments, small inflections,
    and a bounded synonym vocabulary. It keeps clustering and semantic dedup
    reproducible without loading Torch or downloading a model into the worker.
    """

    dimensions = 384

    _synonyms = {
        "mug": "cup",
        "cups": "cup",
        "holding": "support",
        "hold": "support",
        "holds": "support",
        "held": "support",
        "supporting": "support",
        "supports": "support",
        "folded": "fold",
        "folding": "fold",
        "folds": "fold",
        "experiment": "test",
        "experiments": "test",
        "testing": "test",
        "tested": "test",
        "coins": "coin",
        "bridges": "bridge",
        "narrated": "story",
        "narrating": "story",
        "narration": "story",
        "narrative": "story",
        "narratives": "story",
        "storytelling": "story",
        "storyteller": "story",
        "stories": "story",
        "voiceover": "voice",
        "voiceovers": "voice",
    }

    def embed(self, texts: list[str]) -> list[list[float]]:
        output: list[list[float]] = []
        for text in texts:
            tokens = [_semantic_token(token, self._synonyms) for token in re.findall(r"[a-z0-9]+", text.lower())]
            tokens = [token for token in tokens if token and token not in _STOP_WORDS]
            weighted_features = [
                *((token, 1.0) for token in tokens),
                *((f"{left}_{right}", 0.55) for left, right in zip(tokens, tokens[1:])),
                *((f"#{fragment}", 0.2) for token in tokens for fragment in _character_fragments(token)),
            ]
            vector = [0.0] * self.dimensions
            for feature, weight in weighted_features:
                # FNV-1a is stable across Python processes (unlike hash()).
                bucket = _fnv1a(feature) % self.dimensions
                vector[bucket] += weight
            norm = math.sqrt(sum(value * value for value in vector)) or 1.0
            output.append([round(value / norm, 6) for value in vector])
        return output


class FakeEmbeddingsProvider(DeterministicEmbeddingsProvider):
    """Backward-compatible fixture name for deterministic embeddings."""


_STOP_WORDS = {
    "a", "after", "an", "and", "are", "can", "does", "for", "full", "how", "in", "is", "of",
    "on", "or", "the", "this", "to", "what", "when", "which", "will", "with",
}


def _semantic_token(token: str, synonyms: dict[str, str]) -> str:
    if token in synonyms:
        return synonyms[token]
    if len(token) > 5 and token.endswith("ing"):
        token = token[:-3]
    elif len(token) > 4 and token.endswith("ed"):
        token = token[:-2]
    elif len(token) > 4 and token.endswith("s"):
        token = token[:-1]
    return synonyms.get(token, token)


def _character_fragments(token: str) -> list[str]:
    padded = f"^{token}$"
    return [padded[index:index + 3] for index in range(max(0, len(padded) - 2))]


def _fnv1a(value: str) -> int:
    result = 2166136261
    for byte in value.encode("utf-8"):
        result ^= byte
        result = (result * 16777619) & 0xFFFFFFFF
    return result
