"""Rights-aware visual asset preflight. YouTube videos are evidence, never reusable assets."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

from ..core.config import AppMode
from ..core.errors import ClosedModeViolation


MAX_ASSET_IDEAS = 30


@dataclass(frozen=True)
class AssetResult:
    idea: str
    video_count: int
    image_count: int
    sources: list[str]
    rights_metadata_present: bool
    visual_payoff_feasible: bool
    reveal_clip_count: int = 0
    portrait_clip_count: int = 0
    assets: list[dict[str, Any]] = field(default_factory=list)
    semantic_fit: bool | None = None
    semantic_fit_confidence: float | None = None
    semantic_fit_reason: str | None = None
    reveal_validation_confidence: float | None = None
    reveal_validation_reason: str | None = None
    provider_errors: list[dict[str, Any]] = field(default_factory=list)


class AssetConnector(Protocol):
    async def search(self, ideas: list[str]) -> list[AssetResult]: ...


class AssetRunSession:
    """Run-scoped cache and phase-aware hard budget around an asset connector.

    Preliminary searches may use only the preflight allocation.  The reserved
    final allocation cannot be consumed before authoritative candidate ideas
    have been generated.  Budget rejections are deliberately not cached so an
    idea deferred during preflight can still be admitted during the final pass.
    """

    def __init__(
        self,
        connector: AssetConnector,
        maximum_ideas: int = MAX_ASSET_IDEAS,
        final_reserve: int = 10,
    ) -> None:
        self.connector = connector
        self.maximum_ideas = max(1, min(MAX_ASSET_IDEAS, int(maximum_ideas)))
        self.final_reserve = max(1, min(self.maximum_ideas, int(final_reserve)))
        self.preflight_capacity = self.maximum_ideas - self.final_reserve
        self.max_concurrency = getattr(connector, "max_concurrency", 1)
        self._claimed: set[str] = set()
        self._preflight_claimed: set[str] = set()
        self._cache: dict[str, AssetResult] = {}

    @classmethod
    def for_final_candidate(
        cls,
        connector: AssetConnector,
        maximum_ideas: int = MAX_ASSET_IDEAS,
    ) -> "AssetRunSession":
        """Create an independent authoritative budget with at least ten checks."""
        candidate_capacity = max(10, min(MAX_ASSET_IDEAS, int(maximum_ideas)))
        return cls(
            connector,
            maximum_ideas=candidate_capacity,
            final_reserve=candidate_capacity,
        )

    async def search(
        self,
        ideas: list[str],
        *,
        phase: str = "final",
        maximum_new_ideas: int | None = None,
    ) -> list[AssetResult]:
        if phase not in {"preflight", "final"}:
            raise ValueError("asset search phase must be 'preflight' or 'final'")
        ordered = list(dict.fromkeys(idea.strip() for idea in ideas if idea.strip()))
        unseen = [idea for idea in ordered if idea not in self._claimed]
        phase_ceiling = self.preflight_capacity if phase == "preflight" else self.maximum_ideas
        remaining = max(0, phase_ceiling - len(self._claimed))
        if maximum_new_ideas is not None:
            remaining = min(remaining, max(0, int(maximum_new_ideas)))
        admitted = unseen[:remaining]
        self._claimed.update(admitted)
        if phase == "preflight":
            self._preflight_claimed.update(admitted)
        if admitted:
            raw = await self.connector.search(admitted)
            returned = {result.idea: result for result in raw}
            for idea in admitted:
                self._cache[idea] = returned.get(idea) or _unavailable_asset_result(
                    idea, "connector returned no typed result"
                )
        return [
            self._cache.get(idea) or _unavailable_asset_result(
                idea,
                f"run-level asset idea budget unavailable during {phase} allocation",
            )
            for idea in ordered
        ]

    def budget_status(self) -> dict[str, Any]:
        return {
            "maximum_ideas": self.maximum_ideas,
            "claimed_ideas": len(self._claimed),
            "remaining_ideas": max(0, self.maximum_ideas - len(self._claimed)),
            "preflight_capacity": self.preflight_capacity,
            "preflight_claimed_ideas": len(self._preflight_claimed),
            "final_reserved_ideas": self.final_reserve,
        }


class FixtureAssetConnector:
    async def search(self, ideas: list[str]) -> list[AssetResult]:
        results = []
        for index, idea in enumerate(ideas):
            supported = index % 5 != 0
            sources = ["fixture://pexels", "fixture://commons"] if supported else ["fixture://manifest"]
            results.append(AssetResult(idea, 4 if supported else 1, 3, sources, True, supported, 2 if supported else 0, 3 if supported else 0, [{"source": source, "license": "fixture-approved", "reusable": True} for source in sources], supported, .95 if supported else .2))
        return results


class LiveAssetConnector:
    def __init__(
        self,
        mode: AppMode,
        pexels_api_key: str | None = None,
        pixabay_api_key: str | None = None,
        user_agent: str = "NicheIntel/1.0",
        max_ideas: int = MAX_ASSET_IDEAS,
        max_concurrency: int = 4,
    ) -> None:
        if mode == AppMode.CLOSED_TEST:
            raise ClosedModeViolation("live asset connectors are disabled in closed_test mode")
        self.pexels_api_key = pexels_api_key
        self.pixabay_api_key = pixabay_api_key
        self.user_agent = user_agent
        self.max_ideas = max(1, min(MAX_ASSET_IDEAS, int(max_ideas)))
        self.max_concurrency = max(1, min(16, int(max_concurrency)))

    async def search(self, ideas: list[str]) -> list[AssetResult]:
        bounded_ideas = list(dict.fromkeys(idea.strip() for idea in ideas if idea.strip()))[:self.max_ideas]
        semaphore = asyncio.Semaphore(self.max_concurrency)
        async with httpx.AsyncClient(timeout=20, headers={"User-Agent": self.user_agent}) as client:
            async def bounded_search(idea: str) -> AssetResult:
                async with semaphore:
                    return await self._search_one(idea, client)

            return list(await asyncio.gather(*(bounded_search(idea) for idea in bounded_ideas)))

    async def _search_one(self, idea: str, client: httpx.AsyncClient) -> AssetResult:
        assets: list[dict[str, Any]] = []
        provider_errors: list[dict[str, Any]] = []
        providers: list[tuple[str, str, dict[str, Any], dict[str, str] | None, Any]] = []
        if self.pexels_api_key:
            providers.append((
                "pexels", "https://api.pexels.com/videos/search",
                {"query": idea, "per_page": 8, "orientation": "portrait"},
                {"Authorization": self.pexels_api_key, "User-Agent": self.user_agent},
                _pexels_assets,
            ))
        if self.pixabay_api_key:
            providers.append((
                "pixabay", "https://pixabay.com/api/videos/",
                {"key": self.pixabay_api_key, "q": idea, "per_page": 8, "safesearch": "true"},
                None,
                _pixabay_assets,
            ))
        providers.extend([
            (
                "wikimedia_commons_web_search", "https://commons.wikimedia.org/w/api.php",
                {"action": "query", "generator": "search", "gsrsearch": f"filetype:video {idea}", "gsrnamespace": 6, "gsrlimit": 8, "prop": "imageinfo", "iiprop": "url|mime|extmetadata", "iiurlwidth": 640, "format": "json", "origin": "*"},
                None,
                _commons_assets,
            ),
            (
                "internet_archive_web_search", "https://archive.org/advancedsearch.php",
                {"q": f'title:({idea}) AND mediatype:(movies)', "fl[]": ["identifier", "title", "licenseurl"], "rows": 8, "page": 1, "output": "json"},
                None,
                _archive_assets,
            ),
        ])
        for provider, url, params, headers, parser in providers:
            try:
                response = await client.get(url, params=params, headers=headers)
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict):
                    raise ValueError("provider response must be an object")
                assets.extend(parser(payload))
            except Exception as exc:
                provider_errors.append(_provider_failure(provider, exc))
        videos = [asset for asset in assets if asset.get("reusable")]
        sources = sorted({asset["source"] for asset in videos})
        return AssetResult(
            idea, len(videos), 0, sources,
            any(bool(asset.get("license")) for asset in videos),
            False,
            0,
            sum(bool(asset.get("portrait")) for asset in videos),
            assets,
            provider_errors=provider_errors,
        )


def _pexels_assets(payload: dict[str, Any]) -> list[dict[str, Any]]:
    items = payload.get("videos", [])
    if not isinstance(items, list):
        raise ValueError("Pexels videos must be a list")
    return [
        {
            "source": "pexels", "id": str(item.get("id")), "url": item.get("url"),
            "preview_ref": item.get("image"), "license": "Pexels license", "reusable": True,
            "portrait": float(item.get("height") or 0) >= float(item.get("width") or 0),
        }
        for item in items if isinstance(item, dict)
    ]


def _pixabay_assets(payload: dict[str, Any]) -> list[dict[str, Any]]:
    items = payload.get("hits", [])
    if not isinstance(items, list):
        raise ValueError("Pixabay hits must be a list")
    assets: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        videos = item.get("videos", {})
        if not isinstance(videos, dict):
            raise ValueError("Pixabay video variants must be an object")
        preview = next(
            (value.get("thumbnail") or value.get("url") for value in videos.values() if isinstance(value, dict)),
            None,
        )
        assets.append({
            "source": "pixabay", "id": str(item.get("id")), "url": item.get("pageURL"),
            "preview_ref": preview, "license": "Pixabay Content License", "reusable": True,
            "portrait": False,
        })
    return assets


def _commons_assets(payload: dict[str, Any]) -> list[dict[str, Any]]:
    pages = payload.get("query", {}).get("pages", {})
    if not isinstance(pages, dict):
        raise ValueError("Commons pages must be an object")
    assets: list[dict[str, Any]] = []
    for item in pages.values():
        if not isinstance(item, dict):
            continue
        image_info = item.get("imageinfo") or [{}]
        if not isinstance(image_info, list) or not image_info or not isinstance(image_info[0], dict):
            continue
        info = image_info[0]
        if not str(info.get("mime", "")).startswith("video/"):
            continue
        metadata = info.get("extmetadata") or {}
        if not isinstance(metadata, dict):
            metadata = {}
        license_name = (metadata.get("LicenseShortName") or {}).get("value")
        assets.append({
            "source": "wikimedia_commons_web_search", "id": str(item.get("pageid")),
            "url": info.get("descriptionurl"), "preview_ref": info.get("thumburl") or info.get("url"),
            "license": license_name, "reusable": bool(license_name), "portrait": False,
        })
    return assets


def _archive_assets(payload: dict[str, Any]) -> list[dict[str, Any]]:
    items = payload.get("response", {}).get("docs", [])
    if not isinstance(items, list):
        raise ValueError("Internet Archive docs must be a list")
    assets: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        identifier = str(item.get("identifier") or "")
        if identifier:
            license_url = item.get("licenseurl")
            assets.append({
                "source": "internet_archive_web_search", "id": identifier,
                "url": f"https://archive.org/details/{identifier}",
                "preview_ref": f"https://archive.org/services/img/{identifier}",
                "license": license_url,
                "rights_status": "known" if license_url else "unknown",
                "reusable": True if license_url else None,
                "portrait": False,
            })
    return assets


def _provider_failure(provider: str, exc: Exception) -> dict[str, Any]:
    diagnostic: dict[str, Any] = {
        "provider": provider,
        "status": "unavailable",
        "error_type": type(exc).__name__,
    }
    if isinstance(exc, httpx.HTTPStatusError):
        diagnostic["status_code"] = exc.response.status_code
        diagnostic["reason"] = "provider returned a non-success status"
    elif isinstance(exc, httpx.TransportError):
        diagnostic["reason"] = "provider transport failed"
    else:
        diagnostic["reason"] = "provider returned an invalid response"
    return diagnostic


async def calculate_clip_ceiling(
    ideas: list[str],
    connector: AssetConnector,
    minimum_clips: int = 3,
    visual_validator: Any | None = None,
    *,
    phase: str = "final",
    maximum_new_ideas: int | None = None,
) -> dict[str, Any]:
    requested_ideas = list(dict.fromkeys(idea.strip() for idea in ideas if idea.strip()))
    bounded_ideas = requested_ideas[:MAX_ASSET_IDEAS]
    if isinstance(connector, AssetRunSession):
        raw_results = await connector.search(
            bounded_ideas,
            phase=phase,
            maximum_new_ideas=maximum_new_ideas,
        )
    else:
        raw_results = await connector.search(bounded_ideas)
    results_by_idea = {result.idea: result for result in raw_results}
    results = [
        results_by_idea.get(idea) or AssetResult(
            idea, 0, 0, [], False, False,
            provider_errors=[{"provider": "asset_connector", "status": "unavailable", "reason": "no typed result returned"}],
        )
        for idea in bounded_ideas
    ]
    if visual_validator is not None:
        checked: list[AssetResult] = []
        for result in results:
            previews = [str(asset["preview_ref"]) for asset in result.assets if asset.get("preview_ref")][:4]
            if previews:
                if not getattr(visual_validator, "supports_image_inputs", False) or not getattr(
                    visual_validator, "supports_semantic_image_validation", False
                ):
                    reason = (
                        "configured validator cannot establish semantic image fit or reveal capability"
                        if getattr(visual_validator, "supports_image_inputs", False)
                        else "configured validator is not image-capable"
                    )
                    checked.append(AssetResult(**{
                        **result.__dict__, "semantic_fit": False, "semantic_fit_confidence": 0.0,
                        "semantic_fit_reason": reason,
                        "visual_payoff_feasible": False, "reveal_clip_count": 0,
                        "reveal_validation_confidence": 0.0,
                        "reveal_validation_reason": reason,
                    }))
                    continue
                try:
                    analysis = await visual_validator.analyze_visuals(f"Judge whether these candidate assets visibly match this idea and can support a reveal: {result.idea}", previews, [])
                except Exception as exc:
                    checked.append(AssetResult(**{
                        **result.__dict__, "semantic_fit": False, "semantic_fit_confidence": 0.0,
                        "semantic_fit_reason": f"image validation failed: {type(exc).__name__}",
                        "visual_payoff_feasible": False, "reveal_clip_count": 0,
                        "reveal_validation_confidence": 0.0,
                        "reveal_validation_reason": f"image validation failed: {type(exc).__name__}",
                    }))
                    continue
                features = " ".join([analysis.hook_visual, analysis.composition_pattern, *analysis.observable_features]).lower()
                fit = analysis.confidence >= .45 and not any(token in features for token in ("unrelated", "does not match", "mismatch"))
                reveal, reveal_reason = _observed_reveal(analysis)
                checked.append(AssetResult(**{
                    **result.__dict__, "semantic_fit": fit, "semantic_fit_confidence": analysis.confidence,
                    "semantic_fit_reason": (
                        f"image evidence inspected by {getattr(visual_validator, 'name', 'configured image-capable validator')}; "
                        f"uncertainty: {analysis.uncertainty}"
                    ),
                    "visual_payoff_feasible": reveal, "reveal_clip_count": 1 if reveal else 0,
                    "reveal_validation_confidence": analysis.confidence,
                    "reveal_validation_reason": reveal_reason,
                }))
            else:
                checked.append(result)
        results = checked
    validated = [
        result.idea
        for result in results
        if result.video_count >= minimum_clips
        and result.reveal_clip_count >= 1
        and result.semantic_fit is True
        and len(set(result.sources)) >= 2
    ]
    total = max(len(results), 1)
    sources = {source for result in results for source in result.sources}
    provider_diagnostics = [
        {"idea": result.idea, **diagnostic}
        for result in results
        for diagnostic in result.provider_errors
    ]
    deferred_ideas = sum(
        any(
            "budget unavailable during" in str(diagnostic.get("reason", ""))
            for diagnostic in result.provider_errors
        )
        for result in results
    )
    evaluated_ideas = len(results) - deferred_ideas
    return {
        "asset_coverage": round(len(validated) / total, 3),
        "evaluated_asset_coverage": round(
            len(validated) / max(evaluated_ideas, 1), 3
        ),
        "validated_count": len(validated),
        "validated_ideas": validated,
        "minimum_clips_per_idea": minimum_clips,
        "source_diversity": len(sources),
        "source_diversity_coverage": round(sum(len(set(result.sources)) >= 2 for result in results) / total, 3),
        "video_coverage": round(sum(result.video_count >= minimum_clips for result in results) / total, 3),
        "reveal_coverage": round(sum(result.reveal_clip_count >= 1 for result in results) / total, 3),
        "portrait_coverage": round(sum(result.portrait_clip_count >= 1 for result in results) / total, 3),
        "rights_metadata_share": round(sum(result.rights_metadata_present for result in results) / total, 3),
        "semantic_fit_share": round(sum(result.semantic_fit is True for result in results) / total, 3),
        "unsupported_idea_share": round(1 - len(validated) / total, 3),
        "provider_diagnostics": provider_diagnostics,
        "search_bounds": {
            "requested_ideas": len(requested_ideas),
            "searched_ideas": len(results),
            "evaluated_ideas": evaluated_ideas,
            "deferred_ideas": deferred_ideas,
            "maximum_ideas": getattr(connector, "maximum_ideas", MAX_ASSET_IDEAS),
            "truncated": len(requested_ideas) > len(bounded_ideas),
            "maximum_concurrency": getattr(connector, "max_concurrency", 1),
            "phase": phase,
            "maximum_new_ideas": maximum_new_ideas,
            "run_budget": connector.budget_status() if hasattr(connector, "budget_status") else None,
        },
        "results": [
            {
                **result.__dict__,
                "source_diversity_count": len(set(result.sources)),
                "source_diversity_passed": len(set(result.sources)) >= 2,
            }
            for result in results
        ],
        "calculation_version": "clip-ceiling-v6-phase-budget-and-semantic-capability",
        "rights_note": "Clip availability is measured separately from licensing. Source metadata is preserved, but licensing does not gate niche discovery in this self-hosted research tool.",
    }


def _unavailable_asset_result(idea: str, reason: str) -> AssetResult:
    return AssetResult(
        idea, 0, 0, [], False, False,
        provider_errors=[{"provider": "asset_connector", "status": "unavailable", "reason": reason}],
    )


def _observed_reveal(analysis: Any) -> tuple[bool, str]:
    text = " ".join([
        str(getattr(analysis, "reveal_pattern", "")),
        str(getattr(analysis, "hook_visual", "")),
        str(getattr(analysis, "composition_pattern", "")),
        *[str(item) for item in getattr(analysis, "observable_features", [])],
    ]).lower()
    negative = ("no reveal", "without a reveal", "reveal not visible", "no final result", "cannot verify")
    positive = ("reveal", "final result", "final state", "before and after", "transformation", "visible payoff", "outcome shown")
    if getattr(analysis, "confidence", 0.0) < .45:
        return False, "visual confidence was below the reveal threshold"
    if any(marker in text for marker in negative):
        return False, "visual analysis explicitly found no verifiable reveal"
    if any(marker in text for marker in positive):
        return True, "image-capable validation observed a visible reveal or final payoff"
    return False, "no reveal or final payoff was observed in the inspected pixels"
