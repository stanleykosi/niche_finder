import asyncio
from datetime import datetime, timezone

from apps.api.app.research.preprocessing import english_likelihood, preprocess_video
from apps.api.app.sources.base import BrowserMediaRecord, VideoRecord
from apps.api.app.sources.media_analysis import PassthroughMediaAnalyzer


def _video() -> VideoRecord:
    return VideoRecord("v", "c", "https://www.youtube.com/watch?v=v", "Why this paper bridge test works", "Three failed attempts", 42, datetime.now(timezone.utc), "27", ["paper", "bridge"], {}, 100)


def test_metadata_preprocessing_supplies_live_topic_and_format():
    result = preprocess_video(_video())
    assert result.topic == "paper bridge"
    assert result.format_label == "mystery evidence reveal"


def test_passthrough_analyzer_records_english_and_selective_filmstrip_method():
    media = BrowserMediaRecord("fixture", True, "This is the proof and it works.", None, ["frame"], None, None, [], datetime.now(timezone.utc), .8)
    result = asyncio.run(PassthroughMediaAnalyzer().analyze("fixture-run", _video(), media))
    assert result.visual_features["english_likelihood"] == english_likelihood(media.visible_transcript)
    assert "selective_filmstrip" in result.visual_features["analysis_method"]


def test_latin_script_is_not_mistaken_for_english():
    assert english_likelihood("Este puente de papel sostiene una taza después de tres pliegues.") == 0.0
    assert english_likelihood("Ce pont en papier tient une tasse après trois plis.") == 0.0
    assert english_likelihood("Diese Papierbrücke hält eine Tasse nach drei Faltungen.") == 0.0
    assert (english_likelihood("This paper bridge holds a mug after three folds.") or 0) >= .55


def test_marker_free_technical_transcript_remains_unknown_not_negative():
    assert english_likelihood("Quantum entanglement Bell photons spin correlation") is None
