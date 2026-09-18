"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, CheckCircle2, Loader2, Radar, XCircle } from "lucide-react";

import { ErrorNote } from "@/components/error-note";
import { SeverityBadge, StatusText, ago } from "@/components/severity";
import { Button } from "@/components/ui/button";
import { VolumeChart } from "@/components/volume-chart";
import { getDashboard, getRun, startScan, type Dashboard, type Severity } from "@/lib/api";

function Tile({ label, children, footer }: { label: string; children: React.ReactNode; footer?: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-2 rounded-xl border bg-card p-4">
      <p className="text-xs text-muted-foreground">{label}</p>
      <div className="flex-1">{children}</div>
      {footer && <div className="text-xs text-muted-foreground">{footer}</div>}
    </div>
  );
}

function compact(n: number) {
  return n >= 10_000 ? `${(n / 1000).toFixed(1)}K` : n.toLocaleString();
}

export default function DashboardPage() {
  const [data, setData] = useState<Dashboard | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [scanning, setScanning] = useState(false);

  const load = useCallback(() => {
    getDashboard()
      .then((d) => {
        setData(d);
        setError(null);
      })
      .catch((e: Error) => setError(e.message));
  }, []);
  useEffect(load, [load]);

  async function scan() {
    setScanning(true);
    setError(null);
    try {
      const { run_id } = await startScan();
      for (let i = 0; i < 120; i++) {
        await new Promise((r) => setTimeout(r, 1500));
        if ((await getRun(run_id)).status !== "running") break;
      }
      load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setScanning(false);
    }
  }

  const v = data?.pipeline.volume;
  const run = data?.pipeline.last_run;
  const f = data?.findings;
  const u = data?.usage;
  const openTotal = f ? Object.values(f.by_severity).reduce((a, b) => a + b, 0) : 0;
  const down = (v?.pct_change ?? 0) < 0;

  return (
    <main className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-6 px-4 py-8">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div className="flex flex-col gap-1">
          <h1 className="text-2xl font-semibold">Pipeline health</h1>
          <p className="text-sm text-muted-foreground">
            {data?.pipeline.as_of ? `Business date ${data.pipeline.as_of}, the latest one loaded.` : "Loading the latest business date..."}
            {u?.last_scan && ` Last scan ${ago(u.last_scan.started_at)}.`}
          </p>
        </div>
        <Button onClick={scan} disabled={scanning}>
          {scanning ? <Loader2 className="animate-spin" /> : <Radar />}
          {scanning ? "Scanning..." : "Run a scan"}
        </Button>
      </header>

      {error && (
        <div className="rounded-lg border border-destructive/40 bg-destructive/10 px-4 py-3">
          <ErrorNote message={error.startsWith("Sign in") ? error : `${error}. The API may be waking up on the free tier; try again in 30 seconds.`} />
        </div>
      )}
      {!data && !error && <Loader2 className="size-4 animate-spin text-muted-foreground" />}

      {data && (
        <>
          <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Tile
              label={`Rows loaded ${data.pipeline.as_of ?? ""}`}
              footer={v ? `7-day average ${Math.round(v.trailing_avg_7d).toLocaleString()}` : undefined}
            >
              {v ? (
                <div className="flex items-baseline gap-2">
                  <span className="text-3xl font-semibold">{compact(v.rows)}</span>
                  {v.pct_change != null && (
                    <span className={down ? "text-sm text-red-300" : "text-sm text-teal"}>
                      {v.pct_change > 0 ? "+" : ""}
                      {(v.pct_change * 100).toFixed(1)}%
                    </span>
                  )}
                </div>
              ) : (
                <span className="text-sm text-muted-foreground">No volume data</span>
              )}
            </Tile>
            <Tile
              label="Open findings"
              footer={
                f && f.pending_review > 0 ? (
                  <Link href="/review" className="text-amber hover:underline">
                    {f.pending_review} waiting for review
                  </Link>
                ) : (
                  "nothing waiting for review"
                )
              }
            >
              <div className="flex items-baseline gap-3">
                <span className="text-3xl font-semibold">{openTotal}</span>
                <span className="flex flex-wrap gap-1.5">
                  {(["S1", "S2", "S3", "S4"] as Severity[]).map((s) =>
                    f && f.by_severity[s] > 0 ? (
                      <span key={s} className="flex items-center gap-1 text-xs">
                        <SeverityBadge severity={s} /> {f.by_severity[s]}
                      </span>
                    ) : null,
                  )}
                </span>
              </div>
            </Tile>
            <Tile
              label="Last pipeline run"
              footer={run ? `${run.runs_failed_14d} failed run${run.runs_failed_14d === 1 ? "" : "s"} in the last 14` : undefined}
            >
              {run ? (
                <div className="flex flex-col gap-1">
                  <span className="flex items-center gap-1.5 text-lg font-semibold">
                    {run.state === "success" ? (
                      <CheckCircle2 className="size-4 text-teal" />
                    ) : run.state === "failed" ? (
                      <XCircle className="size-4 text-red-300" />
                    ) : (
                      <AlertTriangle className="size-4 text-amber" />
                    )}
                    {run.state}
                  </span>
                  <span className="text-xs text-muted-foreground">
                    {run.business_date} · {Math.round(run.duration_s / 60)} min
                    {run.failed_tasks.length > 0 && ` · failed: ${run.failed_tasks.join(", ")}`}
                  </span>
                </div>
              ) : (
                <span className="text-sm text-muted-foreground">No runs</span>
              )}
            </Tile>
            <Tile label="Model usage today (UTC)" footer={u ? `${u.runs} agent run${u.runs === 1 ? "" : "s"}, ${u.llm_calls} LLM calls` : undefined}>
              {u && (
                <div className="flex flex-col gap-1">
                  <span className="text-3xl font-semibold">${u.cost_usd.toFixed(u.cost_usd < 1 ? 4 : 2)}</span>
                  <span className="text-xs text-muted-foreground">
                    {u.providers.length
                      ? u.providers.map((p) => `${p.provider} ${p.calls}`).join(" · ")
                      : "no model calls: answers came from templates and the runbooks"}
                  </span>
                </div>
              )}
            </Tile>
          </section>

          {v && v.series.length > 0 && (
            <section className="rounded-xl border bg-card p-4">
              <h2 className="mb-2 text-sm font-medium">Daily volume, last 14 business days</h2>
              <VolumeChart series={v.series} average={v.trailing_avg_7d} />
            </section>
          )}

          <section className="flex flex-col gap-3">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-medium">Latest findings</h2>
              <Link href="/incidents" className="text-xs text-muted-foreground hover:text-foreground">
                Incident feed
              </Link>
            </div>
            {f && f.items.length === 0 && (
              <p className="text-sm text-muted-foreground">No findings yet. Run a scan to have the agents look.</p>
            )}
            <ul className="flex flex-col divide-y rounded-xl border bg-card">
              {f?.items.map((item) => (
                <li key={item.id} className="flex items-center gap-3 px-4 py-2.5">
                  <SeverityBadge severity={item.severity} />
                  <span className="min-w-0 flex-1 truncate text-sm">{item.title}</span>
                  <StatusText status={item.status} />
                </li>
              ))}
            </ul>
          </section>
        </>
      )}
    </main>
  );
}
