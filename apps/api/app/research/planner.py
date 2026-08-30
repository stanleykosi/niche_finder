from __future__ import annotations

from dataclasses import dataclass, field
from itertools import islice

from ..domain.contracts import ResearchRunCreate
from ..domain.enums import RequestedFormat


# Empty-seed discovery is a reproducible cross-market portfolio. Each query is
# concrete enough to return actual content formats rather than generic
# "trending niche" advice videos.
BROAD_MARKET_PORTFOLIO: tuple[tuple[str, str], ...] = (
    ("science", "everyday science experiments"),
    ("history", "forgotten history stories"),
    ("technology", "new technology demonstrations"),
    ("engineering", "how everyday machines work"),
    ("nature", "surprising animal behavior explained"),
    ("food", "food science tests"),
    ("sports", "sports technique breakdown"),
    ("business", "business failure case studies"),
    ("consumer", "product comparison tests"),
    ("restoration", "before and after restoration"),
    ("psychology", "human behavior experiments"),
    ("geography", "hidden places local guides"),
    ("health", "healthy habit demonstrations"),
    ("careers", "day in the life unusual jobs"),
    ("language", "language mistakes explained"),
    ("art", "art technique transformations"),
    ("personal finance", "personal finance case studies"),
    ("home", "home organization transformations"),
    ("education", "difficult ideas visually explained"),
    ("culture", "cultural traditions explained"),
)


@dataclass
class ResearchPlan:
    queries: list[str]
    target_candidate_count: int
    max_expansion_depth: int
    discovery_strategy: str = "seeded"
    covered_markets: list[str] = field(default_factory=list)
    visited_queries: set[str] = field(default_factory=set)
    visited_channels: set[str] = field(default_factory=set)
    visited_videos: set[str] = field(default_factory=set)
    zero_yield_queries: int = 0

    def should_stop(self, new_candidates: int, query_index: int) -> bool:
        if new_candidates == 0:
            self.zero_yield_queries += 1
        else:
            self.zero_yield_queries = 0
        return query_index >= len(self.queries) or len(self.visited_videos) >= self.target_candidate_count or self.zero_yield_queries >= 2


class ResearchPlanner:
    def create(self, request: ResearchRunCreate) -> ResearchPlan:
        if not request.seeds:
            portfolio = BROAD_MARKET_PORTFOLIO[:request.limits.max_queries]
            queries = [_format_query(query, request.requested_format) for _, query in portfolio]
            strategy = "cross_market_portfolio"
            covered_markets = [market for market, _ in portfolio]
        else:
            expanded = request.broad_discovery or request.limits.deep_research
            queries = _bounded_seed_queries(
                request.seeds,
                request.limits.max_queries,
                expanded=expanded,
                include_examples=request.broad_discovery,
            )
            strategy = "seeded_expansion" if expanded else "seeded"
            covered_markets = []
        return ResearchPlan(
            queries=queries[:request.limits.max_queries],
            target_candidate_count=request.limits.max_videos,
            max_expansion_depth=request.limits.max_expansion_depth,
            discovery_strategy=strategy,
            covered_markets=covered_markets,
        )


def _format_query(query: str, requested_format: RequestedFormat) -> str:
    if requested_format == RequestedFormat.SHORTS:
        return f"{query} shorts"
    if requested_format == RequestedFormat.LONG_FORM:
        return f"{query} documentary"
    return query


def _bounded_seed_queries(
    seeds: list[str],
    maximum_queries: int,
    *,
    expanded: bool,
    include_examples: bool,
) -> list[str]:
    """Generate only the bounded query prefix, with every seed considered first."""
    if not expanded:
        return list(seeds[:maximum_queries])
    suffixes = ["", " shorts", " most viewed", " channels", " viral", " explained", " compilation"]
    if include_examples:
        suffixes.append(" examples")
    candidates = (
        f"{seed}{suffix}".strip()
        for suffix in suffixes
        for seed in seeds
    )
    return list(islice(dict.fromkeys(candidates), maximum_queries))
