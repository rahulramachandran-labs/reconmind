"""Score the RAG pipeline on the golden set with RAGAS and gate on thresholds.

    uv run --group eval python evals/run_ragas.py                    # hybrid, offline judge
    uv run --group eval python evals/run_ragas.py --retriever dense  # the Phase A baseline
    uv run --group eval python evals/run_ragas.py --gate --record    # what CI and `make eval` run

Two judges:

offline (default, no API key needed)
    context_precision  ragas NonLLMContextPrecisionWithReference (rank-aware)
    context_recall     ragas NonLLMContextRecall
    faithfulness       share of answer sentences entailed by a retrieved passage,
                       scored by an NLI cross-encoder
    answer_relevancy   MS MARCO cross-encoder relevance of the answer to the question

llm (--judge llm, needs OPENAI_API_KEY or a reachable Ollama)
    the LLM-judged ragas metrics: Faithfulness, ResponseRelevancy,
    LLMContextPrecisionWithReference, LLMContextRecall

The reference contexts are the exact chunks listed in golden_set.jsonl, so the
context metrics use a 0.9 string-similarity threshold: a retrieved chunk counts
only if it is (almost) the reference chunk itself.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import math
import os
import re
import subprocess
import sys
import time
import types
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# ragas 0.4.3 still imports a Vertex AI chat model that langchain-community 0.4
# removed. Nothing here uses Vertex, so a placeholder module is enough.
_vertex = types.ModuleType("langchain_community.chat_models.vertexai")
_vertex.ChatVertexAI = type("ChatVertexAI", (), {})  # type: ignore[attr-defined]
sys.modules.setdefault("langchain_community.chat_models.vertexai", _vertex)

from ragas.dataset_schema import SingleTurnSample
from ragas.metrics import NonLLMContextPrecisionWithReference, NonLLMContextRecall

from app.core.config import Settings
from app.llm.providers import LLMChain
from app.rag.answer import answer_question
from app.retrieval.service import RetrievalService

EVALS = ROOT / "evals"
METRICS = ("faithfulness", "answer_relevancy", "context_precision", "context_recall")
NLI_MODEL = "cross-encoder/nli-MiniLM2-L6-H768"
# a bigger sibling of the reranker, so the model that ranks passages isn't grading answers
RELEVANCE_MODEL = "cross-encoder/ms-marco-MiniLM-L-12-v2"
_CITATION = re.compile(r"\s*\[\d+\]")


@dataclass
class Item:
    id: str
    question: str
    reference_answer: str
    reference_chunks: list[str]
    anomaly: str
    screen: str


def load_golden(path: Path) -> list[Item]:
    return [Item(**json.loads(line)) for line in path.read_text().splitlines() if line.strip()]


def answer_sentences(answer: str) -> list[str]:
    body = "\n".join(
        line for line in answer.splitlines() if not line.startswith("From the runbooks")
    )
    parts = re.split(r"(?<=[.!?])\s+|\n+", body)
    out = []
    for p in parts:
        p = _CITATION.sub("", p).strip(" -*")
        if len(p) > 12:
            out.append(p)
    return out


def premise_windows(context: str, size: int = 2) -> list[str]:
    body = context.split("\n", 1)[1] if "\n" in context else context
    units = [
        u.replace("**", "").strip(" -|*`")
        for u in re.split(r"(?<=[.!?])\s+|\n+", body)
        if len(u.strip(" -|*`")) > 3 and not u.strip().startswith("|---")
    ]
    if len(units) <= size:
        return [" ".join(units)] if units else []
    return [" ".join(units[i : i + size]) for i in range(len(units) - size + 1)]


class OfflineJudge:
    def __init__(self) -> None:
        from sentence_transformers import CrossEncoder

        self.nli = CrossEncoder(NLI_MODEL, device="cpu")
        labels = {v.lower(): k for k, v in self.nli.model.config.id2label.items()}
        self.entail = labels["entailment"]
        self.rel = CrossEncoder(RELEVANCE_MODEL, device="cpu")

    def faithfulness(self, answer: str, contexts: list[str]) -> float:
        """Share of answer sentences entailed by some passage.

        NLI models are trained on short premises, so each passage is cut into
        windows of two consecutive sentences or lines and a claim counts as
        supported if any window entails it (the SummaC zero-shot approach).
        """
        sentences = answer_sentences(answer)
        windows = [w for ctx in contexts for w in premise_windows(ctx)]
        if not sentences or not windows:
            return 0.0
        pairs = [(w, s) for s in sentences for w in windows]
        probs = self.nli.predict(pairs, apply_softmax=True, batch_size=64)
        supported = 0
        for i in range(len(sentences)):
            row = probs[i * len(windows) : (i + 1) * len(windows)]
            if max(float(p[self.entail]) for p in row) >= 0.5:
                supported += 1
        return supported / len(sentences)

    def answer_relevancy(self, question: str, answer: str) -> float:
        text = " ".join(answer_sentences(answer))
        if not text:
            return 0.0
        logit = float(self.rel.predict([(question, text)])[0])
        return 1 / (1 + math.exp(-logit))


def llm_judge_metrics(settings: Settings) -> list[Any]:
    from langchain_openai import ChatOpenAI, OpenAIEmbeddings
    from ragas.embeddings import LangchainEmbeddingsWrapper
    from ragas.llms import LangchainLLMWrapper
    from ragas.metrics import (
        Faithfulness,
        LLMContextPrecisionWithReference,
        LLMContextRecall,
        ResponseRelevancy,
    )

    from app.retrieval.embeddings import build_embeddings

    if settings.openai_api_key:
        key = settings.openai_api_key.get_secret_value()
        chat = ChatOpenAI(model=settings.openai_model, api_key=key)
        emb: Any = LangchainEmbeddingsWrapper(
            OpenAIEmbeddings(model=settings.openai_embeddings_model, api_key=key)
        )
    else:
        chat = ChatOpenAI(
            model=settings.ollama_model,
            base_url=settings.ollama_base_url.rstrip("/") + "/v1",
            api_key="ollama",
        )
        emb = LangchainEmbeddingsWrapper(
            build_embeddings("sentence-transformers", settings.embeddings_model)
        )
    llm = LangchainLLMWrapper(chat)
    return [
        Faithfulness(llm=llm),
        ResponseRelevancy(llm=llm, embeddings=emb),
        LLMContextPrecisionWithReference(llm=llm),
        LLMContextRecall(llm=llm),
    ]


async def score_context(sample: SingleTurnSample) -> tuple[float, float]:
    precision = NonLLMContextPrecisionWithReference(threshold=0.9)
    recall = NonLLMContextRecall(threshold=0.9)
    return (
        float(await precision.single_turn_ascore(sample)),
        float(await recall.single_turn_ascore(sample)),
    )


def git_sha() -> str:
    try:
        sha = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True)
        return sha + ("+dirty" if dirty.stdout.strip() else "")
    except (OSError, subprocess.CalledProcessError):
        return os.environ.get("GITHUB_SHA", "unknown")[:7]


def run(args: argparse.Namespace) -> dict[str, Any]:
    settings = Settings(retriever=args.retriever)
    if args.answerer == "extractive":
        settings = settings.model_copy(update={"llm_providers": []})
    retrieval = RetrievalService.from_settings(settings)
    llm = LLMChain.from_settings(settings)
    by_id = {c.metadata["chunk_id"]: c.page_content for c in retrieval.chunks}

    items = load_golden(args.golden)
    if args.limit:
        items = items[: args.limit]
    missing = [cid for it in items for cid in it.reference_chunks if cid not in by_id]
    if missing:
        raise SystemExit(f"golden set points at chunks that no longer exist: {missing}")

    judge = OfflineJudge() if args.judge == "offline" else None
    llm_metrics = llm_judge_metrics(settings) if args.judge == "llm" else []
    rows = []
    providers: set[str] = set()
    start = time.perf_counter()
    for it in items:
        ans = answer_question(it.question, retrieval, llm, k=args.k)
        providers.add(ans.provider)
        contexts = [c.text for c in ans.sources]
        sample = SingleTurnSample(
            user_input=it.question,
            response=ans.answer,
            reference=it.reference_answer,
            retrieved_contexts=contexts,
            reference_contexts=[by_id[c] for c in it.reference_chunks],
        )
        row: dict[str, Any] = {
            "id": it.id,
            "anomaly": it.anomaly,
            "retrieved": [c.chunk_id for c in ans.sources],
            "provider": ans.provider,
        }
        if judge is not None:
            row["context_precision"], row["context_recall"] = asyncio.run(score_context(sample))
            row["faithfulness"] = judge.faithfulness(ans.answer, contexts)
            row["answer_relevancy"] = judge.answer_relevancy(it.question, ans.answer)
        else:
            f, r, p, c = llm_metrics
            row["faithfulness"] = float(asyncio.run(f.single_turn_ascore(sample)))
            row["answer_relevancy"] = float(asyncio.run(r.single_turn_ascore(sample)))
            row["context_precision"] = float(asyncio.run(p.single_turn_ascore(sample)))
            row["context_recall"] = float(asyncio.run(c.single_turn_ascore(sample)))
        rows.append(row)

    scores = {
        m: round(sum(r[m] for r in rows if not math.isnan(r[m])) / len(rows), 4) for m in METRICS
    }
    return {
        "timestamp": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "commit": git_sha(),
        "retriever": args.retriever,
        "judge": args.judge,
        "answerer": "+".join(sorted(providers)),
        "n": len(rows),
        "seconds": round(time.perf_counter() - start, 1),
        "scores": scores,
        "by_anomaly": {
            a: {
                m: round(
                    sum(r[m] for r in rows if r["anomaly"] == a)
                    / sum(1 for r in rows if r["anomaly"] == a),
                    3,
                )
                for m in METRICS
            }
            for a in sorted({r["anomaly"] for r in rows})
        },
        "rows": rows,
    }


def record(result: dict[str, Any], gate: str) -> None:
    path = EVALS / "history.csv"
    new = not path.exists()
    with path.open("a", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        if new:
            w.writerow(
                ["timestamp", "commit", "retriever", "judge", "answerer", "n", *METRICS, "gate"]
            )
        w.writerow(
            [
                result["timestamp"],
                result["commit"],
                result["retriever"],
                result["judge"],
                result["answerer"],
                result["n"],
                *(result["scores"][m] for m in METRICS),
                gate,
            ]
        )


def check(result: dict[str, Any], thresholds: dict[str, float]) -> list[str]:
    return [
        f"{m} {result['scores'][m]:.3f} < {thresholds[m]:.2f}"
        for m in METRICS
        if result["scores"][m] < thresholds[m]
    ]


def summary_markdown(
    result: dict[str, Any], failures: list[str], thresholds: dict[str, float]
) -> str:
    lines = [
        f"### RAGAS ({result['judge']} judge, {result['retriever']} retrieval, "
        f"answers by {result['answerer']}, n={result['n']})",
        "",
        "| metric | score | threshold |",
        "|---|---|---|",
    ]
    for m in METRICS:
        mark = "ok" if result["scores"][m] >= thresholds[m] else "FAIL"
        lines.append(f"| {m} | {result['scores'][m]:.3f} | {thresholds[m]:.2f} {mark} |")
    if failures:
        lines += ["", "Gate failed: " + "; ".join(failures)]
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--golden", type=Path, default=EVALS / "golden_set.jsonl")
    ap.add_argument("--retriever", choices=["hybrid", "dense", "bm25"], default="hybrid")
    ap.add_argument("--judge", choices=["offline", "llm"], default="offline")
    ap.add_argument("--answerer", choices=["chain", "extractive"], default="chain")
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--gate", action="store_true", help="exit 1 if a metric is under threshold")
    ap.add_argument("--record", action="store_true", help="append to evals/history.csv")
    ap.add_argument("--out", type=Path, default=EVALS / "results" / "latest.json")
    args = ap.parse_args()

    thresholds = yaml.safe_load((EVALS / "thresholds.yaml").read_text())["min"]
    result = run(args)
    failures = check(result, thresholds)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n")
    md = summary_markdown(result, failures, thresholds)
    print(md)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as fh:
            fh.write(md)
    if args.record:
        record(result, "fail" if failures else "pass")
    if args.gate and failures:
        sys.exit(1)


if __name__ == "__main__":
    main()
