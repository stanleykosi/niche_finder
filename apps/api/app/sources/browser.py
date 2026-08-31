"""Playwright browser adapter with bounded navigation and allowed-host protection."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse
import re
import hashlib

from ..core.config import AppMode, Settings
from ..core.errors import ClosedModeViolation, ErrorCode, NicheIntelError
from ..domain.enums import SourceType
from ..domain.youtube_urls import channel_videos_url, classify_direct_youtube_url
from .base import BrowserMediaRecord, DiscoveryRequest, DiscoveryResult


VIDEO_CARD_SELECTOR = ", ".join((
    "ytd-video-renderer a#video-title",
    "ytd-rich-item-renderer a#video-title-link",
    "ytd-grid-video-renderer a#video-title",
    "ytd-reel-item-renderer a[href^='/shorts/']",
    "a#video-title-link[href^='/watch']",
    "a[href^='/shorts/']",
))
VIDEO_CARD_CONTAINER_XPATH = (
    "xpath=ancestor::ytd-video-renderer | ancestor::ytd-reel-item-renderer | "
    "ancestor::ytd-rich-item-renderer | ancestor::ytd-grid-video-renderer"
)
YOUTUBE_CONSENT_SELECTOR = "ytd-consent-bump-v2-lightbox"
CONSENT_DISCOVERY_TIMEOUT_MS = 750
SEARCH_RESULT_HYDRATION_TIMEOUT_MS = 5_000
VIDEO_PAGE_HYDRATION_SELECTOR = ", ".join((
    "video",
    "ytd-watch-flexy",
    "ytd-reel-video-renderer",
    "#shorts-container",
))
VIDEO_PAGE_HYDRATION_TIMEOUT_MS = 8_000
VIDEO_PAGE_OPERATION_TIMEOUT_MS = 5_000
VIDEO_PAGE_NAVIGATION_TIMEOUT_MS = 15_000
BROWSER_SHUTDOWN_TIMEOUT_SECONDS = 5


async def _reject_optional_youtube_consent(page: Any) -> None:
    """Prefer YouTube's non-personalized consent path when the prompt appears."""
    from playwright.async_api import Error as PlaywrightError  # type: ignore

    consent = page.locator(YOUTUBE_CONSENT_SELECTOR).first
    try:
        await consent.wait_for(state="attached", timeout=CONSENT_DISCOVERY_TIMEOUT_MS)
        reject = consent.get_by_role("button", name=re.compile(r"^Reject all$", re.I)).first
        if await reject.count():
            await reject.click(timeout=2_000)
            await consent.wait_for(state="hidden", timeout=2_000)
    except PlaywrightError:
        # Consent is regional and optional. Its absence or a disappearing
        # control must not prevent later bounded extraction.
        pass


async def _prepare_search_results(page: Any) -> bool:
    """Reject optional consent and wait for YouTube's asynchronous card hydration."""
    from playwright.async_api import TimeoutError as PlaywrightTimeoutError  # type: ignore

    await _reject_optional_youtube_consent(page)

    try:
        await page.locator(VIDEO_CARD_SELECTOR).first.wait_for(
            state="attached", timeout=SEARCH_RESULT_HYDRATION_TIMEOUT_MS
        )
    except PlaywrightTimeoutError:
        return False
    return True


async def _prepare_video_page(page: Any) -> bool:
    """Use response-commit navigation, then bound YouTube's watch-page hydration."""
    from playwright.async_api import TimeoutError as PlaywrightTimeoutError  # type: ignore

    await _reject_optional_youtube_consent(page)
    try:
        await page.locator(VIDEO_PAGE_HYDRATION_SELECTOR).first.wait_for(
            state="attached", timeout=VIDEO_PAGE_HYDRATION_TIMEOUT_MS
        )
    except PlaywrightTimeoutError:
        return False
    return True


class PlaywrightBrowserSource:
    def __init__(self, settings: Settings, allowed_hosts: set[str] | None = None) -> None:
        if settings.app_mode == AppMode.CLOSED_TEST:
            raise ClosedModeViolation("live Chromium is unavailable in closed_test mode")
        self.settings = settings
        self.allowed_hosts = allowed_hosts or {"www.youtube.com", "youtube.com", "m.youtube.com", "youtu.be"}
        self.profile_root = Path(settings.browser_profile_root)

    def validate_url(self, url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme not in {"https"} or parsed.hostname not in self.allowed_hosts:
            raise NicheIntelError("browser navigation target is not an allowed YouTube host")

    async def discover(self, request: DiscoveryRequest) -> DiscoveryResult:
        """Use Playwright when installed; return an explicit typed partial result otherwise."""
        if not self.settings.browser_enabled:
            raise NicheIntelError("browser is disabled by BROWSER_ENABLED", ErrorCode.SOURCE_UNAVAILABLE)
        try:
            from playwright.async_api import Error as PlaywrightError  # type: ignore
        except ImportError as exc:
            raise NicheIntelError("Playwright is not installed; install the browser extra", ErrorCode.CONFIGURATION) from exc
        try:
            return await self._discover_once(request)
        except PlaywrightError as exc:
            raise NicheIntelError(f"browser discovery unavailable: {type(exc).__name__}", ErrorCode.SOURCE_UNAVAILABLE) from exc

    async def _discover_once(self, request: DiscoveryRequest) -> DiscoveryResult:
        from playwright.async_api import async_playwright  # type: ignore
        url, direct_kind = _discovery_target(
            request.query,
            request.requested_format,
            language=request.language,
            region=request.region,
            recency_days=request.recency_days,
        )
        self.validate_url(url)
        async with async_playwright() as playwright:
            context = await playwright.chromium.launch_persistent_context(
                str(self.profile_root / request.profile_id),
                headless=self.settings.browser_headless,
                executable_path=self.settings.browser_executable_path,
                locale=_browser_locale(request.language, request.region),
            )
            page = await context.new_page()
            await page.goto(url, wait_until="domcontentloaded")
            results = []
            if direct_kind == "video":
                await _reject_optional_youtube_consent(page)
                from .base import SearchResult
                video_id = _direct_video_id(url)
                title_meta = page.locator("meta[name='title'], meta[property='og:title']").first
                title = await title_meta.get_attribute("content") if await title_meta.count() else await page.title()
                channel_link = page.locator("ytd-video-owner-renderer a[href*='/@'], ytd-video-owner-renderer a[href*='/channel/']").first
                channel_href = await channel_link.get_attribute("href") if await channel_link.count() else ""
                channel_title = (await channel_link.inner_text()).strip() if await channel_link.count() else ""
                results.append(SearchResult(
                    video_id, url, title or video_id, (channel_href or "").rstrip("/").split("/")[-1], channel_title,
                    "", "", "/shorts/" in urlparse(url).path, 1,
                    raw_payload={"direct_input": True, "youtube_presented_as_short": "/shorts/" in urlparse(url).path},
                ))
            else:
                await _prepare_search_results(page)
            for _ in range(min(3, self.settings.browser_max_results_per_query // 10 + 1)):
                await page.mouse.wheel(0, 800)
                await page.wait_for_timeout(250)
            cards = await page.locator(VIDEO_CARD_SELECTOR).all()
            seen: set[str] = {item.canonical_url for item in results}
            for position, card in enumerate(cards, start=1):
                href = await card.get_attribute("href")
                title = (await card.get_attribute("title")) or (await card.inner_text())
                canonical_url = _absolute_youtube_url(href or "")
                if not href or canonical_url in seen:
                    continue
                seen.add(canonical_url)
                is_short = "/shorts/" in urlparse(canonical_url).path
                video_id = _direct_video_id(canonical_url)
                if not video_id:
                    continue
                from .base import SearchResult
                container = card.locator(VIDEO_CARD_CONTAINER_XPATH).first
                card_text = await container.inner_text() if await container.count() else ""
                channel_link = container.locator("a[href*='/@'], a[href*='/channel/']").first
                channel_href = await channel_link.get_attribute("href") if await channel_link.count() else ""
                channel_title = (await channel_link.inner_text()).strip() if await channel_link.count() else ""
                channel_id = (channel_href or "").rstrip("/").split("/")[-1]
                views = next((line for line in card_text.splitlines() if "view" in line.lower()), "")
                age = next((line for line in card_text.splitlines() if re.search(r"\b(hour|day|week|month|year)s? ago\b", line.lower())), "")
                results.append(SearchResult(video_id, canonical_url, title, channel_id, channel_title, views, age, is_short, position, raw_payload={"youtube_presented_as_short": is_short, "card_text": card_text[:1000], "direct_input": direct_kind is not None}))
                if len(results) >= request.max_results:
                    break
            screenshot = str(self.profile_root / request.profile_id / f"search-{_safe_name(request.query)}.png")
            await page.screenshot(path=screenshot)
            results = _attach_screenshot(results, screenshot)
            await context.close()
        return DiscoveryResult(source=SourceType.BROWSER, query=request.query, results=results, screenshot_refs=[screenshot])

    async def inspect_video(self, video_id: str, canonical_url: str | None = None, profile_id: str = "research", capture_frames: bool = True) -> BrowserMediaRecord:
        if not self.settings.browser_enabled:
            raise NicheIntelError("browser is disabled by BROWSER_ENABLED", ErrorCode.SOURCE_UNAVAILABLE)
        url = canonical_url or f"https://www.youtube.com/watch?v={video_id}"
        self.validate_url(url)
        try:
            from playwright.async_api import Error as PlaywrightError, async_playwright  # type: ignore
        except ImportError as exc:
            raise NicheIntelError("Playwright is not installed; install the browser extra", ErrorCode.CONFIGURATION) from exc
        manager = async_playwright()
        playwright = await manager.start()
        context = None
        try:
            try:
                context = await asyncio.wait_for(
                    playwright.chromium.launch_persistent_context(
                        str(self.profile_root / profile_id),
                        headless=self.settings.browser_headless,
                        executable_path=self.settings.browser_executable_path,
                    ),
                    timeout=VIDEO_PAGE_NAVIGATION_TIMEOUT_MS / 1_000,
                )
            except (PlaywrightError, TimeoutError) as exc:
                raise NicheIntelError(f"Chromium inspection profile could not start: {type(exc).__name__}", ErrorCode.CONFIGURATION) from exc
            try:
                return await self._inspect_video_context(context, video_id, url, profile_id, capture_frames)
            except PlaywrightError as exc:
                detail = " ".join(str(exc).split())[-300:]
                raise NicheIntelError(
                    f"browser video inspection unavailable for {video_id}: {type(exc).__name__}: {detail}",
                    ErrorCode.SOURCE_UNAVAILABLE,
                ) from exc
        finally:
            if context is not None:
                try:
                    await asyncio.wait_for(
                        context.close(), timeout=BROWSER_SHUTDOWN_TIMEOUT_SECONDS
                    )
                except (PlaywrightError, TimeoutError):
                    pass
            try:
                await asyncio.wait_for(
                    playwright.stop(), timeout=BROWSER_SHUTDOWN_TIMEOUT_SECONDS
                )
            except (PlaywrightError, TimeoutError):
                pass

    async def _inspect_video_context(self, context: Any, video_id: str, url: str, profile_id: str, capture_frames: bool = True) -> BrowserMediaRecord:
        from playwright.async_api import Error as PlaywrightError  # type: ignore

        page = await context.new_page()
        page.set_default_timeout(VIDEO_PAGE_OPERATION_TIMEOUT_MS)
        page.set_default_navigation_timeout(VIDEO_PAGE_NAVIGATION_TIMEOUT_MS)
        response = await page.goto(
            url,
            wait_until="commit",
            timeout=VIDEO_PAGE_NAVIGATION_TIMEOUT_MS,
        )
        if response is None or not response.ok:
            status = response.status if response is not None else "no response"
            raise NicheIntelError(
                f"browser video inspection returned {status} for {video_id}",
                ErrorCode.SOURCE_UNAVAILABLE,
            )
        if not await _prepare_video_page(page):
            raise NicheIntelError(
                f"browser video page did not hydrate for {video_id}",
                ErrorCode.SOURCE_UNAVAILABLE,
            )
        await page.wait_for_timeout(1200)
        # YouTube hides transcripts behind the description/action menu.
        for selector in ("button[aria-label*='description']", "tp-yt-paper-button#expand", "button:has-text('more')"):
            locator = page.locator(selector).first
            if await locator.count():
                try:
                    await locator.click(timeout=1200)
                except Exception:
                    pass
        transcript_button = page.get_by_text(re.compile("show transcript", re.I)).first
        if await transcript_button.count():
            try:
                await transcript_button.click(timeout=2000)
                await page.wait_for_timeout(600)
            except Exception:
                pass
        transcript_locator = page.locator("#transcript, ytd-transcript-segment-renderer, [aria-label*='transcript']")
        try:
            transcript = await transcript_locator.first.inner_text() if await transcript_locator.count() else None
        except PlaywrightError:
            transcript = None
        presentation = await page.locator("ytd-reel-video-renderer, #shorts-container").count()
        video_locator = page.locator("video").first
        try:
            video_data = await video_locator.evaluate("el => ({duration: Number.isFinite(el.duration) ? el.duration : null, width: el.videoWidth, height: el.videoHeight})") if await video_locator.count() else {}
        except PlaywrightError:
            video_data = {}
        has_captions = bool(await page.locator(".ytp-caption-segment").count())
        structure = [text for text in ["visible opening", "captioned" if has_captions else None, "shorts presentation" if presentation else None] if text]
        frames: list[str] = []
        duration = video_data.get("duration") or 0
        for index, fraction in enumerate((.02, .18, .45, .72, .92) if capture_frames else ()):
            if duration and await video_locator.count():
                try:
                    await video_locator.evaluate("(el, time) => { el.pause(); el.currentTime = time; }", duration * fraction)
                    await page.wait_for_timeout(250)
                except Exception:
                    pass
            screenshot = str(self.profile_root / profile_id / f"video-{video_id}-{index}.png")
            try:
                await page.screenshot(
                    path=screenshot,
                    animations="disabled",
                    timeout=VIDEO_PAGE_OPERATION_TIMEOUT_MS,
                )
                frames.append(screenshot)
            except PlaywrightError:
                continue
        return BrowserMediaRecord(
            source_profile=profile_id, is_short_presentation=bool(presentation), visible_transcript=transcript,
            thumbnail_ref=None, frame_refs=frames, opening_visual_summary="Opening frame captured for multimodal interpretation" if frames else None, caption_style="YouTube captions visible" if has_captions else None,
            observable_structure=structure or ["visible page inspection"], observed_at=datetime.now(timezone.utc), confidence=.7,
            first_spoken_line=(transcript or "").splitlines()[0] if transcript else None,
            duration_seconds=video_data.get("duration"), scene_change_count=None, average_shot_duration_seconds=None,
            reveal_timestamp_seconds=None, caption_density=1.0 if has_captions else 0.0, motion_score=None, pacing_score=None,
            music_cue_count=None, editing_pattern="selective frame samples captured; multimodal model must infer only observable cuts" if capture_frames else "lightweight page inspection; filmstrip skipped by run media bound",
            visual_features={"width": video_data.get("width"), "height": video_data.get("height"), "portrait": (video_data.get("height") or 0) > (video_data.get("width") or 0), "frame_sample_times": [.02, .18, .45, .72, .92] if capture_frames else [], "analysis_method": "chromium_selective_filmstrip" if capture_frames else "chromium_lightweight_page"},
        )


def _discovery_target(
    query: str,
    requested_format: str,
    *,
    language: str = "en",
    region: str = "US",
    recency_days: int | None = None,
    observed_at: datetime | None = None,
) -> tuple[str, str | None]:
    candidate = query.strip()
    direct_kind = classify_direct_youtube_url(candidate)
    if direct_kind == "video":
        return candidate, "video"
    if direct_kind == "channel":
        return channel_videos_url(candidate), "channel"
    search_query = candidate if requested_format != "shorts" or "short" in candidate.lower() else f"{candidate} shorts"
    if recency_days is not None:
        anchor = observed_at or datetime.now(timezone.utc)
        published_after = (anchor - timedelta(days=max(1, int(recency_days)))).date().isoformat()
        search_query = f"{search_query} after:{published_after}".strip()
    parameters = {
        "search_query": search_query,
        "hl": (language or "en").split("-", 1)[0].lower(),
        "gl": (region or "US").upper(),
    }
    return f"https://www.youtube.com/results?{urlencode(parameters)}", None


def _browser_locale(language: str, region: str) -> str:
    normalized_language = (language or "en").split("-", 1)[0].lower()
    normalized_region = (region or "US").upper()
    return f"{normalized_language}-{normalized_region}"


def _attach_screenshot(results: list[Any], screenshot_ref: str) -> list[Any]:
    """Bind the captured search surface to every observation from that surface."""
    return [replace(item, screenshot_ref=screenshot_ref) for item in results]


def _direct_video_id(url: str) -> str:
    parsed = urlparse(url)
    if parsed.hostname == "youtu.be":
        return parsed.path.strip("/").split("/", 1)[0]
    if parsed.path.startswith("/shorts/"):
        return parsed.path.split("/shorts/", 1)[1].split("/", 1)[0]
    return parse_qs(parsed.query).get("v", [""])[0]


def _absolute_youtube_url(href: str) -> str:
    if href.startswith("https://"):
        return href
    return f"https://www.youtube.com{href}"


def _safe_name(value: str) -> str:
    readable = re.sub(r"[^A-Za-z0-9_-]+", "-", value).strip("-")[:32] or "query"
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:10]
    return f"{readable}-{digest}"
