from apps.api.app.domain.contracts import ResearchRunCreate
from apps.api.app.domain.enums import RequestedFormat
from apps.api.app.research.planner import BROAD_MARKET_PORTFOLIO, ResearchPlanner


def test_empty_seed_uses_concrete_cross_market_portfolio():
    request = ResearchRunCreate(
        seeds=[],
        broad_discovery=True,
        requested_format=RequestedFormat.BOTH,
        limits={"max_queries": 12, "max_results_per_query": 8, "max_channels": 30, "max_videos": 80, "max_expansion_depth": 1},
    )
    plan = ResearchPlanner().create(request)
    assert plan.discovery_strategy == "cross_market_portfolio"
    assert len(plan.queries) == 12
    assert len(plan.covered_markets) == 12
    assert plan.queries == [query for _, query in BROAD_MARKET_PORTFOLIO[:12]]
    assert all("emerging" not in query and "best niche" not in query for query in plan.queries)


def test_market_portfolio_respects_requested_format_and_query_bound():
    request = ResearchRunCreate(
        seeds=[],
        requested_format=RequestedFormat.SHORTS,
        limits={"max_queries": 3, "max_results_per_query": 8, "max_channels": 10, "max_videos": 30, "max_expansion_depth": 1},
    )
    plan = ResearchPlanner().create(request)
    assert len(plan.queries) == 3
    assert all(query.endswith(" shorts") for query in plan.queries)


def test_explicit_seeds_are_not_replaced_by_market_portfolio():
    request = ResearchRunCreate(seeds=["paper bridge tests"], broad_discovery=False)
    plan = ResearchPlanner().create(request)
    assert plan.discovery_strategy == "seeded"
    assert plan.queries == ["paper bridge tests"]
    assert plan.covered_markets == []


def test_seed_expansion_is_generated_lazily_and_covers_seeds_before_variants():
    request = ResearchRunCreate(
        seeds=["paper bridges", "coin tests", "food science", "restoration"],
        broad_discovery=True,
        limits={"max_queries": 3},
    )
    plan = ResearchPlanner().create(request)
    assert plan.queries == ["paper bridges", "coin tests", "food science"]


def test_api_defaults_preserve_fast_and_deep_empty_seed_portfolios():
    fast = ResearchRunCreate()
    deep = ResearchRunCreate(limits={"deep_research": True})
    explicitly_bounded = ResearchRunCreate(limits={"deep_research": True, "max_queries": 4})
    assert fast.limits.max_queries == 12
    assert len(ResearchPlanner().create(fast).queries) == 12
    assert deep.limits.max_queries == 20
    assert len(ResearchPlanner().create(deep).queries) == 20
    assert explicitly_bounded.limits.max_queries == 4
