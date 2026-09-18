"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ExternalLink, Loader2 } from "lucide-react";

import { StatusText, ago } from "@/components/severity";
import { listRuns, type Run } from "@/lib/api";

export default function TracesPage() {
  const [runs, setRuns] = useState<Run[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    listRuns().then(setRuns).catch((e: Error) => setError(e.message));
  }, []);

  return (
    <main className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-6 px-4 py-8">
      <header className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold">Traces</h1>
        <p className="text-sm text-muted-foreground">
          Every agent run, with what it cost and how long it took. Each step of a run is recorded
          here; runs also link to LangFuse when it is configured.
        </p>
      </header>
      {error && <p className="text-sm text-destructive">{error}</p>}
      {!runs && !error && <Loader2 className="size-4 animate-spin text-muted-foreground" />}
      {runs && (
        <div className="overflow-x-auto rounded-xl border">
          <table className="w-full min-w-[720px] text-sm">
            <thead className="bg-secondary/50 text-left text-xs text-muted-foreground">
              <tr>
                <th className="px-3 py-2 font-medium">Started</th>
                <th className="px-3 py-2 font-medium">Trigger</th>
                <th className="px-3 py-2 font-medium">Status</th>
                <th className="px-3 py-2 text-right font-medium">Latency</th>
                <th className="px-3 py-2 text-right font-medium">LLM calls</th>
                <th className="px-3 py-2 text-right font-medium">Tokens</th>
                <th className="px-3 py-2 text-right font-medium">Cost</th>
                <th className="px-3 py-2" />
              </tr>
            </thead>
            <tbody>
              {runs.map((r) => (
                <tr key={r.id} className="border-t hover:bg-secondary/30">
                  <td className="px-3 py-2 whitespace-nowrap text-muted-foreground">{ago(r.started_at)}</td>
                  <td className="max-w-72 truncate px-3 py-2">
                    <Link href={`/traces/${r.id}`} className="hover:underline">
                      {r.trigger === "scan" ? "scheduled scan" : r.question}
                    </Link>
                  </td>
                  <td className="px-3 py-2">
                    <StatusText status={r.status} />
                  </td>
                  <td className="px-3 py-2 text-right font-mono text-xs">
                    {r.latency_ms != null ? `${(r.latency_ms / 1000).toFixed(1)}s` : ""}
                  </td>
                  <td className="px-3 py-2 text-right font-mono text-xs">{r.llm_calls ?? 0}</td>
                  <td className="px-3 py-2 text-right font-mono text-xs">
                    {(r.prompt_tokens + r.completion_tokens).toLocaleString()}
                  </td>
                  <td className="px-3 py-2 text-right font-mono text-xs">${r.cost_usd.toFixed(4)}</td>
                  <td className="px-3 py-2 text-right">
                    {r.trace_url && (
                      <a href={r.trace_url} target="_blank" rel="noreferrer" className="text-muted-foreground hover:text-foreground">
                        <ExternalLink className="size-3.5" />
                      </a>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </main>
  );
}
