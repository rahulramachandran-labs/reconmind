"use client";

import { useCallback, useEffect, useState } from "react";
import { Loader2, Radar } from "lucide-react";

import { ReportBody, ReportSummary } from "@/components/incident-report";
import { Button } from "@/components/ui/button";
import { getRun, listIncidents, startScan, type IncidentReport } from "@/lib/api";
import { cn } from "@/lib/utils";

const SEVERITIES = ["", "S1", "S2", "S3", "S4"];
const STATUSES = ["", "pending_review", "published", "rejected"];

export default function IncidentsPage() {
  const [items, setItems] = useState<IncidentReport[] | null>(null);
  const [severity, setSeverity] = useState("");
  const [status, setStatus] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [scanning, setScanning] = useState<string | null>(null);

  const load = useCallback(() => {
    listIncidents({ severity, status })
      .then((r) => {
        setItems(r);
        setError(null);
      })
      .catch((e: Error) => setError(e.message));
  }, [severity, status]);

  useEffect(load, [load]);

  async function scan() {
    setError(null);
    try {
      const { run_id } = await startScan();
      setScanning(run_id);
      for (let i = 0; i < 120; i++) {
        await new Promise((r) => setTimeout(r, 1500));
        const run = await getRun(run_id);
        if (run.status !== "running") break;
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setScanning(null);
      load();
    }
  }

  return (
    <main className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-6 px-4 py-8">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div className="flex flex-col gap-1">
          <h1 className="text-2xl font-semibold">Incident feed</h1>
          <p className="text-sm text-muted-foreground">
            Every finding the agents have written up. Open one for the full report.
          </p>
        </div>
        <Button onClick={scan} disabled={!!scanning}>
          {scanning ? <Loader2 className="animate-spin" /> : <Radar />}
          {scanning ? "Scanning..." : "Run a scan"}
        </Button>
      </header>

      <div className="flex flex-wrap gap-2 text-xs">
        {SEVERITIES.map((s) => (
          <button
            key={s || "all-sev"}
            onClick={() => setSeverity(s)}
            className={cn("rounded-full border px-3 py-1", severity === s ? "border-amber text-foreground" : "text-muted-foreground")}
          >
            {s || "all severities"}
          </button>
        ))}
        <span className="mx-1 border-l" />
        {STATUSES.map((s) => (
          <button
            key={s || "all-status"}
            onClick={() => setStatus(s)}
            className={cn("rounded-full border px-3 py-1", status === s ? "border-teal text-foreground" : "text-muted-foreground")}
          >
            {s ? s.replace("_", " ") : "any status"}
          </button>
        ))}
      </div>

      {error && (
        <p className="rounded-lg border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm">
          {error}. The API may be waking up on the free tier; try again in a few seconds.
        </p>
      )}
      {!items && !error && <Loader2 className="size-4 animate-spin text-muted-foreground" />}
      {items?.length === 0 && (
        <p className="text-sm text-muted-foreground">No findings yet. Run a scan to have the agents look.</p>
      )}
      <ul className="flex flex-col gap-3">
        {items?.map((r) => (
          <li key={r.id}>
            <details className="group rounded-xl border bg-card">
              <summary className="flex cursor-pointer list-none items-center gap-3 px-4 py-3">
                <ReportSummary report={r} />
              </summary>
              <div className="border-t px-4 py-4">
                <ReportBody report={r} />
              </div>
            </details>
          </li>
        ))}
      </ul>
    </main>
  );
}
