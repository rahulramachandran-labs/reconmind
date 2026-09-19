"""Write the findings up again with the model the API is using now.

    WRITE_TOKEN=... python3 scripts/regenerate_reports.py --api https://reconmind-labs-api.onrender.com
    make regenerate-reports API=https://reconmind-labs-api.onrender.com

Calls POST /incidents/{id}/regenerate for each finding in the feed that has no
model write-up yet (all of them with --all). The template's version is kept
beside the model's. Standard library only, so the refresh workflow can run it
without installing anything.
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from typing import Any


def call(api: str, method: str, path: str, token: str = "", timeout: int = 300) -> Any:
    headers = {"X-Reviewer": "regenerate-reports"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(f"{api}{path}", method=method, headers=headers)  # noqa: S310
    with urllib.request.urlopen(req, timeout=timeout) as res:  # noqa: S310 (our own API)
        return json.loads(res.read())


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--api", default=os.environ.get("RECONMIND_API_URL", "http://localhost:8000"))
    ap.add_argument("--all", action="store_true", help="also findings that have a model write-up")
    ap.add_argument(
        "--pause", type=float, default=10, help="seconds between findings (free-tier limits)"
    )
    args = ap.parse_args()
    api, token = args.api.rstrip("/"), os.environ.get("WRITE_TOKEN", "")

    model = call(api, "GET", "/model")
    print(f"API model: {model['provider']} {model.get('model') or ''}".rstrip())
    if model["provider"] == "extractive":
        print("no model configured on the API; nothing to do")
        return 1
    incidents = call(api, "GET", "/incidents")
    todo = [r for r in incidents if args.all or not r.get("model_analysis")]
    print(f"{len(todo)} of {len(incidents)} findings to write up")
    failed = 0
    for i, r in enumerate(todo):
        if i:
            time.sleep(args.pause)
        try:
            out = call(api, "POST", f"/incidents/{r['id']}/regenerate", token)
        except urllib.error.HTTPError as exc:
            failed += 1
            print(f"  {r['severity']} {r['title']}: HTTP {exc.code} {exc.read().decode()[:200]}")
            continue
        m = out["model_analysis"]
        print(
            f"  {r['severity']} {r['title']}: {m['provider']}/{m['model']}, "
            f"{m['latency_ms']} ms, {m['prompt_tokens']}+{m['completion_tokens']} tokens, "
            f"${m['cost_usd']:.4f}"
        )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
