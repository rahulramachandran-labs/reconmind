"""Walk through the app with Playwright and save the frames used for docs/demo.gif,
or, with --screenshots, one still of each screen for the README, or, with
--video, the narrated walkthrough in docs/DEMO.md as an MP4 with captions.

    uv run --with playwright python scripts/record_demo.py --out /tmp/frames
    uv run python scripts/make_gif.py /tmp/frames docs/demo.gif
    uv run --with playwright python scripts/record_demo.py --screenshots docs/screenshots
    uv run --with playwright python scripts/record_demo.py --video docs/demo.mp4

Needs `uvx playwright install chromium` once, the API and the web app running,
and a freshly seeded database so the scan finds the planted anomalies. The
screenshots expect a scan to have run already (scripts/capture_readme_evidence.py
runs one).
"""

import argparse
import asyncio
import json
import urllib.request
from pathlib import Path

from playwright.async_api import Page, async_playwright

MOBILE_QUESTION = "Did the MOBILE file have a schema problem on 2026-06-16?"
RUNBOOK_QUESTION = "Which file wins when a submitter resends the same day?"
EXPLORE_QUESTION = (
    "Show me which submitter sent the fewest rows on 2026-06-18, and when its file landed."
)


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


def api_get(api: str, path: str) -> list[dict[str, object]]:
    with urllib.request.urlopen(f"{api}{path}", timeout=60) as res:  # noqa: S310 (local API)
        data: list[dict[str, object]] = json.loads(res.read())
        return data


async def screenshots(base: str, api: str, out: Path) -> None:
    """One 1440x900 still per screen, named for the README's screens table."""
    out.mkdir(parents=True, exist_ok=True)
    incidents = api_get(api, "/incidents")
    key_drift = next(r for r in incidents if r["finding_type"] == "key_drift")
    scan = next(r for r in api_get(api, "/runs") if r["trigger"] == "scan")

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 1440, "height": 900})

        # the Next.js dev-mode badge isn't part of the app
        await page.add_init_script(
            "document.addEventListener('DOMContentLoaded', () => {"
            " const s = document.createElement('style');"
            " s.textContent = 'nextjs-portal { display: none !important; }';"
            " document.head.appendChild(s); });"
        )

        async def still(name: str) -> None:
            await page.mouse.move(1435, 895)  # park the pointer where it triggers no tooltip
            await page.wait_for_timeout(600)
            await page.screenshot(path=out / f"{name}.png")

        await page.goto(f"{base}/signin?callbackUrl=/")
        await page.click("text=Continue as the demo reviewer")
        await page.wait_for_selector("text=Rows loaded", timeout=120_000)
        await still("dashboard")

        await page.goto(f"{base}/incidents")
        await page.wait_for_selector("summary")
        await still("incidents")

        await page.goto(f"{base}/incidents/{key_drift['id']}")
        await page.wait_for_selector("text=Recommended fix", timeout=60_000)
        await still("incident-detail")
        await page.click("text=Deterministic checks")
        await still("incident-template")

        await page.goto(f"{base}/review")
        await page.wait_for_selector("text=Findings to sign off")
        await still("review")

        await page.goto(f"{base}/ask")
        await page.fill("textarea", MOBILE_QUESTION)
        await page.keyboard.press("Enter")
        await page.wait_for_selector("text=/^\\d+ LLM calls$/", timeout=600_000)
        await still("ask")
        await page.click("text=New conversation")
        await page.fill("textarea", RUNBOOK_QUESTION)
        await page.keyboard.press("Enter")
        await page.wait_for_selector("text=/^answered by/", timeout=600_000)
        await still("ask-runbook")
        await page.click("text=New conversation")
        await page.fill("textarea", EXPLORE_QUESTION)
        await page.keyboard.press("Enter")
        await page.wait_for_selector("text=/^answered by/", timeout=600_000)
        await still("ask-explore")

        await page.goto(f"{base}/traces/{scan['id']}")
        await page.wait_for_selector("text=LLM calls")
        await still("trace")

        query = "q=basket_ref+ContractViolation"
        await page.goto(f"{base}/docs?{query}")
        await page.wait_for_selector("text=/^#1$/")
        await still("docs-hybrid")
        await page.goto(f"{base}/docs?{query}&mode=dense")
        await page.wait_for_selector("text=/^#1$/")
        await still("docs-dense")

        await page.goto(f"{base}/verify")
        await page.wait_for_selector("text=Verify it yourself")
        await page.wait_for_timeout(3000)
        await page.evaluate("window.scrollTo(0, 0)")
        await still("verify")
        await browser.close()


CAPTION_JS = """(text) => {
  let el = document.getElementById("demo-caption");
  if (!el) {
    el = document.createElement("div");
    el.id = "demo-caption";
    Object.assign(el.style, {
      position: "fixed", left: "50%", bottom: "28px", transform: "translateX(-50%)",
      maxWidth: "1080px", padding: "12px 20px", borderRadius: "10px", zIndex: 99999,
      background: "rgba(10, 12, 16, 0.92)", color: "#f4f4f5", font: "500 19px/1.4 system-ui",
      boxShadow: "0 6px 24px rgba(0,0,0,.45)", border: "1px solid rgba(255,255,255,.12)",
      textAlign: "center", pointerEvents: "none",
    });
    document.body.appendChild(el);
  }
  el.textContent = text;
}"""


async def video(base: str, api: str, out: Path) -> None:
    """The walkthrough in docs/DEMO.md, recorded at 1280x720 with a caption per step.

    Expects a freshly seeded database: the scan happens on camera."""
    import shutil
    import subprocess
    import tempfile

    raw = Path(tempfile.mkdtemp(prefix="reconmind-video-"))
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        ctx = await browser.new_context(
            viewport={"width": 1280, "height": 720},
            record_video_dir=str(raw),
            record_video_size={"width": 1280, "height": 720},
        )
        page = await ctx.new_page()
        await page.add_init_script(
            "document.addEventListener('DOMContentLoaded', () => {"
            " const s = document.createElement('style');"
            " s.textContent = 'nextjs-portal { display: none !important; }';"
            " document.head.appendChild(s); });"
        )

        async def say(text: str, hold: float = 5) -> None:
            await page.evaluate(CAPTION_JS, text)
            await page.wait_for_timeout(int(hold * 1000))

        await page.goto(f"{base}/")
        await page.wait_for_selector("text=Rows loaded", timeout=120_000)
        await say(
            "ReconMind watches a synthetic retail pipeline: four submitters, 21 days, "
            "four problems planted in the data.",
            6,
        )
        await say("The chart flags the light day: POSFEED on 2026-06-18, 40% under its average.")

        await page.goto(f"{base}/signin?callbackUrl=/")
        await page.click("text=Continue as the demo reviewer")
        await page.wait_for_selector("text=Rows loaded", timeout=120_000)
        await page.get_by_role("button", name="Run a scan").click()
        await say(
            "Run a scan: the Planner sends the Reconciliation and Data-Quality agents "
            "in parallel, reading the pipeline through read-only MCP tools.",
            3,
        )
        await page.get_by_role("button", name="Run a scan").wait_for(timeout=300_000)
        await page.wait_for_selector("text=/^\\d+ waiting for review$/", timeout=60_000)
        await say(
            "Four findings, one S1. The checks measured the facts; Groq's free tier "
            "wrote the explanations.",
            6,
        )

        incidents = api_get(api, "/incidents")
        key_drift = next(r for r in incidents if r["finding_type"] == "key_drift")
        await page.goto(f"{base}/incidents/{key_drift['id']}")
        await page.wait_for_selector("text=Recommended fix", timeout=60_000)
        await say(
            "Each finding is a change-request style report: problem, records, root cause, "
            "fix steps, confidence, open questions.",
            6,
        )
        await page.mouse.wheel(0, 420)
        await say("The chip names the model, its latency, tokens and cost.", 4)
        await page.mouse.wheel(0, -420)
        await page.click("text=Side by side")
        await say(
            "Side by side: the deterministic template and the model's write-up. "
            "The counts are the checks' in both.",
            7,
        )

        await page.goto(f"{base}/review")
        await page.wait_for_selector("text=Findings to sign off")
        await say("S1 findings always stop here for a person to sign off.", 4)
        await page.fill("textarea", "Resend requested from S1003")
        await page.click("text=Approve with note")
        await page.wait_for_selector("text=/Nothing waiting|nothing waiting/", timeout=120_000)
        await say(
            "The decision resumes the paused LangGraph run and lands in an append-only ledger.", 5
        )

        await page.goto(f"{base}/ask")
        await page.fill("textarea", MOBILE_QUESTION)
        await page.keyboard.press("Enter")
        await say("A question about the data: the Planner routes it to Data-Quality only.", 3)
        await page.wait_for_selector("text=/^\\d+ LLM calls$/", timeout=300_000)
        await say("The answer streams in, step by step, with a link to its trace.", 5)
        await page.click("text=New conversation")
        await page.fill("textarea", RUNBOOK_QUESTION)
        await page.keyboard.press("Enter")
        await page.wait_for_selector("text=/^answered by/", timeout=300_000)
        await say(
            "A runbook question is answered from the documents, with citations, "
            "and names the model that answered.",
            6,
        )
        await page.click("text=New conversation")
        await page.fill("textarea", EXPLORE_QUESTION)
        await page.keyboard.press("Enter")
        await say(
            "A fact no check covers goes to the Explorer: the model picks read-only tools "
            "itself, up to three.",
            3,
        )
        await page.wait_for_selector("text=/^answered by/", timeout=300_000)
        await say("It answers from what the tools returned; the trace shows each call.", 6)

        scan = next(r for r in api_get(api, "/runs") if r["trigger"] == "scan")
        await page.goto(f"{base}/traces/{scan['id']}")
        await page.wait_for_selector("text=LLM calls")
        await say(
            "Every agent step, MCP tool call, retrieval and model call is traced, "
            "with latency and cost.",
            6,
        )

        query = "q=basket_ref+ContractViolation"
        await page.goto(f"{base}/docs?{query}")
        await page.wait_for_selector("text=/^#1$/")
        await say(
            "Hybrid search finds the schema-drift runbook and the past incident "
            "for an exact identifier...",
            5,
        )
        await page.goto(f"{base}/docs?{query}&mode=dense")
        await page.wait_for_selector("text=/^#1$/")
        await say("...where embeddings alone miss the incident.", 5)

        await page.goto(f"{base}/verify")
        await page.wait_for_selector("text=Verify it yourself")
        await page.wait_for_timeout(2000)
        await page.evaluate("window.scrollTo(0, 0)")
        await say(
            "Verify: what was planted, what was found, the test that proves it, "
            "and both write-ups.",
            6,
        )
        await page.mouse.wheel(0, 700)
        await say("Synthetic data, real agents. github.com/rahulramachandran-labs/reconmind", 6)
        await ctx.close()
        await browser.close()

    webm = next(raw.glob("*.webm"))
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(webm),
            "-vf",
            "scale=1280:720,format=yuv420p",
            "-c:v",
            "libx264",
            "-preset",
            "slow",
            "-crf",
            "28",
            "-movflags",
            "+faststart",
            "-an",
            str(out),
        ],
        check=True,
    )
    shutil.rmtree(raw, ignore_errors=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:3000")
    ap.add_argument("--api", default="http://localhost:8000")
    ap.add_argument("--out", type=Path, default=Path("frames"))
    ap.add_argument("--screenshots", type=Path, help="save one still per screen here instead")
    ap.add_argument("--video", type=Path, help="record the captioned walkthrough to this MP4")
    args = ap.parse_args()
    if args.video:
        asyncio.run(video(args.base, args.api, args.video))
    elif args.screenshots:
        asyncio.run(screenshots(args.base, args.api, args.screenshots))
    else:
        asyncio.run(main(args.base, args.out))
