"""Deterministic live metadata normalization before AI interpretation."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import replace

from ..sources.base import VideoRecord


FORMAT_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("ranking escalation", ("rank", "top ", "best ", "worst ", "vs")),
    ("mystery evidence reveal", ("why", "mystery", "secret", "hidden", "reason")),
    ("failed attempts proof", ("test", "attempt", "fail", "can ", "proof", "experiment")),
    ("transformation reveal", ("before", "after", "restore", "transform", "makeover")),
    ("explainer demonstration", ("how", "explained", "works", "tutorial", "guide")),
)


def preprocess_video(record: VideoRecord) -> VideoRecord:
    text = " ".join([record.title, record.description, *record.tags]).lower()
    format_label = record.format_label or next(
        (label for label, signals in FORMAT_RULES if any(signal in text for signal in signals)),
        "demonstration",
    )
    topic = record.topic or _topic(record.title, record.tags)
    return replace(record, format_label=format_label, topic=topic)


def english_likelihood(text: str | None) -> float | None:
    if not text or not text.strip():
        return None
    letters = [character for character in text if character.isalpha()]
    latin_letters = sum("LATIN" in unicodedata.name(character, "") for character in letters)
    if letters and latin_letters / len(letters) < .5:
        # A predominantly non-Latin transcript is affirmative evidence that
        # it is not English, unlike a marker-free Latin technical transcript.
        return 0.0
    words = re.findall(r"[^\W\d_]+(?:'[^\W\d_]+)?", text.lower(), flags=re.UNICODE)
    if not words:
        return 0.0
    scores = {language: sum(word in markers for word in words) for language, markers in _LANGUAGE_MARKERS.items()}
    english_hits = scores["en"]
    competitor = max(scores[language] for language in ("es", "fr", "de", "pt"))
    # Latin script is shared by many languages and is not evidence of English.
    # Positive English lexical evidence must beat any explicit competing profile.
    if competitor >= 2 and competitor > english_hits:
        return 0.0
    if english_hits == 0:
        # Absence of our deliberately small English vocabulary is not
        # positive evidence of another language. Preserve it as unknown so a
        # technical English transcript is not rejected on missing markers.
        return None if competitor == 0 else 0.0
    denominator = max(min(len(words), 12), 1)
    lexical_share = english_hits / denominator
    margin = max(0, english_hits - competitor)
    return round(min(1.0, .42 + lexical_share * 1.8 + min(.22, margin * .07)), 3)


def _topic(title: str, tags: list[str]) -> str:
    if tags:
        return " ".join(tags[:3]).lower()
    stop = {"the", "a", "an", "and", "or", "to", "of", "in", "for", "this", "that", "why", "how"}
    words = [word.lower() for word in re.findall(r"[A-Za-z0-9]+", title) if word.lower() not in stop]
    return " ".join(words[:5]) or "unclassified topic"


_LANGUAGE_MARKERS: dict[str, set[str]] = {
    "en": {
        "a", "after", "again", "another", "are", "before", "can", "changes", "difference",
        "does", "down", "edge", "enter", "explain", "explains", "fail", "fails", "final",
        "first", "five", "for", "here", "historical", "hold", "holds", "in", "is", "it",
        "mystery", "now", "of", "old", "one", "paper", "result", "see", "shape", "slow",
        "stop", "strange", "surface", "than", "that", "the", "then", "this", "three", "to",
        "try", "watch", "we", "what", "why", "wins", "with", "works", "you",
    },
    "es": {
        "a", "ahora", "antes", "como", "con", "de", "después", "donde", "el", "ella", "en",
        "es", "esta", "este", "esto", "hace", "la", "las", "lo", "los", "más", "para", "pero",
        "por", "porque", "prueba", "que", "se", "sin", "sostiene", "su", "una", "uno", "y",
    },
    "fr": {
        "à", "après", "avec", "avant", "ce", "ces", "cette", "comme", "dans", "de", "des", "du",
        "elle", "en", "est", "et", "fait", "la", "le", "les", "mais", "ne", "pas", "pour", "que",
        "qui", "sans", "son", "sur", "une", "un",
    },
    "de": {
        "aber", "als", "auch", "auf", "aus", "bei", "das", "dem", "den", "der", "des", "die", "ein",
        "eine", "er", "es", "für", "im", "in", "ist", "mit", "nach", "nicht", "oder", "sie", "und",
        "von", "vor", "warum", "wie", "zu",
    },
    "pt": {
        "a", "agora", "antes", "após", "as", "com", "como", "da", "de", "depois", "do", "e", "ela",
        "ele", "em", "é", "esta", "este", "isso", "mais", "mas", "não", "o", "os", "para", "por",
        "porque", "que", "sem", "uma", "um",
    },
}
