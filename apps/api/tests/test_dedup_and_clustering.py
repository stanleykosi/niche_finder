from apps.api.app.research.dedup import canonical_video_id, deduplicate_ideas, semantic_key
from apps.api.app.analytics.clustering import cluster_videos
from apps.api.app.ai.embeddings import DeterministicEmbeddingsProvider
from apps.api.app.sources.fixture_youtube import FixtureYoutubeSource
from apps.api.app.sources.base import VideoRecord
import asyncio
from datetime import datetime, timezone


def test_url_canonicalization_and_semantic_dedup():
    assert canonical_video_id("https://www.youtube.com/watch?v=abc&list=1") == "abc"
    assert canonical_video_id("https://youtu.be/abc") == "abc"
    assert semantic_key("How to test a paper bridge") == semantic_key("paper bridge test")
    assert len(deduplicate_ideas(["The paper bridge test", "paper bridge test", "A coin test"])) == 2


def test_fixture_embeddings_cluster_stably():
    source = FixtureYoutubeSource("strong")
    videos = asyncio.run(source.enrich_videos(["v-bridge-01", "v-bridge-02", "v-paper-01"]))
    first = cluster_videos(videos)
    second = cluster_videos(videos)
    assert [cluster.label for cluster in first] == [cluster.label for cluster in second]
    assert first[0].representative_video_ids


def test_semantic_dedup_collapses_paraphrases_with_different_token_sets():
    ideas = [
        "Can a folded-paper bridge support a full cup?",
        "Will a paper bridge hold a mug after folding?",
        "Which surface stops a spinning coin fastest?",
    ]
    assert deduplicate_ideas(ideas) == [ideas[0], ideas[2]]


def test_live_deterministic_embeddings_match_storytelling_variants():
    provider = DeterministicEmbeddingsProvider()
    story, narration, unrelated = provider.embed([
        "faceless storytelling channel",
        "narrated stories with voiceover",
        "daily football transfer analysis",
    ])

    def similarity(left, right):
        return sum(a * b for a, b in zip(left, right))

    assert similarity(story, narration) > similarity(story, unrelated)


def test_same_format_is_partitioned_into_semantic_topic_clusters():
    now = datetime.now(timezone.utc)
    common = {
        "channel_id": "channel",
        "description": "",
        "duration_seconds": 40,
        "published_at": now,
        "category_id": "27",
        "tags": [],
        "thumbnails": {},
        "view_count": 100,
        "format_label": "failed attempts proof",
    }
    videos = [
        VideoRecord("bridge-a", canonical_url="https://youtube/bridge-a", title="Folded paper bridge holds a mug", topic="paper bridge strength", **common),
        VideoRecord("bridge-b", canonical_url="https://youtube/bridge-b", title="Paper bridge supports a cup after folding", topic="paper bridge strength", **common),
        VideoRecord("coin-a", canonical_url="https://youtube/coin-a", title="Spinning coin stops on rough surfaces", topic="coin surface friction", **common),
    ]
    clusters = cluster_videos(videos)
    assert len(clusters) == 2
    assert sorted(len(cluster.video_ids) for cluster in clusters) == [1, 2]
