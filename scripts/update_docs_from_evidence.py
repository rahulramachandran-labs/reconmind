"""Rewrite the parts of the docs that quote a real run, from docs/evidence/.

    uv run python scripts/update_docs_from_evidence.py

README.md marks each generated part with <!-- evidence:NAME --> ... <!-- /evidence:NAME -->
and everything between the markers is replaced: the trace excerpt, the quoted report,
the IncidentReport model, Results, the screens table, the test counts and the course
table. docs/VERIFY.md and docs/COURSE_MAPPING.md are written whole. Links to code are
pinned to the current commit, with line numbers read from the code itself, so push
before sharing them.

scripts/capture_readme_evidence.py runs this after every capture, so the numbers in
the docs are always the ones in docs/evidence/.
"""

import ast
import csv
import json
import re
import subprocess
import textwrap
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
EVIDENCE = ROOT / "docs" / "evidence"
REPO = "https://github.com/rahulramachandran-labs/reconmind"


def load(name: str) -> Any:
    return json.loads((EVIDENCE / name).read_text())


def head_sha() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.strip()


def span(path: str, name: str) -> tuple[int, int]:
    """First and last line of a top-level function or class, decorators included."""
    tree = ast.parse((ROOT / path).read_text())
    for node in tree.body:
        kinds = ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef
        if isinstance(node, kinds) and node.name == name:
            start = min([d.lineno for d in node.decorator_list] + [node.lineno])
            return start, node.end_lineno or node.lineno
    raise KeyError(f"{name} not found in {path}")


def link(sha: str, path: str, name: str, label: str) -> str:
    a, b = span(path, name)
    return f"[{label}]({REPO}/blob/{sha}/{path}#L{a}-L{b})"


def first_sentence(text: str) -> str:
    return re.split(r"(?<=[.!?])\s+", text.strip())[0]


def wrap(text: str, indent: int) -> str:
    return textwrap.fill(
        text, width=100, initial_indent=" " * indent, subsequent_indent=" " * (indent + 3)
    )


# -- README blocks -------------------------------------------------------------------


def trace_block(summary: dict[str, Any]) -> str:
    run = load("ask-mobile-run.json")
    steps = run["steps"]
    llm = [s for s in steps if s["kind"] == "llm"]
    model = f"{llm[0]['provider']}/{llm[0]['model']}" if llm else "no model"

    def tokens(s: dict[str, Any]) -> str:
        return f"{s['prompt_tokens']:,} + {s['completion_tokens']:,} tokens"

    def reply(s: dict[str, Any]) -> dict[str, Any]:
        text = (s.get("output") or {}).get("text", "")
        try:
            return dict(json.loads(text[text.find("{") : text.rfind("}") + 1]))
        except ValueError:
            return {}

    out = [
        f"run {run['id'][:8]}  \"{summary['questions']['ask-mobile']['question']}\"  "
        f"{run['status']}",
        "",
    ]
    tools = [s for s in steps if s["kind"] == "tool" and s["node"] == "data_quality"]
    failed = next((s for s in tools if s["name"].endswith("get_failed_tasks")), None)
    for s in steps:
        if s["kind"] == "llm" and s["node"] == "planner":
            plan = reply(s)
            out.append(
                f"planner       llm   planner   {s['provider']}/{s['model']}   "
                f"{s['latency_ms']:,} ms   {tokens(s)}   $0"
            )
            out.append(
                wrap(
                    f"-> intent: {plan.get('intent')}, specialists: "
                    f"{plan.get('specialists')}, confidence: {plan.get('confidence')}",
                    14,
                )
            )
            if plan.get("rationale"):
                out.append(wrap(f"   rationale: {plan['rationale']}", 14))
        elif s["kind"] == "tool" and s["node"] == "planner":
            out.append(
                f"planner       tool  {s['name']}   {s['latency_ms']} ms   "
                f"{json.dumps(s['input'])}"
            )
    if failed:
        f = failed["output"]["failures"][0]
        out.append(f"data_quality  tool  {failed['name']}   {failed['latency_ms']} ms")
        out.append(f"              <- {json.dumps(failed['input'])}")
        out.append(
            wrap(
                f"-> {f['task_id']} failed on {f['business_date']}: " f"{f['first_error_line']}", 14
            )
        )
        rest = [s for s in tools if s is not failed]
        names = sorted({s["name"].split("/")[1] for s in rest})
        lat = [s["latency_ms"] for s in rest]
        out.append(
            f"data_quality  tool  {', '.join(names)}: {len(rest)} calls, "
            f"{min(lat)}-{max(lat)} ms each"
        )
    for s in steps:
        if s["kind"] == "retrieval":
            out.append(f"{s['node']:<13} retrieval  {s['name']}   {s['latency_ms']:,} ms")
    if tools and not any(s["name"].startswith("analyse") for s in llm):
        out.append(
            "data_quality  (no write-up call: the finding already had one from the scan, "
            "so it was reused)"
        )
    for s in llm:
        if s["node"] == "planner":
            continue
        out.append(
            f"{s['node']:<13} llm   {s['name']}   {s['provider']}/{s['model']}   "
            f"{s['latency_ms']:,} ms   {tokens(s)}   $0"
        )
        r = reply(s)
        said = r.get("root_cause_hypothesis") or r.get("headline")
        if said:
            out.append(wrap(f"-> {first_sentence(said)}", 14))
    return "\n".join(
        [
            f"An excerpt from the trace of one captured run, the question "
            f"*{summary['questions']['ask-mobile']['question']}*, answered in "
            f"{run['latency_ms'] / 1000:.1f} s by `{model}`:",
            "",
            "```",
            *out,
            "```",
            "",
            f"The full trace, {len(steps)} steps with every input and output, is "
            "[`docs/evidence/ask-mobile-run.json`](docs/evidence/ask-mobile-run.json).",
        ]
    )


def report_block() -> str:
    k = load("incident-key-drift.json")
    m, t = k.get("model_analysis") or {}, k.get("template") or {}
    fix = " ".join(f"{i}. {x}" for i, x in enumerate(k["recommended_fix"], 1))
    ev = k["evidence"][0]
    runbooks = f"{k['sources'][0]['title']}: " + ", ".join(
        f"*{s['section']}*" for s in k["sources"]
    )
    who = (
        f"written by `{m['model']}` ({m['provider']}) in {m['latency_ms']:,} ms "
        f"({m['prompt_tokens']:,} prompt + {m['completion_tokens']:,} completion tokens, "
        f"${m['cost_usd']:.2f})"
        if m
        else "written from the template, because no model reply validated"
    )
    return "\n".join(
        [
            "The key-drift report from the captured scan, exactly as the API returned it:",
            "",
            f"> **Problem.** {k['problem_statement']}",
            ">",
            f"> **Affected records.** {k['affected_records']['detail']} · **Severity** "
            f"{k['severity']} · **Status** {k['status']}",
            ">",
            f"> **Root-cause hypothesis.** {k['root_cause_hypothesis']}",
            ">",
            f"> **Recommended fix.** {fix}",
            ">",
            f"> **Confidence.** {k['confidence']:.2f} ({k['confidence_label']})",
            ">",
            f"> **Open questions.** {' '.join(k['open_questions'])}",
            ">",
            f"> **Evidence.** `{ev['source']}`: {ev['summary']}",
            ">",
            f"> **Runbooks consulted.** {runbooks}",
            "",
            f"Run `{k['run_id']}`, captured {k['created_at'][:19].replace('T', ' ')} UTC · "
            f"`analysis_by: {k['analysis_by']}` · {who}. The problem statement and counts come "
            "from the deterministic check; the root cause, fix, confidence and open questions "
            "are the model's, with confidence capped at the template's "
            f"{t.get('confidence', 0):.2f} plus 0.15. The template's own version is stored "
            "beside it, and its hypothesis "
            f"reads: *\"{t.get('root_cause_hypothesis', '')}\"* Raw JSON: "
            "[`docs/evidence/incident-key-drift.json`](docs/evidence/incident-key-drift.json).",
        ]
    )


def schema_block(sha: str) -> str:
    path = "app/agents/schemas.py"
    a, b = span(path, "IncidentReport")
    code = "\n".join((ROOT / path).read_text().splitlines()[a - 1 : b])
    return "\n".join(
        [
            "<details>",
            "<summary>The report contract: every report is validated against this Pydantic "
            "model before it is stored</summary>",
            "",
            f"From [`{path}`]({REPO}/blob/{sha}/{path}#L{a}-L{b}):",
            "",
            "```python",
            code,
            "```",
            "",
            "</details>",
        ]
    )


def results_block(s: dict[str, Any]) -> str:
    sc, t, ci = s["scan"], s.get("tests") or {}, s.get("ci") or {}
    gate = next(
        (r for r in s["ragas"] if r["retriever"] == "hybrid" and r["answerer"] == "extractive"),
        None,
    )
    f = {x["finding_type"]: x for x in sc["findings"]}
    p = {k: v["planted"] for k, v in f.items()}
    rows = [
        (
            "Schema drift",
            f"`{p['schema_drift']['file']}` renames `channel_basket_id` to `basket_ref`: "
            f"{p['schema_drift']['affected_rows']} rows",
            "schema_drift",
        ),
        (
            "Key drift",
            f"`{p['key_drift']['location_id']}` also reports as "
            f"`{p['key_drift']['drifted_outlet_id']}`: {p['key_drift']['drifted_rows']} of "
            f"{p['key_drift']['rows_in_window']:,} rows",
            "key_drift",
        ),
        (
            "Duplicate submission",
            f"`{p['duplicate_submission']['resend_file']}` supersedes "
            f"{p['duplicate_submission']['superseded_rows']} rows, "
            f"{p['duplicate_submission']['changed_rows']} with changed values, after the DAG ran",
            "duplicate_submission",
        ),
        (
            "Volume anomaly",
            f"`{p['volume_anomaly']['file']}`: {p['volume_anomaly']['rows']} rows vs "
            f"{p['volume_anomaly']['trailing_avg_7d']} trailing, "
            f"{p['volume_anomaly']['minutes_after_sla']} min late",
            "volume_anomaly",
        ),
    ]
    out = [
        f"From the last capture, on {s['captured_at'][:10]}: a freshly seeded local stack with "
        "Groq's free tier first in the fallback chain, and every scenario a reviewer would try "
        "([`docs/evidence/`](docs/evidence/README.md)). Planted sizes are from "
        "[`expected_anomalies.json`](data/sample/expected_anomalies.json).",
        "",
        "| Planted anomaly | Planted size | Finding produced | Severity | Outcome | Written by |",
        "|---|---|---|---|---|---|",
    ]
    for name, size, key in rows:
        x = f[key]
        expected = x["planted"]["expected_severity"]
        sev = x["severity"] + (", as expected" if x["severity"] == expected else f" ({expected})")
        outcome = "held for review" if x["status"] == "pending_review" else x["status"]
        out.append(
            f"| {name} | {size} | {x['title']}; {x['affected_records']} records | {sev} | "
            f"{outcome} | `{x.get('written_by', x['analysis_by'])}` |"
        )
    caught = len(sc["findings"]) == 4 and all(
        x["severity"] == x["planted"]["expected_severity"] for x in sc["findings"]
    )
    out += [
        "",
        (
            "All four planted anomalies were found, each by the specialist expected to find it "
            "and at the expected severity, and nothing else was flagged."
            if caught
            else "Not every planted anomaly was found as expected; see the table."
        )
        + f" The scan took {sc['wall_seconds']} s from the request to four written-up findings: "
        f"{sc['nodes']} agent nodes, {sc['tool_calls']} MCP tool calls, {sc['retrievals']} "
        f"retrievals and {sc['llm_calls']} model calls ({sc['prompt_tokens']:,} prompt and "
        f"{sc['completion_tokens']:,} completion tokens, ${sc['cost_usd']:.2f} on the free tier).",
        "",
        "Then the questions, each a real run:",
        "",
    ]
    q = s["questions"]

    def went(a: dict[str, Any]) -> str:
        if a.get("intent") == "investigate":
            names = [x.replace("_", "-").title() for x in a.get("specialists") or []]
            return f"went to the {' and '.join(names)} agent{'s' if len(names) > 1 else ''}"
        if a.get("intent") == "explore":
            return "went to the Explorer"
        if a.get("intent") == "answer":
            return "was answered from the runbooks"
        return f"was routed `{a.get('intent')}`"

    for slug in ("ask-mobile", "ask-runbook", "ask-follow-up", "ask-explore"):
        a = q.get(slug)
        if not a:
            continue
        line = (
            f"- *{a['question']}* {went(a)} in {a['latency_ms'] / 1000:.1f} s, "
            f"{a['llm_calls']} model call{'s' if a['llm_calls'] != 1 else ''}"
        )
        if slug == "ask-follow-up":
            line += " (asked in the same session, so the Planner saw the question before it)"
        if a.get("tools_used"):
            tools = ", ".join(f"`{x.split('/')[1]}`" for x in a["tools_used"])
            line += f"; the model chose {tools}"
        if a.get("reply"):
            said = first_sentence(a["reply"]).rstrip(".")
            line += f". It said: *\u201c{said}.\u201d*"
        out.append(line if line.endswith("*") else line + ".")
    rg, rs = s.get("regenerate_s1") or {}, s.get("rescan") or {}
    after = s.get("feed_after", [])
    out.append("")
    notes = []
    if rg:
        m = rg["model_analysis"]
        notes.append(
            "Writing the S1 up again with `POST /incidents/{id}/regenerate` returned HTTP "
            f"{rg['status_code']}, `analysis_by: {rg['analysis_by']}`, from "
            f"`{m['provider']}/{m['model']}` in {m['latency_ms']:,} ms, with the template's "
            "version kept beside it."
        )
    if s.get("review_s1"):
        notes.append("Approving it with a note resumed its paused run and published it.")
    if rs:
        s1: dict[str, Any] = next((x for x in after if x["severity"] == "S1"), {})
        fell = rs.get("fallbacks") or []
        notes.append(
            f"A second scan took {rs.get('latency_ms', 0) / 1000:.1f} s and paused for nothing; "
            f"the feed still held {len(after)} findings, each counted as seen again (the S1 "
            f"{s1.get('seen_count')} times, counting any question that looked at it). It reused "
            f"the stored write-ups rather than asking the model again, so its {rs['llm_calls']} "
            f"model call{'s' if rs['llm_calls'] != 1 else ''} went to the summary"
            + (f", after falling back past {', '.join(fell)}." if fell else ".")
        )
    if notes:
        out.append(" ".join(notes))
        out.append("")
    tail = []
    if t:
        tail.append(
            f"`make test`: {t['passed']} passed, {t['failed']} failed, "
            f"{t['coverage_percent']}% line and branch coverage "
            "([`tests.txt`](docs/evidence/tests.txt))."
        )
    if gate:
        tail.append(
            f"The RAGAS gate: {gate['gate']} (faithfulness {float(gate['faithfulness']):.3f}, "
            f"answer relevancy {float(gate['answer_relevancy']):.3f}, context precision "
            f"{float(gate['context_precision']):.3f}, context recall "
            f"{float(gate['context_recall']):.3f})."
        )
    if ci:
        tail.append(
            f"CI: [run {ci['databaseId']}]({ci['url']}) on `{ci['headSha'][:7]}`, "
            f"{ci['conclusion']}."
        )
    out.append(" ".join(tail))
    return "\n".join(out)


SCREENS = [
    (
        "Dashboard",
        "dashboard.png",
        "Latest business date against its trailing week, open findings by severity with the "
        "S1 waiting for review, the last DAG run, and today's model calls, tokens and cost. "
        "The chart flags POSFEED's light day.",
    ),
    (
        "Incident feed",
        "incidents.png",
        "One row per finding, with who wrote it up and how many scans have seen it.",
    ),
    (
        "Incident detail: model analysis",
        "incident-detail.png",
        "The key-drift report as the model wrote it. The chip names the model, its latency, "
        "tokens and cost.",
    ),
    (
        "Incident detail: deterministic checks",
        "incident-template.png",
        "The template the model's answer is held against: the same problem and counts, and a "
        "calibrated confidence. *Side by side* shows both at once.",
    ),
    ("Review queue", "review.png", "The S1 waits for a person, with the reason it paused."),
    ("Ask ReconMind: an investigation", "ask.png", None),
    (
        "Ask ReconMind: a runbook question",
        "ask-runbook.png",
        "Answered from the runbooks with numbered citations, and the footer names the model "
        "that answered.",
    ),
    (
        "Ask ReconMind: a fact no check covers",
        "ask-explore.png",
        "The Planner sends it to the Explorer, which picks the read-only tools itself (at most "
        "three), then answers from what they returned.",
    ),
    (
        "Traces",
        "trace.png",
        "The scan's trace: each agent, then its MCP tool calls, retrievals and model calls "
        "with their latency. The headline and summary at the top are the model's.",
    ),
    (
        "Docs & runbooks, hybrid",
        "docs-hybrid.png",
        "`basket_ref ContractViolation` with hybrid search: the schema-drift runbook and "
        "incident INC-0438 come first. The badges show each hit's dense and BM25 rank; INC-0438 "
        "is 10th on meaning alone and 1st on keywords.",
    ),
    (
        "Docs & runbooks, dense only",
        "docs-dense.png",
        "The same query with embeddings only: docs and dbt models for the transactions table "
        "fill the top four, the runbook is 5th and the incident isn't in the top five.",
    ),
    (
        "Verify",
        "verify.png",
        "Each planted anomaly beside the finding this deployment produced, the chaos test that "
        "proves it, and the template's and the model's root causes side by side.",
    ),
]


def screens_block() -> str:
    events = load("ask-mobile-events.json")
    summ = next((e for e in events if e["event"] == "summary"), None)
    run = load("ask-mobile-run.json")
    rep = next((s for s in run["steps"] if s["name"] == "reporter:summary"), None)
    ask = "The MOBILE question goes to Data-Quality only, and the steps stream in."
    if summ and rep:
        quote = f"{summ['headline'].rstrip('.')}. {first_sentence(summ['summary'])}"
        ask += (
            " From the captured run, the first two sentences of the answer, written by "
            f"`{rep['provider']}/{rep['model']}`: *“{quote}”*"
        )
    out = ["| Screen | |", "|---|---|"]
    for name, img, caption in SCREENS:
        out.append(
            f"| **{name}**<br><br>{caption or ask} | "
            f'<img src="docs/screenshots/{img}" width="560" alt="{name}"> |'
        )
    return "\n".join(out)


def testing_block(s: dict[str, Any]) -> str:
    t = s.get("tests")
    if not t:
        return ""
    layers = t["layers"]
    return "\n".join(
        [
            "From the last captured run of `make test` "
            f"([`docs/evidence/tests.txt`](docs/evidence/tests.txt)): {t['passed']} passed, "
            f"{t['failed']} failed, {t['coverage_percent']}% coverage.",
            "",
            "| Layer | Tests | What it covers |",
            "|---|---|---|",
            f"| Unit | {layers['unit']} | Retrieval (tokenizer, RRF, reranker), the model fallback "
            "chain, structured output, prompts, tracing, the synthetic generator, rate limits |",
            f"| Integration | {layers['integration']} | Postgres and the append-only ledger, both "
            "MCP servers through a real client, the agent graph end to end, the API |",
            f"| of which prompt injection | {layers['prompt injection']} | A runbook carrying "
            "planted instructions can't change a severity or approve anything "
            "([test](tests/integration/test_prompt_injection.py)) |",
            f"| of which domain-agnostic proof | {layers['domain-agnostic proof']} | "
            "The same graph runs on the support-triage domain, and no agent module imports "
            "a domain "
            "([test](tests/integration/test_domain_agnostic.py)) |",
            f"| Chaos | {layers['chaos']} | Each anomaly planted on its own is caught by the right "
            "agent at the right severity, a clean pipeline raises nothing, and a scan fits the "
            "30-second budget ([tests](tests/chaos/test_injected_anomalies.py)) |",
        ]
    )


# (module, concept, [(path, symbol, label)], [(path, symbol, label)])
COURSE = [
    (
        "GenAI foundations",
        "Delimited, untrusted context in prompts; Pydantic-validated structured output with a "
        "retry loop",
        [
            ("app/rag/prompts.py", "format_passages", "`format_passages`"),
            ("app/llm/structured.py", "structured", "`structured`"),
        ],
        [
            (
                "tests/integration/test_prompt_injection.py",
                "test_planted_instructions_do_not_change_agent_behaviour",
                "planted injection",
            ),
            (
                "tests/unit/test_structured.py",
                "test_reprompts_with_the_validation_error",
                "re-prompt on invalid JSON",
            ),
        ],
    ),
    (
        "Models and APIs",
        "Provider abstraction and fallback across OpenAI, Anthropic, Groq, Gemini, OpenRouter "
        "and Ollama; token and cost accounting per call",
        [
            ("app/llm/providers.py", "build_providers", "`build_providers`"),
            ("app/llm/providers.py", "LLMChain", "`LLMChain`"),
        ],
        [
            (
                "tests/unit/test_llm_chain.py",
                "test_first_healthy_provider_answers_and_failures_are_recorded",
                "fallback order",
            ),
            (
                "tests/unit/test_llm_chain.py",
                "test_a_rate_limited_free_tier_falls_through_to_the_next_one",
                "rate-limited free tier",
            ),
        ],
    ),
    (
        "LangChain",
        "Markdown and dbt YAML loaders, section-aware splitting, a `BaseRetriever`, a "
        "`ChatPromptTemplate` with a `MessagesPlaceholder`, chat memory as a "
        "`BaseChatMessageHistory` over Postgres",
        [
            ("app/retrieval/corpus.py", "load_corpus", "`load_corpus`"),
            ("app/retrieval/chunking.py", "chunk_docs", "`chunk_docs`"),
            ("app/retrieval/hybrid.py", "HybridRetriever", "`HybridRetriever`"),
            ("app/rag/prompts.py", "answer_messages", "`ANSWER_PROMPT`"),
            ("app/memory/sessions.py", "SessionHistory", "`SessionHistory`"),
        ],
        [
            ("tests/unit/test_corpus.py", "test_chunks_carry_title_and_section", "chunk metadata"),
            (
                "tests/unit/test_hybrid.py",
                "test_hybrid_is_a_langchain_retriever",
                "LangChain retriever",
            ),
            (
                "tests/unit/test_rag.py",
                "test_the_answer_prompt_is_a_chat_prompt_template",
                "prompt template",
            ),
            (
                "tests/unit/test_sessions.py",
                "test_a_session_is_a_langchain_message_history",
                "message history",
            ),
        ],
    ),
    (
        "RAG",
        "Chunking, BM25 + dense hybrid, RRF, reranking, a RAGAS gate in CI",
        [
            ("app/retrieval/bm25.py", "tokenize", "`tokenize`"),
            ("app/retrieval/hybrid.py", "rrf", "`rrf`"),
            ("app/retrieval/rerank.py", "_Base", "reranker"),
            ("evals/run_ragas.py", "OfflineJudge", "offline judge"),
        ],
        [
            ("tests/unit/test_hybrid.py", "test_rrf_rewards_agreement_between_lists", "RRF"),
            (
                "tests/unit/test_hybrid.py",
                "test_bm25_finds_exact_identifiers_in_the_real_corpus",
                "exact identifiers",
            ),
        ],
    ),
    (
        "Agentic AI",
        "LangGraph StateGraph, conditional edges, parallel specialists, checkpoints, "
        "human-in-the-loop, and an Explorer where the model chooses its own tools",
        [
            ("app/agents/graph.py", "build_graph", "`build_graph`"),
            ("app/agents/review.py", "report_review", "`interrupt()`"),
            ("app/agents/bootstrap.py", "build_investigations", "Postgres checkpointer"),
            ("app/agents/explorer.py", "run", "Explorer (tool choice)"),
        ],
        [
            (
                "tests/integration/test_agents.py",
                "test_specialists_run_concurrently",
                "parallel specialists",
            ),
            (
                "tests/integration/test_agents.py",
                "test_approving_the_review_resumes_and_writes_the_ledger",
                "pause and resume",
            ),
            (
                "tests/integration/test_agents.py",
                "test_the_explorer_answers_from_the_tools_it_chose",
                "model picks tools",
            ),
        ],
    ),
    (
        "MCP",
        "Host, client and server; two read-only servers; stdio vs HTTP transports",
        [
            ("mcp_servers/warehouse_metadata/server.py", "build_server", "warehouse server"),
            (
                "mcp_servers/orchestration_metadata/server.py",
                "build_server",
                "orchestration server",
            ),
            ("app/tools/mcp_toolbox.py", "MCPToolBox", "`MCPToolBox`"),
        ],
        [
            (
                "tests/integration/test_warehouse_mcp.py",
                "test_no_sql_and_bad_inputs_rejected",
                "inputs validated, no SQL",
            ),
            (
                "tests/unit/test_orchestration_mcp.py",
                "test_tools_are_listed_and_read_only",
                "read-only tools",
            ),
        ],
    ),
    (
        "Observability and deployment",
        "LangFuse tracing, FastAPI, Docker, Render and Vercel, CI/CD",
        [
            ("app/observability/tracer.py", "RunTracer", "`RunTracer`"),
            ("app/llm/traced.py", "TracedLLM", "`TracedLLM`"),
        ],
        [
            (
                "tests/unit/test_tracer.py",
                "test_langfuse_mirror_nests_children_under_the_node",
                "LangFuse nesting",
            ),
            (
                "tests/integration/test_agents.py",
                "test_every_llm_call_is_traced",
                "every call traced",
            ),
            (
                "tests/unit/test_structured.py",
                "test_llm_calls_outside_a_run_are_refused",
                "untraced call refused",
            ),
        ],
    ),
]
EXTRA_WHERE = {
    "RAG": ["[RAGAS job](.github/workflows/ci.yml)"],
    "Observability and deployment": [
        "[Dockerfile](Dockerfile)",
        "[render.yaml](render.yaml)",
        "[ci.yml](.github/workflows/ci.yml)",
    ],
}


def course_rows(sha: str, prefix: str = "") -> list[str]:
    rows = ["| Module | Concept demonstrated | Where | Test |", "|---|---|---|---|"]
    for module, concept, where, tests in COURSE:
        w = [link(sha, p, n, lbl) for p, n, lbl in where]
        w += [x.replace("](", f"]({prefix}") for x in EXTRA_WHERE.get(module, [])]
        tl = [link(sha, p, n, lbl) for p, n, lbl in tests]
        rows.append(f"| {module} | {concept} | {' · '.join(w)} | {' · '.join(tl)} |")
    return rows


def course_block(sha: str) -> str:
    return "\n".join(
        [
            f"Links in *Where* and *Test* point at the exact lines, pinned to commit `{sha[:7]}`. "
            "[docs/COURSE_MAPPING.md](docs/COURSE_MAPPING.md) says more about each.",
            "",
            *course_rows(sha),
        ]
    )


# -- whole documents -------------------------------------------------------------------


def verify_doc(s: dict[str, Any], sha: str) -> str:
    reports = {r["finding_type"]: r for r in load("scan-reports.json")}
    expected = json.loads((ROOT / "data" / "sample" / "expected_anomalies.json").read_text())
    chaos_path = "tests/chaos/test_injected_anomalies.py"
    each = link(sha, chaos_path, "test_each_anomaly_is_caught_by_the_right_agent", "x")
    each_url = each[each.index("(") + 1 : -1]
    planted = {
        "key_drift": (
            "Key drift",
            "`LOC-0517` reports under its canonical `OUT-1017` and under "
            "`OUT-1071`, which isn't in `outlet_location_map`: **251** of 8,373 "
            "deduplicated rows (3.0%).",
        ),
        "duplicate_submission": (
            "Duplicate submission",
            "`S1002_20260612_1120_ECOMM.txt` "
            "repeats every key from `S1002_20260612_0304_ECOMM.txt`: **88** "
            "superseded rows, **3** with a corrected `qty` and `amount`, "
            "landed after that night's DAG run.",
        ),
        "schema_drift": (
            "Schema drift",
            "`S1003_20260616_0216_MOBILE.txt` renamed "
            "`channel_basket_id` to `basket_ref`: **82** rows land with a null "
            "dedup-key column and `validate_schema` fails with a "
            "`ContractViolation`.",
        ),
        "volume_anomaly": (
            "Volume anomaly",
            "`S1001_20260618_0638_POSFEED.txt` has **110** "
            "rows against a trailing 7-day average of **182.6** (40% below) and "
            "landed **161** minutes after the submitter SLA.",
        ),
    }
    out = [
        "# Verify it yourself",
        "",
        "The written companion to the [/verify page](https://reconmind-labs.vercel.app/verify) "
        "on the live app. For each problem planted in the synthetic data: what the generator "
        "planted, what the agents found, the test that proves they find it, and what the "
        "template and the model each wrote about it. Then how to ask your own question, and "
        "where the evaluation scores come from.",
        "",
        f"The findings and write-ups are from the captured run in "
        f"[`docs/evidence/`](evidence/README.md) ({s['captured_at'][:10]}). Links to code are "
        f"pinned to commit `{sha[:7]}`. This file is regenerated by "
        "[`scripts/update_docs_from_evidence.py`](../scripts/update_docs_from_evidence.py).",
        "",
        "## Planted, found, proven",
        "",
    ]
    for key in ("key_drift", "duplicate_submission", "schema_drift", "volume_anomaly"):
        name, what = planted[key]
        r, e = reports[key], expected[key]
        m, t = r.get("model_analysis") or {}, r.get("template") or {}
        agent = e["expected_agent"].replace("_", "-").title()
        found_status = "held for review" if r["status"] == "pending_review" else r["status"]
        model = (
            f"{m.get('root_cause_hypothesis', '')} *({m['provider']}/{m['model']}, "
            f"{m['latency_ms']:,} ms, "
            f"{m['prompt_tokens'] + m['completion_tokens']:,} tokens, $0)*"
            if m
            else "No model write-up in this capture."
        )
        out += [
            f"### {name}",
            "",
            "| | |",
            "|---|---|",
            f"| **Planted** | {what} Source: [`DATA_DICTIONARY.md`](../data/DATA_DICTIONARY.md), "
            "[`expected_anomalies.json`](../data/sample/expected_anomalies.json) |",
            f"| **Expected** | `{key}` from the {agent} agent, {e['expected_severity']} |",
            f"| **Found** | {r['severity']} *{r['title']}*, {r['affected_records']['count']} "
            f"records, by the {r['specialist'].replace('_', '-')} agent; {found_status} |",
            f"| **Proven by** | [`test_each_anomaly_is_caught_by_the_right_agent[{key}]`]"
            f"({each_url}): plants only this anomaly into a fresh database and fails unless the "
            "right agent reports it at the right severity. Runs in CI on every push. |",
            f"| **Template's root cause** | {t.get('root_cause_hypothesis', '')} |",
            f"| **Model's root cause** | {model} |",
            "",
        ]
    clean = link(sha, chaos_path, "test_a_clean_pipeline_raises_nothing", "test")
    budget = link(sha, chaos_path, "test_full_investigation_fits_the_latency_budget", "test")
    out += [
        f"A clean pipeline raises nothing ({clean}), and a full investigation fits a "
        f"30-second budget ({budget}).",
        "",
        "## Ask your own question",
        "",
        "The [/verify page](https://reconmind-labs.vercel.app/verify) and **Ask ReconMind** "
        "send any question through the live agent graph and link its trace. From a terminal:",
        "",
        "```bash",
        "curl -N https://reconmind-labs-api.onrender.com/chat/stream \\",
        "  -H 'content-type: application/json' \\",
        '  -d \'{"question": "Which submitter files landed late last week, and why?"}\'',
        "```",
        "",
        "The `plan` event shows how the Planner routed it, `answer` or `summary` names the "
        "model that wrote the reply, and `run` gives the id to open under **Traces**. "
        "`GET /model` says which model is answering right now.",
        "",
        "## Evaluation scores",
        "",
        "The latest row for each retriever, answerer and judge in "
        "[`evals/history.csv`](../evals/history.csv):",
        "",
        "| Retriever | Answers written by | Judged by | Faithfulness | Answer relevancy | "
        "Context precision | Context recall | Gate |",
        "|---|---|---|---|---|---|---|---|",
    ]
    latest: dict[tuple[str, str, str], dict[str, str]] = {}
    with (ROOT / "evals" / "history.csv").open() as fh:
        for row in csv.DictReader(fh):
            latest[(row["retriever"], row["answerer"], row["judge"])] = row
    for (ret, ans, jud), r in latest.items():
        out.append(
            f"| {ret} | `{ans}` | `{jud}` | {float(r['faithfulness']):.3f} | "
            f"{float(r['answer_relevancy']):.3f} | {float(r['context_precision']):.3f} | "
            f"{float(r['context_recall']):.3f} | {r['gate']} |"
        )
    out += [
        "",
        "How each judge works, and why the gate runs on extractive answers, is in "
        "[EVALUATION.md](EVALUATION.md).",
        "",
        "## Reproduce it",
        "",
        "```bash",
        "make bootstrap && make dev                          # seeded stack on :8000 and :3000",
        "uv run pytest -m chaos -v                           # each planted anomaly, one at a time",
        "uv run python scripts/capture_readme_evidence.py    # the scenarios behind docs/evidence/",
        "make eval                                           # RAGAS on the golden set",
        "```",
        "",
    ]
    return "\n".join(out)


NOTES = {
    "GenAI foundations": "Retrieved passages go to the model inside a delimited context block "
    "that a document cannot close, with an instruction to treat it as data. Every model "
    "reply the agents use is parsed into a Pydantic model; an invalid reply is re-prompted "
    "with the validation error, twice, then the template stands.",
    "Models and APIs": "One chain tries providers in order, benches one that fails for a "
    "cooldown, retries a free tier's 429 before moving on, and records provider, model, "
    "tokens and estimated cost for every call. `DEMO_MODE` removes the paid providers.",
    "LangChain": "Markdown with front matter and dbt model YAML are loaded as documents, split "
    "by section then size with the section carried into each chunk, and served through a "
    "LangChain `BaseRetriever`. The answer prompt is a `ChatPromptTemplate` whose "
    "`MessagesPlaceholder` takes the conversation so far, read from a "
    "`BaseChatMessageHistory` over the Postgres session store.",
    "RAG": "BM25 with an identifier-aware tokenizer and MiniLM embeddings each rank the "
    "corpus, reciprocal rank fusion merges them, and a cross-encoder re-scores the top 10. "
    "RAGAS scores the golden set on every push and fails CI below the thresholds.",
    "Agentic AI": "A LangGraph `StateGraph`: the Planner routes, specialists built from the "
    "domain adapter run in the same superstep, the Reporter decides who signs off, and "
    "`interrupt()` pauses the run in Postgres until a reviewer decides. For a question no "
    "check covers, the Explorer lets the model choose among the MCP tools, up to three "
    "calls, and answer from what they return (ADR 0013).",
    "MCP": "Two MCP servers expose warehouse and orchestrator metadata as typed, read-only "
    "tools. The agents reach them through one client over stdio, streamable HTTP or in "
    "process, and every call is traced.",
    "Observability and deployment": "Every node, tool call, retrieval and model call is a "
    "trace step in Postgres, mirrored to LangFuse; a model call outside a traced run is "
    "refused. The API ships as a Docker image to Render, the web app to Vercel, and CI "
    "gates both.",
}


def course_doc(sha: str) -> str:
    out = [
        "# Course mapping",
        "",
        "Where each module of the IIT Patna Generative AI & Agentic AI for Developers program "
        "shows up in ReconMind, with links to the exact lines and the test that covers it. "
        f"Links are pinned to commit `{sha[:7]}`; this file is regenerated by "
        "[`scripts/update_docs_from_evidence.py`](../scripts/update_docs_from_evidence.py).",
        "",
        *course_rows(sha, prefix="../"),
        "",
    ]
    for module, *_ in COURSE:
        out += [f"## {module}", "", NOTES[module], ""]
    return "\n".join(out)


def replace_block(text: str, name: str, body: str) -> str:
    pattern = re.compile(rf"(<!-- evidence:{name} -->\n).*?(\n<!-- /evidence:{name} -->)", re.S)
    if not pattern.search(text):
        raise SystemExit(f"README.md has no <!-- evidence:{name} --> block")
    return pattern.sub(lambda m: m.group(1) + body + m.group(2), text)


def main() -> None:
    s = load("summary.json")
    sha = head_sha()
    readme = ROOT / "README.md"
    text = readme.read_text()
    blocks = {
        "trace": trace_block(s),
        "report": report_block(),
        "schema": schema_block(sha),
        "results": results_block(s),
        "screens": screens_block(),
        "testing": testing_block(s),
        "course": course_block(sha),
    }
    for name, body in blocks.items():
        text = replace_block(text, name, body)
    readme.write_text(text)
    (ROOT / "docs" / "VERIFY.md").write_text(verify_doc(s, sha))
    (ROOT / "docs" / "COURSE_MAPPING.md").write_text(course_doc(sha))
    print(
        f"updated README.md ({len(blocks)} blocks), docs/VERIFY.md, docs/COURSE_MAPPING.md "
        f"at {sha[:7]}"
    )


if __name__ == "__main__":
    main()
