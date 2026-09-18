"use client";

import { useCallback, useEffect, useState } from "react";
import { Check, Loader2, MessageSquarePlus, X } from "lucide-react";

import { ErrorNote } from "@/components/error-note";
import { ReportBody, ReportSummary } from "@/components/incident-report";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { reviewPlan, reviewQueue, reviewReport, type IncidentReport, type PausedPlan } from "@/lib/api";

function ReportItem({ report, onDone }: { report: IncidentReport; onDone: () => void }) {
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function decide(decision: "approve" | "reject" | "annotate") {
    if (decision === "annotate" && !note.trim()) {
      setError("Write the note first.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await reviewReport(report.id, decision, note);
      onDone();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <li className="rounded-xl border bg-card">
      <div className="flex flex-col gap-2 px-4 py-3">
        <ReportSummary report={report} />
        {report.review_reason && <p className="text-xs text-amber">Why it paused: {report.review_reason}</p>}
      </div>
      <details className="border-t">
        <summary className="cursor-pointer px-4 py-2 text-xs text-muted-foreground">Read the full write-up</summary>
        <div className="px-4 pb-4">
          <ReportBody report={report} />
        </div>
      </details>
      <div className="flex flex-col gap-3 border-t px-4 py-3">
        <Textarea
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder="Optional note for the write-up (required to annotate)"
          className="min-h-16 text-sm"
          maxLength={2000}
        />
        <div className="flex flex-wrap gap-2">
          <Button size="sm" onClick={() => decide("approve")} disabled={busy}>
            {busy ? <Loader2 className="animate-spin" /> : <Check />} Approve
          </Button>
          <Button size="sm" variant="secondary" onClick={() => decide("annotate")} disabled={busy}>
            <MessageSquarePlus /> Approve with note
          </Button>
          <Button size="sm" variant="outline" onClick={() => decide("reject")} disabled={busy}>
            <X /> Reject
          </Button>
        </div>
        {error && <ErrorNote message={error} />}
      </div>
    </li>
  );
}

function PlanItem({ run, onDone }: { run: PausedPlan; onDone: () => void }) {
  const [busy, setBusy] = useState(false);
  const options = ["reconciliation", "data_quality"];
  const [picked, setPicked] = useState<string[]>(run.plan.specialists ?? []);
  const [error, setError] = useState<string | null>(null);
  async function decide(decision: "approve" | "reject") {
    setBusy(true);
    setError(null);
    try {
      await reviewPlan(run.id, decision, picked);
      onDone();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <li className="flex flex-col gap-3 rounded-xl border bg-card px-4 py-3">
      <p className="text-sm">&ldquo;{run.question}&rdquo;</p>
      <p className="text-xs text-amber">
        Planner confidence {Math.round(run.plan.confidence * 100)}%: {run.plan.rationale}
      </p>
      <div className="flex flex-wrap gap-3 text-xs">
        {options.map((o) => (
          <label key={o} className="flex items-center gap-1.5">
            <input
              type="checkbox"
              checked={picked.includes(o)}
              onChange={(e) => setPicked((p) => (e.target.checked ? [...p, o] : p.filter((x) => x !== o)))}
            />
            {o.replace("_", "-")}
          </label>
        ))}
      </div>
      <div className="flex gap-2">
        <Button size="sm" onClick={() => decide("approve")} disabled={busy}>
          Investigate {picked.length ? "with these" : "(answer from runbooks)"}
        </Button>
        <Button size="sm" variant="outline" onClick={() => decide("reject")} disabled={busy}>
          Drop it
        </Button>
      </div>
      {error && <ErrorNote message={error} />}
    </li>
  );
}

export default function ReviewPage() {
  const [queue, setQueue] = useState<{ reports: IncidentReport[]; plans: PausedPlan[] } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(() => {
    reviewQueue()
      .then((q) => {
        setQueue(q);
        setError(null);
      })
      .catch((e: Error) => setError(e.message));
  }, []);
  useEffect(load, [load]);

  const empty = queue && queue.reports.length === 0 && queue.plans.length === 0;
  return (
    <main className="mx-auto flex w-full max-w-4xl flex-1 flex-col gap-6 px-4 py-8">
      <header className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold">Review queue</h1>
        <p className="text-sm text-muted-foreground">
          The graph stops here instead of guessing: every S1 finding, anything the agents are not
          confident about, and questions the planner could not route. Your decision resumes the run
          and goes into the audit ledger.
        </p>
      </header>
      {error && <p className="text-sm text-destructive">{error}</p>}
      {!queue && !error && <Loader2 className="size-4 animate-spin text-muted-foreground" />}
      {empty && <p className="text-sm text-muted-foreground">Nothing waiting. Scans will stop here when they need you.</p>}
      {queue && queue.plans.length > 0 && (
        <section className="flex flex-col gap-3">
          <h2 className="text-xs font-medium tracking-wide text-muted-foreground uppercase">Questions to route</h2>
          <ul className="flex flex-col gap-3">
            {queue.plans.map((p) => (
              <PlanItem key={p.id} run={p} onDone={load} />
            ))}
          </ul>
        </section>
      )}
      {queue && queue.reports.length > 0 && (
        <section className="flex flex-col gap-3">
          <h2 className="text-xs font-medium tracking-wide text-muted-foreground uppercase">Findings to sign off</h2>
          <ul className="flex flex-col gap-3">
            {queue.reports.map((r) => (
              <ReportItem key={r.id} report={r} onDone={load} />
            ))}
          </ul>
        </section>
      )}
    </main>
  );
}
