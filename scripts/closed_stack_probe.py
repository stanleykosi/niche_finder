"""Exercise the container Chromium binary against the isolated fixture site."""

from __future__ import annotations

import asyncio
import os

from playwright.async_api import async_playwright


async def main() -> None:
    executable = os.environ.get("BROWSER_EXECUTABLE_PATH")
    fixture_base_url = os.environ.get("FIXTURE_BASE_URL", "http://fixture-server:8765")
    async with async_playwright() as playwright:
        # The closed probe must connect directly to the isolated fixture even
        # when the developer shell exports a corporate/system HTTP proxy.
        browser = await playwright.chromium.launch(
            headless=True,
            executable_path=executable,
            args=["--no-proxy-server"],
        )
        page = await browser.new_page()
        await page.goto(f"{fixture_base_url}/results?search_query=paper+bridge", wait_until="domcontentloaded")
        cards = page.get_by_test_id("search-result")
        if await cards.count() < 3:
            raise RuntimeError("fixture search did not expose the bounded candidate set")
        await cards.first.locator("a").click()
        await page.wait_for_load_state("domcontentloaded")
        if not await page.get_by_test_id("transcript").count():
            raise RuntimeError("fixture video did not expose its transcript observation")
        if await page.get_by_test_id("related-video").count() < 1:
            raise RuntimeError("fixture video did not expose related-video observations")
        await browser.close()
    print("closed Chromium fixture probe: PASS")


if __name__ == "__main__":
    asyncio.run(main())
