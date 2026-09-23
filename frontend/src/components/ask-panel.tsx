"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { ArrowUp, CheckCircle2, FileText, Loader2, PauseCircle, RotateCcw } from "lucide-react";

import { Markdown } from "@/components/markdown";
import { SeverityBadge } from "@/components/severity";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { chatStream, type Severity } from "@/lib/api";

const EXAMPLES = [
  "Anything wrong with the pipeline?",
  "Are there any duplicate submissions this week?",
  "Did the MOBILE file have a schema problem on 2026-06-16?",
  "Which file wins when a submitter resends the same day?",
];

const NODE_LABEL: Record<string, string> = {
  planner: "Planner routed the question",
  reconciliation: "Reconciliation agent checked dedup keys and key drift",
  data_quality: "Data-Quality agent checked contract, volume and timing",
  reporter: "Reporter wrote the incident reports",
  answer: "Answered from the runbooks",
  explore: "Explorer agent picked read-only tools and answered from what they returned",
  plan_review: "Plan check",
  report_review: "Human review applied",
};

type Finding = { severity: Severity; title: string; finding_type: string };
type Source = { chunk_id: string; doc_id: string; title: string; section: string; doc_type: string };
type Turn = {
  question: string;
  runId?: string;
  plan?: { intent: string; specialists: string[]; confidence: number; rationale: string };
  nodes: string[];
  findings: Finding[];
  answer?: string;
  provider?: string;
  model?: string;
  fallbacks?: string[];
  /** Who wrote each incident report in an investigation: a provider, or "template". */
  writtenBy: string[];
  /** Why a model's write-up was not used, when the report carries a reason. */
  writeUpError?: string;
  sources: Source[];
  summary?: { headline: string; summary: string };
  paused?: boolean;
  done?: { latency_ms: number; llm_calls: number; cost_usd: number };
  error?: string;
};

function AnsweredBy({ turn }: { turn: Turn }) {
  if (turn.answer !== undefined) {
    if (!turn.provider || turn.provider === "extractive") {
      return (
        <p className="text-xs text-amber">
          No model answered this one. It is an extractive answer: the most relevant runbook passages, quoted as they
          are.
        </p>
      );
    }
    return (
      <Badge variant="outline" className="font-mono">
        answered by {turn.provider}
        {turn.model && ` · ${turn.model}`}
        {turn.fallbacks?.length ? ` after ${turn.fallbacks.join(", ")} did not respond` : ""}
      </Badge>
    );
  }
  if (!turn.writtenBy.length) return null;
  const models = [...new Set(turn.writtenBy.filter((w) => w !== "template"))];
  if (!models.length) {
    return (
      <p className="text-xs text-amber">
        {turn.writeUpError
          ? `These write-ups came from templates. The model was asked: ${turn.writeUpError}`
          : "These write-ups came from templates: either no model is configured, or the findings were written up before one was."}
      </p>
    );
  }
  return (
    <Badge variant="outline" className="font-mono">
      written up by {models.join(", ")}
    </Badge>
  );
}

function TurnView({ turn }: { turn: Turn }) {
  const busy = !turn.done && !turn.paused && !turn.error;
  return (
    <section className="flex flex-col gap-3">
      <p className="self-end rounded-2xl rounded-br-sm bg-secondary px-4 py-2 text-sm">{turn.question}</p>
      <div className="flex flex-col gap-3 rounded-xl border bg-card p-4">
        {turn.plan && (
          <p className="text-xs text-muted-foreground">
            <span className="text-foreground">
              {turn.plan.intent === "investigate"
                ? `Investigating with ${turn.plan.specialists.map((s) => s.replace("_", "-")).join(" + ")}`
                : turn.plan.intent === "answer"
                  ? "Answering from the runbooks"
                  : turn.plan.intent === "explore"
                    ? "Looking at the data with tools"
                    : "Not sure what to check"}
            </span>{" "}
            · {turn.plan.rationale}
          </p>
        )}
        <ul className="flex flex-col gap-1 text-xs text-muted-foreground">
          {turn.nodes
            .filter((n) => NODE_LABEL[n] && n !== "planner")
            .map((n, i) => (
              <li key={i} className="flex items-center gap-1.5">
                <CheckCircle2 className="size-3 text-teal" /> {NODE_LABEL[n]}
              </li>
            ))}
          {busy && (
            <li className="flex items-center gap-1.5">
              <Loader2 className="size-3 animate-spin" /> working...
            </li>
          )}
        </ul>
        {turn.findings.length > 0 && (
          <ul className="flex flex-col gap-1.5">
            {turn.findings.map((f, i) => (
              <li key={i} className="flex items-center gap-2 text-sm">
                <SeverityBadge severity={f.severity} />
                <span className="truncate">{f.title}</span>
              </li>
            ))}
          </ul>
        )}
        {turn.summary && (
          <div className="flex flex-col gap-1">
            <p className="font-medium">{turn.summary.headline}</p>
            <p className="text-sm whitespace-pre-wrap text-muted-foreground">{turn.summary.summary}</p>
            <Link href="/incidents" className="text-xs text-teal hover:underline">
              Open the full write-ups in the incident feed
            </Link>
          </div>
        )}
        {turn.answer && (
          <div className="leading-relaxed">
            <Markdown>{turn.answer}</Markdown>
          </div>
        )}
        {turn.sources.length > 0 && (
          <ul className="flex flex-wrap gap-2">
            {turn.sources.map((s, i) => (
              <li key={s.chunk_id}>
                <Link href={`/docs/${s.doc_id}`} className="flex items-center gap-1 rounded-md border px-2 py-1 text-xs hover:border-teal/60">
                  <span className="font-mono text-amber">[{i + 1}]</span>
                  <FileText className="size-3 text-teal" />
                  {s.title}
                </Link>
              </li>
            ))}
          </ul>
        )}
        {turn.paused && (
          <p className="flex items-center gap-2 rounded-md border border-amber/40 bg-amber/10 px-3 py-2 text-sm">
            <PauseCircle className="size-4 text-amber" />
            Paused for a human decision.{" "}
            <Link href="/review" className="underline">
              Open the review queue
            </Link>
          </p>
        )}
        {turn.error && <p className="text-sm text-destructive">{turn.error}</p>}
        {(turn.done || turn.paused) && turn.runId && (
          <div className="flex flex-wrap items-center gap-3 border-t pt-2 text-xs text-muted-foreground">
            <AnsweredBy turn={turn} />
            {turn.done && <span>{(turn.done.latency_ms / 1000).toFixed(1)}s</span>}
            {turn.done && <span>{turn.done.llm_calls} LLM calls</span>}
            <Link href={`/traces/${turn.runId}`} className="hover:text-foreground">
              trace
            </Link>
          </div>
        )}
      </div>
    </section>
  );
}

export function AskPanel({ examples = EXAMPLES, inline = false }: { examples?: string[]; inline?: boolean } = {}) {
  const [question, setQuestion] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [sessionId, setSessionId] = useState<string | undefined>();
  const [loading, setLoading] = useState(false);
  const bottom = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turns]);

  function patch(fn: (t: Turn) => Turn) {
    setTurns((all) => all.map((t, i) => (i === all.length - 1 ? fn(t) : t)));
  }

  async function submit(q: string) {
    const text = q.trim();
    if (text.length < 3 || loading) return;
    setLoading(true);
    setQuestion("");
    setTurns((t) => [...t, { question: text, nodes: [], findings: [], writtenBy: [], sources: [] }]);
    try {
      for await (const { event, data } of chatStream(text, sessionId)) {
        const str = (k: string) => String(data[k] ?? "");
        if (event === "session") setSessionId(str("session_id"));
        else if (event === "run") patch((t) => ({ ...t, runId: str("run_id") }));
        else if (event === "plan") patch((t) => ({ ...t, plan: data as Turn["plan"] }));
        else if (event === "node") patch((t) => ({ ...t, nodes: [...t.nodes, str("node")] }));
        else if (event === "finding")
          patch((t) => ({ ...t, findings: [...t.findings, data as unknown as Finding] }));
        else if (event === "report") {
          const m = data.model_analysis as { provider?: string; model?: string } | null | undefined;
          const by = m?.provider ? `${m.provider}${m.model ? ` · ${m.model}` : ""}` : str("analysis_by") === "model" ? "model" : str("analysis_by");
          const why = str("model_error") || undefined;
          patch((t) => ({ ...t, writtenBy: [...t.writtenBy, by], writeUpError: t.writeUpError ?? why }));
        } else if (event === "summary") patch((t) => ({ ...t, summary: data as Turn["summary"] }));
        else if (event === "answer")
          patch((t) => ({
            ...t,
            answer: str("text"),
            provider: str("provider"),
            model: str("model") || undefined,
            fallbacks: (data.fallbacks as string[]) ?? [],
            sources: (data.sources as Source[]) ?? [],
          }));
        else if (event === "paused") patch((t) => ({ ...t, paused: true }));
        else if (event === "done") patch((t) => ({ ...t, done: data as Turn["done"] }));
        else if (event === "error") patch((t) => ({ ...t, error: str("message") }));
      }
    } catch (e) {
      patch((t) => ({
        ...t,
        error: `${(e as Error).message}. The API may be waking up on the free tier; give it 30 seconds and try again.`,
      }));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      {turns.length === 0 && (
        <div className="flex flex-wrap gap-2">
          {examples.map((ex) => (
            <button
              key={ex}
              type="button"
              onClick={() => submit(ex)}
              className="rounded-full border px-3 py-1 text-xs text-muted-foreground transition-colors hover:border-amber/60 hover:text-foreground"
            >
              {ex}
            </button>
          ))}
        </div>
      )}
      {turns.map((turn, i) => (
        <TurnView key={i} turn={turn} />
      ))}
      <div ref={bottom} />
      <form
        className={inline ? "flex flex-col gap-2" : "sticky bottom-4 flex flex-col gap-2"}
        onSubmit={(e) => {
          e.preventDefault();
          submit(question);
        }}
      >
        <div className="relative">
          <Textarea
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                submit(question);
              }
            }}
            placeholder={turns.length ? "Ask a follow-up..." : "Ask about the pipeline, a runbook, or a past incident..."}
            className="min-h-24 resize-none bg-card pr-14 text-base shadow-lg"
            maxLength={1000}
          />
          <Button type="submit" size="icon" className="absolute right-3 bottom-3" disabled={loading || question.trim().length < 3} aria-label="Ask">
            {loading ? <Loader2 className="animate-spin" /> : <ArrowUp />}
          </Button>
        </div>
        {sessionId && (
          <button
            type="button"
            onClick={() => {
              setTurns([]);
              setSessionId(undefined);
            }}
            className="flex w-fit items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
          >
            <RotateCcw className="size-3" /> New conversation
          </button>
        )}
      </form>
    </div>
  );
}
