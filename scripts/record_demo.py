"""Walk through the app with Playwright and save the frames used for docs/demo.gif.

    uv run python scripts/record_demo.py --base http://localhost:3000 --out /tmp/frames
    uv run python scripts/make_gif.py /tmp/frames docs/demo.gif

Needs `uvx playwright install chromium` once, the API and the web app running,
and a freshly seeded database so the scan finds the planted anomalies.
"""

import argparse
import asyncio
from pathlib import Path

from playwright.async_api import Page, async_playwright


async def shot(page: Page, out: Path, name: str, hold: int = 1) -> None:
    await page.wait_for_timeout(400)
    for i in range(hold):
        await page.screenshot(path=out / f"{len(list(out.glob('*.png'))):02d}-{name}-{i}.png")


async def main(base: str, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(
            viewport={"width": 1280, "height": 800}, device_scale_factor=1
        )

        await page.goto(f"{base}/")
        await page.wait_for_selector("text=Pipeline health")
        await page.wait_for_selector("text=Rows loaded")
        await shot(page, out, "dashboard", 2)

        await page.goto(f"{base}/signin?callbackUrl=/")
        await shot(page, out, "signin")
        await page.click("text=Continue as the demo reviewer")
        await page.wait_for_selector("text=Pipeline health")
        await page.get_by_role("button", name="Run a scan").click()
        await shot(page, out, "scanning")
        await page.get_by_role("button", name="Run a scan").wait_for(timeout=120_000)
        await page.wait_for_selector("text=/^\\d+ waiting for review$/", timeout=30_000)
        await shot(page, out, "dashboard-after", 3)

        await page.goto(f"{base}/incidents")
        await page.wait_for_selector("summary")
        await page.locator("summary").nth(1).click()
        await shot(page, out, "incident", 2)
        await page.mouse.wheel(0, 520)
        await shot(page, out, "incident-detail", 2)

        await page.goto(f"{base}/review")
        await page.wait_for_selector("text=Findings to sign off")
        await shot(page, out, "review", 2)
        await page.fill("textarea", "Resend requested from S1003")
        await page.click("text=Approve with note")
        await page.wait_for_selector("text=Nothing waiting")
        await shot(page, out, "reviewed")

        await page.goto(f"{base}/ask")
        await page.fill("textarea", "Did the MOBILE file have a schema problem on 2026-06-16?")
        await page.keyboard.press("Enter")
        await page.wait_for_timeout(800)
        await shot(page, out, "ask-streaming")
        await page.wait_for_selector("text=trace", timeout=60_000)
        await shot(page, out, "ask-done", 3)

        await page.goto(f"{base}/docs?q=basket_ref+ContractViolation")
        await page.wait_for_selector("text=bm25")
        await shot(page, out, "docs", 2)

        await page.goto(f"{base}/traces")
        await page.wait_for_selector("table")
        await page.locator("tbody a").first.click()
        await page.wait_for_selector("text=LLM calls")
        await shot(page, out, "trace", 2)
        await browser.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:3000")
    ap.add_argument("--out", type=Path, default=Path("frames"))
    args = ap.parse_args()
    asyncio.run(main(args.base, args.out))
