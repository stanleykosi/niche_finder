from __future__ import annotations

import math
import re
from typing import Protocol


class EmbeddingsProvider(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...


class FakeEmbeddingsProvider:
    """Deterministic lexical-semantic vectors for closed testing.

    The fake deliberately has no learned weights, but unlike a digest of the
    complete string it preserves token overlap, small inflections and a bounded
    synonym vocabulary.  That makes the same clustering and semantic-dedup
    algorithms testable without downloading a model.
    """

    dimensions = 256

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
    }

    def embed(self, texts: list[str]) -> list[list[float]]:
        output: list[list[float]] = []
        for text in texts:
            tokens = [_semantic_token(token, self._synonyms) for token in re.findall(r"[a-z0-9]+", text.lower())]
            tokens = [token for token in tokens if token and token not in _STOP_WORDS]
            features = [*tokens, *(f"{left}_{right}" for left, right in zip(tokens, tokens[1:]))]
            vector = [0.0] * self.dimensions
            for feature in features:
                # FNV-1a is stable across Python processes (unlike hash()).
                bucket = _fnv1a(feature) % self.dimensions
                vector[bucket] += 1.0 if "_" not in feature else 0.55
            norm = math.sqrt(sum(value * value for value in vector)) or 1.0
            output.append([round(value / norm, 6) for value in vector])
        return output


class SentenceTransformersProvider:
    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        self._model = None

    def embed(self, texts: list[str]) -> list[list[float]]:
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer  # type: ignore
            except ImportError as exc:
                raise RuntimeError("sentence-transformers is required for live embeddings") from exc
            self._model = SentenceTransformer(self.model_name)
        return self._model.encode(texts, normalize_embeddings=True).tolist()


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


def _fnv1a(value: str) -> int:
    result = 2166136261
    for byte in value.encode("utf-8"):
        result ^= byte
        result = (result * 16777619) & 0xFFFFFFFF
    return result
