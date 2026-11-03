"""Local synthetic-only smoke flow: PYTHONPATH=src:tests python tests/browser_smoke.py."""
import asyncio
import os
import socket
import tempfile
import threading
from pathlib import Path

import httpx
import uvicorn
from playwright.async_api import async_playwright, expect

from rift_atlas.api import create_app
from rift_atlas.dataset import load_dataset
from test_api import write_fixture


async def smoke(base):
    async with async_playwright() as playwright:
        options = {"headless": True}
        if os.environ.get("DPS_BROWSER_EXECUTABLE"):
            options["executable_path"] = os.environ["DPS_BROWSER_EXECUTABLE"]
        browser = await playwright.chromium.launch(**options)
        page = await browser.new_page(viewport={"width": 1440, "height": 1000})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        await page.goto(base)
        await expect(page.locator("#dataset-provenance")).to_contain_text("synthetic-test-only")
        await expect(page.locator("#dataset-provenance")).to_contain_text("Synthetic test-only data")
        await page.locator("#champion-search").fill("A")
        await page.get_by_role("button", name="Explore", exact=True).click()
        await expect(page.locator("#graph")).to_have_attribute("aria-busy", "false")
        await page.get_by_role("button", name="Pin A", exact=True).click()
        await expect(page.locator("#graph")).to_have_attribute("aria-busy", "false")
        await expect(page.locator("#pinned-champions").get_by_role("button", name="Unpin A", exact=True)).to_be_visible()
        await page.get_by_role("button", name="Pin B", exact=True).click()
        await expect(page.locator("#graph")).to_have_attribute("aria-busy", "false")
        await expect(page.locator("#pinned-champions").get_by_role("button", name="Unpin B", exact=True)).to_be_visible()
        await page.locator('.edge-group').first.press("Enter")
        await expect(page.locator("#evidence-panel")).to_contain_text("Co-pick support")
        await page.locator('.node-action[aria-label^="C,"]').press("Enter")
        await expect(page.locator("#evidence-panel")).to_contain_text("Exact joint support")
        before_viewport = await page.locator("#graph-viewport").get_attribute("transform")
        await page.get_by_role("button", name="Follow node", exact=True).click()
        await expect(page.locator("#graph")).to_have_attribute("aria-busy", "false")
        await expect(page.locator("#champion-search")).to_have_value("C")
        assert await page.locator("#graph-viewport").get_attribute("transform") == before_viewport
        await expect(page.locator("#pinned-champions")).to_contain_text("A")
        await expect(page.locator("#pinned-champions")).to_contain_text("B")
        direct = await page.request.get(base + "/api/v1/relationships?champion=C&pinned=A&pinned=B")
        result = await direct.json()
        assert result["pinned_champions"] == ["A", "B"]
        assert result["dataset_id"] == "synthetic-test-only"
        await page.locator("#filter-toggle").click()
        await page.locator("#clear-all-leagues").click()
        await expect(page.locator("#empty-state")).to_contain_text("No leagues selected")
        await page.locator("#select-all-leagues").click()
        await expect(page.locator("#graph")).to_be_visible()
        await page.locator("#patch-from").select_option("1.2")
        await expect(page.locator("#filter-summary")).to_contain_text("2 team observations")

        # Delay a superseded response; the newest mode must remain rendered.
        async def delay_old(route):
            response = await route.fetch()
            await asyncio.sleep(0.25)
            try:
                await route.fulfill(response=response)
            except Exception:
                pass  # The frontend aborts superseded requests.
        await page.route("**/api/v1/relationships?*mode=frequent*", delay_old)
        await page.locator('[data-mode="frequent"]').click()
        await page.locator('[data-mode="surprising"]').click()
        await expect(page.locator("#graph")).to_have_attribute("aria-busy", "false")
        await page.wait_for_timeout(350)
        await expect(page.locator('[data-mode="surprising"]')).to_have_attribute("aria-pressed", "true")
        await page.route("**/api/v1/relationships?*", lambda route: route.fulfill(status=500, json={"error": "Internal server error"}))
        await page.locator('[data-mode="established"]').click()
        await expect(page.locator("#search-status")).to_contain_text("Could not load relationships")
        assert not errors, errors
        await browser.close()


def main():
    with tempfile.TemporaryDirectory() as directory:
        settings = write_fixture(Path(directory))
        app = create_app(settings, loader=lambda settings: load_dataset(settings, allow_test_data=True))
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            base = f"http://127.0.0.1:{sock.getsockname()[1]}"
            server = uvicorn.Server(uvicorn.Config(app, log_level="error"))
            worker = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
            worker.start()
            try:
                import time
                for _ in range(100):
                    try:
                        if httpx.get(base + "/healthz").status_code == 200:
                            break
                    except httpx.ConnectError:
                        pass
                    time.sleep(0.05)
                else:
                    raise RuntimeError("Test server did not become ready")
                asyncio.run(smoke(base))
                print("Synthetic-only browser smoke passed")
            finally:
                server.should_exit = True
                worker.join(timeout=5)


if __name__ == "__main__":
    main()
