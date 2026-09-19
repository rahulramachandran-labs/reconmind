"""Capture the evidence the README quotes, from a running local stack.

    make dev                                            # in another terminal
    uv run python scripts/capture_readme_evidence.py

Runs one scan and two chat questions against the API, saves what came back to
docs/evidence/, runs the test suite for its counts and coverage, and writes
docs/evidence/README.md saying when, on which commit and with which model it
was captured. Every number in the README's Results section comes from here.

Use a freshly seeded database, so the scan reports the planted anomalies as new
findings instead of repeats of an earlier scan. `--skip-tests` leaves the test
run out, and `--tests-only` adds it to an existing capture later.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parent.parent
MOBILE_QUESTION = "Did the MOBILE file have a schema problem on 2026-06-16?"
RUNBOOK_QUESTION = "Which file wins when a submitter resends the same day?"
TEST_LAYERS = {
    "unit": ["tests/unit"],
    "integration": ["tests/integration"],
    "chaos": ["tests/chaos"],
    "prompt injection": ["tests/integration/test_prompt_injection.py"],
    "domain-agnostic proof": ["tests/integration/test_domain_agnostic.py"],
}


def save(out: Path, name: str, data: Any) -> None:
    (out / name).write_text(json.dumps(data, indent=2, default=str) + "\n")


def wait_for_run(api: httpx.Client, run_id: str, timeout_s: float = 900) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        run: dict[str, Any] = api.get(f"/runs/{run_id}").json()
        if run["status"] != "running":
            return run
        time.sleep(2)
    raise SystemExit(f"run {run_id} still running after {timeout_s:.0f}s")


def stream_question(api: httpx.Client, question: str) -> list[dict[str, Any]]:
    """POST /chat/stream and collect the server-sent events in order."""
    events: list[dict[str, Any]] = []
    name = None
    with api.stream("POST", "/chat/stream", json={"question": question}, timeout=900) as res:
        res.raise_for_status()
        for line in res.iter_lines():
            if line.startswith("event:"):
                name = line.removeprefix("event:").strip()
            elif line.startswith("data:") and name:
                events.append({"event": name, **json.loads(line.removeprefix("data:").strip())})
                name = None
    return events


def usage(run: dict[str, Any]) -> dict[str, Any]:
    steps = run.get("steps", [])
    llm = [s for s in steps if s["kind"] == "llm"]
    return {
        "steps": len(steps),
        "nodes": sum(1 for s in steps if s["kind"] == "node"),
        "tool_calls": sum(1 for s in steps if s["kind"] == "tool"),
        "retrievals": sum(1 for s in steps if s["kind"] == "retrieval"),
        "llm_calls": len(llm),
        "llm_calls_failed": sum(1 for s in llm if s["error"]),
        "prompt_tokens": sum(s["prompt_tokens"] or 0 for s in llm),
        "completion_tokens": sum(s["completion_tokens"] or 0 for s in llm),
        "cost_usd": round(sum(s["cost_usd"] or 0 for s in llm), 6),
        "models": sorted({f"{s['provider']}/{s['model']}" for s in llm if s["provider"]}),
    }


def run_tests(out: Path) -> dict[str, Any]:
    proc = subprocess.run(
        ["uv", "run", "pytest", "--cov", "--cov-report=term", "-q", "-p", "no:cacheprovider"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    (out / "tests.txt").write_text(proc.stdout[-6000:])
    passed = re.search(r"(\d+) passed", proc.stdout)
    failed = re.search(r"(\d+) failed", proc.stdout)
    skipped = re.search(r"(\d+) skipped", proc.stdout)
    coverage = re.search(r"Total coverage: ([\d.]+)%", proc.stdout)
    layers = {}
    for layer, paths in TEST_LAYERS.items():
        collected = subprocess.run(
            ["uv", "run", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider", *paths],
            cwd=ROOT,
            capture_output=True,
            text=True,
        ).stdout
        layers[layer] = sum(1 for line in collected.splitlines() if "::" in line)
    return {
        "command": "make test",
        "exit_code": proc.returncode,
        "passed": int(passed.group(1)) if passed else 0,
        "failed": int(failed.group(1)) if failed else 0,
        "skipped": int(skipped.group(1)) if skipped else 0,
        "coverage_percent": float(coverage.group(1)) if coverage else None,
        "layers": layers,
    }


def latest_ci() -> dict[str, Any] | None:
    try:
        raw = subprocess.run(
            [
                "gh",
                "run",
                "list",
                "--workflow",
                "ci.yml",
                "--branch",
                "main",
                "--status",
                "completed",
                "--limit",
                "1",
                "--json",
                "databaseId,headSha,conclusion,url,createdAt",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return None
    runs = json.loads(raw)
    return runs[0] if runs else None


def ragas_rows() -> list[dict[str, str]]:
    lines = (ROOT / "evals" / "history.csv").read_text().splitlines()
    header = lines[0].split(",")
    latest: dict[tuple[str, str, str], dict[str, str]] = {}
    for line in lines[1:]:
        row = dict(zip(header, line.split(","), strict=True))
        latest[(row["retriever"], row["answerer"], row["judge"])] = row
    return list(latest.values())


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--api", default="http://localhost:8000")
    ap.add_argument("--out", type=Path, default=ROOT / "docs" / "evidence")
    ap.add_argument("--token", default=os.environ.get("WRITE_TOKEN", ""))
    ap.add_argument("--skip-tests", action="store_true")
    ap.add_argument(
        "--tests-only", action="store_true", help="add test counts to an existing capture"
    )
    args = ap.parse_args()
    out: Path = args.out
    out.mkdir(parents=True, exist_ok=True)
    if args.tests_only:
        captured = json.loads((out / "summary.json").read_text())
        captured["tests"] = run_tests(out)
        save(out, "summary.json", captured)
        write_readme(out, captured)
        print(json.dumps(captured["tests"], indent=1), file=sys.stderr)
        return
    headers = {"Authorization": f"Bearer {args.token}"} if args.token else {}
    api = httpx.Client(base_url=args.api, headers=headers, timeout=120)
    captured_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    commit = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True
    ).stdout.strip()

    health = api.get("/healthz").json()
    model = api.get("/model").json()
    save(out, "healthz.json", health)
    save(out, "model.json", model)
    print("api:", health["version"], "providers:", health["llm_providers"], file=sys.stderr)

    start = time.perf_counter()
    run_id = api.post("/scan").json()["run_id"]
    scan = wait_for_run(api, run_id)
    scan_wall_s = round(time.perf_counter() - start, 1)
    save(out, "scan-run.json", scan)
    reports = [r for r in api.get("/incidents").json() if r["run_id"] == run_id]
    save(out, "scan-reports.json", reports)
    key_drift = next(r for r in reports if r["finding_type"] == "key_drift")
    save(out, "incident-key-drift.json", key_drift)
    save(out, "dashboard.json", api.get("/dashboard").json())
    print("scan:", run_id, scan["status"], f"{scan_wall_s}s", file=sys.stderr)

    asked = {}
    for slug, question in (("ask-mobile", MOBILE_QUESTION), ("ask-runbook", RUNBOOK_QUESTION)):
        events = stream_question(api, question)
        ask_run_id = next(e["run_id"] for e in events if e["event"] == "run")
        ask_run = wait_for_run(api, ask_run_id)
        save(out, f"{slug}-events.json", events)
        save(out, f"{slug}-run.json", ask_run)
        asked[slug] = {
            "question": question,
            "run_id": ask_run_id,
            "status": ask_run["status"],
            **usage(ask_run),
        }
        print(slug, ask_run_id, ask_run["status"], file=sys.stderr)

    expected = json.loads((ROOT / "data" / "sample" / "expected_anomalies.json").read_text())
    summary: dict[str, Any] = {
        "captured_at": captured_at,
        "commit": commit,
        "api_version": health["version"],
        "llm_providers": health["llm_providers"],
        "active_model": model,
        "scan": {
            "run_id": run_id,
            "status": scan["status"],
            "wall_seconds": scan_wall_s,
            "graph_latency_ms": scan["latency_ms"],
            **usage(scan),
            "findings": [
                {
                    "finding_type": r["finding_type"],
                    "title": r["title"],
                    "severity": r["severity"],
                    "status": r["status"],
                    "affected_records": r["affected_records"]["count"],
                    "analysis_by": r["analysis_by"],
                    "planted": expected.get(r["finding_type"]),
                }
                for r in reports
            ],
        },
        "questions": asked,
        "ragas": ragas_rows(),
        "ci": latest_ci(),
    }
    if not args.skip_tests:
        summary["tests"] = run_tests(out)
    save(out, "summary.json", summary)
    write_readme(out, summary)
    print(json.dumps({k: summary[k] for k in ("scan", "questions")}, indent=1), file=sys.stderr)


def write_readme(out: Path, s: dict[str, Any]) -> None:
    scan = s["scan"]
    models = ", ".join(scan["models"]) or "none (templates and extractive answers)"
    tests = s.get("tests")
    lines = [
        "# Captured evidence",
        "",
        "Raw responses from a local ReconMind stack, captured by "
        "[`scripts/capture_readme_evidence.py`](../../scripts/capture_readme_evidence.py). "
        "The README's report, trace excerpt and results are quoted from these files.",
        "",
        "| | |",
        "|---|---|",
        f"| Captured | {s['captured_at']} |",
        f"| Commit | `{s['commit']}` |",
        f"| API | {s['api_version']}, providers `{', '.join(s['llm_providers'])}` |",
        f"| Model calls went to | {models} |",
        f"| Scan run | `{scan['run_id']}` ({scan['status']}) |",
        f"| Scan wall time | {scan['wall_seconds']} s |",
        f"| Scan steps | {scan['nodes']} agent nodes, {scan['tool_calls']} MCP tool calls, "
        f"{scan['retrievals']} retrievals, {scan['llm_calls']} model calls |",
        f"| Scan cost | ${scan['cost_usd']:.4f} ({scan['prompt_tokens']} prompt + "
        f"{scan['completion_tokens']} completion tokens) |",
    ]
    for slug, q in s["questions"].items():
        lines.append(f"| {slug} run | `{q['run_id']}` ({q['status']}): {q['question']} |")
    if tests:
        lines.append(
            f"| Tests | {tests['passed']} passed, {tests['failed']} failed, "
            f"{tests['coverage_percent']}% coverage |"
        )
    lines += ["", "| Severity | Finding | Status | Written by |", "|---|---|---|---|"]
    lines += [
        f"| {f['severity']} | {f['title']} | {f['status']} | {f['analysis_by']} |"
        for f in scan["findings"]
    ]
    lines += [
        "",
        "`Written by` is who wrote the root cause, fix and open questions: the model's "
        "provider, or `template` when the model's reply failed validation twice. Counts, "
        "severity and the problem statement always come from the deterministic checks.",
        "",
        "| File | What it is |",
        "|---|---|",
        "| `summary.json` | Everything below, condensed: counts, models, findings, tests, RAGAS |",
        "| `healthz.json`, `model.json` | `GET /healthz` and `GET /model` before the scan |",
        "| `scan-run.json` | `GET /runs/{id}` for the scan: every traced step |",
        "| `scan-reports.json` | The incident reports the scan produced |",
        "| `incident-key-drift.json` | The key-drift report quoted in the README |",
        "| `dashboard.json` | `GET /dashboard` after the scan |",
        "| `ask-mobile-*.json` | Events streamed for the MOBILE question, and its run |",
        "| `ask-runbook-*.json` | Events streamed for a runbook question, and its run |",
        "| `tests.txt` | The tail of `make test`: pass count and coverage |",
        "",
        "Reproduce: start a freshly seeded stack with `make dev`, then run "
        "`uv run python scripts/capture_readme_evidence.py`.",
        "",
    ]
    (out / "README.md").write_text("\n".join(lines))


if __name__ == "__main__":
    main()
