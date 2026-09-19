"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { ArrowLeft, Bot, Database, ExternalLink, Search, Workflow } from "lucide-react";

import { StatusText } from "@/components/severity";
import { Skeleton } from "@/components/ui/skeleton";
import { getRun, type Run, type RunStep } from "@/lib/api";
import { cn } from "@/lib/utils";

const ICON = { node: Workflow, llm: Bot, tool: Database, retrieval: Search };

// Specialists run at the same time, so ordering by start time alone would interleave their
// tool calls. Each step goes under the latest run of the node that recorded it.
function grouped(steps: RunStep[]): RunStep[] {
  const sorted = [...steps].sort((a, b) => a.started_at.localeCompare(b.started_at));
  const nodes = sorted.filter((s) => s.kind === "node");
  const kids = new Map<RunStep, RunStep[]>(nodes.map((n) => [n, []]));
  const loose: RunStep[] = [];
  for (const s of sorted) {
    if (s.kind === "node") continue;
    const owner = [...nodes].reverse().find((n) => n.name === s.node && n.started_at <= s.started_at);
    if (owner) kids.get(owner)?.push(s);
    else loose.push(s);
  }
  return [...nodes.flatMap((n) => [n, ...(kids.get(n) ?? [])]), ...loose];
}

function StepRow({ step }: { step: RunStep }) {
  const Icon = ICON[step.kind];
  return (
    <li className={cn("rounded-lg border", step.kind === "node" ? "bg-secondary/40" : "ml-4 bg-card sm:ml-8")}>
      <details>
        <summary className="flex cursor-pointer list-none flex-wrap items-center gap-2 px-3 py-2 text-sm">
          <Icon className={cn("size-3.5 shrink-0", step.kind === "llm" ? "text-amber" : "text-teal")} />
          <span className="font-mono text-xs">{step.name}</span>
          {step.provider && (
            <span className="text-xs text-muted-foreground">
              {step.provider} · {step.model}
            </span>
          )}
          {step.prompt_version && <span className="font-mono text-[11px] text-muted-foreground">{step.prompt_version}</span>}
          {step.error && <span className="text-xs text-destructive">error</span>}
          <span className="ml-auto flex gap-3 font-mono text-[11px] text-muted-foreground">
            {step.kind === "llm" && <span>{step.prompt_tokens + step.completion_tokens} tok</span>}
            <span>{step.latency_ms} ms</span>
          </span>
        </summary>
        <div className="grid gap-2 border-t px-3 py-2 sm:grid-cols-2">
          {(["input", "output"] as const).map((k) => (
            <pre key={k} className="max-h-72 overflow-auto rounded bg-background/60 p-2 font-mono text-[11px] leading-relaxed whitespace-pre-wrap text-muted-foreground">
              <span className="text-foreground">{k}</span>
              {"\n"}
              {JSON.stringify(step[k], null, 1)}
              {step.error && k === "output" ? `\n${step.error}` : ""}
            </pre>
          ))}
        </div>
      </details>
    </li>
  );
}

export default function TracePage() {
  const { id } = useParams<{ id: string }>();
  const [run, setRun] = useState<Run | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    getRun(id).then(setRun).catch((e: Error) => setError(e.message));
  }, [id]);

  return (
    <main className="mx-auto flex w-full max-w-4xl flex-1 flex-col gap-5 px-4 py-8">
      <Link href="/traces" className="flex w-fit items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="size-4" /> All runs
      </Link>
      {error && <p className="text-sm text-destructive">{error}</p>}
      {!run && !error && <Skeleton className="h-64 w-full" />}
      {run && (
        <>
          <header className="flex flex-col gap-2">
            <h1 className="text-xl font-semibold">{run.trigger === "scan" ? "Scheduled scan" : run.question}</h1>
            <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
              <StatusText status={run.status} />
              <span>{run.latency_ms != null ? `${(run.latency_ms / 1000).toFixed(1)}s` : ""}</span>
              <span>{run.steps?.filter((s) => s.kind === "llm").length ?? 0} LLM calls</span>
              <span>{run.steps?.filter((s) => s.kind === "tool").length ?? 0} tool calls</span>
              <span>${run.cost_usd.toFixed(4)}</span>
              {run.trace_url && (
                <a href={run.trace_url} target="_blank" rel="noreferrer" className="flex items-center gap-1 hover:text-foreground">
                  Open in LangFuse <ExternalLink className="size-3" />
                </a>
              )}
            </div>
            {run.summary && <p className="text-sm whitespace-pre-wrap">{run.summary}</p>}
          </header>
          <ol className="flex flex-col gap-1.5">
            {grouped(run.steps ?? []).map((s, i) => (
              <StepRow key={i} step={s} />
            ))}
          </ol>
        </>
      )}
    </main>
  );
}
