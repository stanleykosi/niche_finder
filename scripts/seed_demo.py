from __future__ import annotations

import asyncio
import json

import httpx


def demo_payload() -> dict[str, object]:
    return {
        "requested_format": "both",
        "language": "English",
        "regions": ["US"],
        "seeds": ["paper bridge"],
        "broad_discovery": False,
        "recency_days": 90,
        "production_constraints": [],
        "minimum_idea_ceiling": 12,
        "maximum_saturation": .75,
        "limits": {
            "max_queries": 2,
            "max_results_per_query": 12,
            "max_channels": 6,
            "max_videos": 12,
            "max_expansion_depth": 0,
            "deep_research": False,
        },
    }


async def main() -> None:
    from apps.api.app.core.config import AppMode, Settings
    from apps.api.app.main import create_app

    app = create_app(Settings(app_mode=AppMode.CLOSED_TEST, ai_provider="fake", database_url="sqlite:///./runtime/demo.db"))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://demo") as client:
        response = await client.post("/api/research-runs", json=demo_payload())
        response.raise_for_status()
        report = await client.get(f"/api/research-runs/{response.json()['id']}/report")
        report.raise_for_status()
        print(json.dumps(report.json(), indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(main())
