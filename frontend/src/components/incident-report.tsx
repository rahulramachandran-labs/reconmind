"use client";

import Link from "next/link";
import { useState } from "react";
import { Cpu, ExternalLink, ListChecks, Loader2, Sparkles } from "lucide-react";

import { SeverityBadge, StatusText, ago } from "@/components/severity";
import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { regenerateReport, SignInRequired, type IncidentReport, type ModelWriteUp, type WriteUp } from "@/lib/api";
import { useSignedIn } from "@/lib/session";

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="flex flex-col gap-1.5">
      <h3 className="text-xs font-medium tracking-wide text-muted-foreground uppercase">{title}</h3>
      <div className="text-sm leading-relaxed">{children}</div>
    </section>
  );
}

function pick(r: IncidentReport): WriteUp {
  return {
    problem_statement: r.problem_statement,
    root_cause_hypothesis: r.root_cause_hypothesis,
    recommended_fix: r.recommended_fix,
    open_questions: r.open_questions,
    confidence: r.confidence,
  };
}

/** The template write-up. Reports from before both versions were stored carry it at the top level. */
export function templateOf(r: IncidentReport): WriteUp | null {
  return r.template ?? (r.analysis_by === "template" ? pick(r) : null);
}

/** The model write-up. Older reports that a model wrote at scan time have no usage figures. */
export function modelOf(r: IncidentReport): ModelWriteUp | null {
  if (r.model_analysis) return r.model_analysis;
  if (r.analysis_by === "template" || r.analysis_by === "model") return null;
  return { ...pick(r), provider: r.analysis_by, model: null, latency_ms: 0, prompt_tokens: 0, completion_tokens: 0, cost_usd: 0 };
}

export function usd(n: number) {
  return `$${n.toFixed(n > 0 && n < 0.01 ? 5 : n < 1 ? 4 : 2)}`;
}

export function ModelChip({ w }: { w: ModelWriteUp }) {
  const tokens = w.prompt_tokens + w.completion_tokens;
  return (
    <p className="flex flex-wrap items-center gap-x-2 gap-y-1 rounded-md border border-teal/30 bg-teal/5 px-2.5 py-1.5 font-mono text-[11px]">
      <Sparkles className="size-3 text-teal" />
      <span className="text-foreground">
        {w.provider}
        {w.model && ` · ${w.model}`}
      </span>
      {w.latency_ms > 0 && <span className="text-muted-foreground">{(w.latency_ms / 1000).toFixed(1)}s</span>}
      {tokens > 0 && <span className="text-muted-foreground">{tokens.toLocaleString()} tokens</span>}
      {tokens > 0 && <span className="text-muted-foreground">{usd(w.cost_usd)}</span>}
      {w.generated_at && <span className="text-muted-foreground">written {ago(w.generated_at)}</span>}
    </p>
  );
}

function TemplateChip() {
  return (
    <p className="flex items-center gap-2 rounded-md border px-2.5 py-1.5 font-mono text-[11px] text-muted-foreground">
      <ListChecks className="size-3" />
      deterministic checks · adapter templates · no model
    </p>
  );
}

function WriteUpView({ w, chip }: { w: WriteUp; chip: React.ReactNode }) {
  const pct = Math.round(w.confidence * 100);
  return (
    <div className="flex min-w-0 flex-col gap-4">
      {chip}
      <Section title="Problem">{w.problem_statement}</Section>
      <Section title="Confidence in root cause">
        <div className="flex items-center gap-2">
          <div className="h-1.5 w-32 overflow-hidden rounded-full bg-secondary">
            <div className="h-full rounded-full bg-teal" style={{ width: `${pct}%` }} />
          </div>
          <span className="font-mono text-xs">{pct}%</span>
        </div>
      </Section>
      <Section title="Root-cause hypothesis">{w.root_cause_hypothesis}</Section>
      <Section title="Recommended fix">
        <ol className="list-decimal space-y-1 pl-5">
          {w.recommended_fix.map((s, i) => (
            <li key={i}>{s}</li>
          ))}
        </ol>
      </Section>
      {w.open_questions.length > 0 && (
        <Section title="Open questions">
          <ul className="list-disc space-y-1 pl-5">
            {w.open_questions.map((q, i) => (
              <li key={i}>{q}</li>
            ))}
          </ul>
        </Section>
      )}
    </div>
  );
}

function NoModelWriteUp({ report, onWritten }: { report: IncidentReport; onWritten: (r: IncidentReport) => void }) {
  const signedIn = useSignedIn();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function write() {
    setBusy(true);
    setError(null);
    try {
      onWritten(await regenerateReport(report.id));
    } catch (e) {
      setError(e instanceof SignInRequired ? "Sign in as the demo reviewer first." : (e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col items-start gap-3 rounded-md border border-dashed px-4 py-3 text-sm text-muted-foreground">
      <p>
        {report.model_error
          ? "A model was asked and its reply was not used. The facts and the template write-up come from deterministic checks; the model only adds its own reading of them."
          : "No model has written this one up yet. The facts and the template write-up come from deterministic checks; a model adds its own reading of the same facts."}
      </p>
      {report.model_error && (
        <p className="font-mono text-[11px] break-words text-amber">{report.model_error}</p>
      )}
      {signedIn ? (
        <Button size="sm" variant="secondary" onClick={write} disabled={busy}>
          {busy ? <Loader2 className="animate-spin" /> : <Sparkles />} Write it up with the model
        </Button>
      ) : (
        signedIn === false && (
          <Link href="/signin?callbackUrl=/incidents" className="text-xs text-amber hover:underline">
            Sign in as demo reviewer to ask the model for a write-up
          </Link>
        )
      )}
      {error && <p className="text-xs text-destructive">{error}</p>}
    </div>
  );
}

type View = "checks" | "model" | "both";

export function ReportBody({ report: initial }: { report: IncidentReport }) {
  const [report, setReport] = useState(initial);
  const template = templateOf(report);
  const model = modelOf(report);
  const [view, setView] = useState<View>(model ? "model" : "checks");

  const checksView = template ? (
    <WriteUpView w={template} chip={<TemplateChip />} />
  ) : (
    <p className="text-sm text-muted-foreground">This report was written before template write-ups were kept alongside.</p>
  );
  const modelView = model ? (
    <WriteUpView w={model} chip={<ModelChip w={model} />} />
  ) : (
    <NoModelWriteUp report={report} onWritten={setReport} />
  );

  return (
    <div className="flex flex-col gap-5">
      <Tabs value={view} onValueChange={(v) => setView(v as View)}>
        <TabsList>
          <TabsTrigger value="checks">
            <Cpu className="size-3.5" /> Deterministic checks
          </TabsTrigger>
          <TabsTrigger value="model">
            <Sparkles className="size-3.5" /> Model analysis
          </TabsTrigger>
          {model && template && (
            <TabsTrigger value="both" className="hidden sm:inline-flex">
              Side by side
            </TabsTrigger>
          )}
        </TabsList>
      </Tabs>
      {view === "checks" && checksView}
      {view === "model" && modelView}
      {view === "both" && (
        <div className="grid gap-6 lg:grid-cols-2">
          {checksView}
          {modelView}
        </div>
      )}
      <Section title="Affected records">
        <span className="font-mono text-lg">{report.affected_records.count.toLocaleString()}</span>{" "}
        <span className="text-muted-foreground">{report.affected_records.detail.replace(/^\d+ records/, "")}</span>
        <span className="ml-2 text-xs text-muted-foreground">measured by the checks, the same in both write-ups</span>
      </Section>
      <Section title="Evidence">
        <ul className="flex flex-col gap-2">
          {report.evidence.map((e, i) => (
            <li key={i} className="rounded-md border bg-background/40 px-3 py-2">
              <p className="font-mono text-[11px] text-teal">{e.source}</p>
              <p className="mt-0.5 text-xs text-muted-foreground">{e.summary}</p>
            </li>
          ))}
        </ul>
      </Section>
      {report.sources.length > 0 && (
        <Section title="Runbooks and past incidents consulted">
          <ul className="flex flex-wrap gap-2">
            {report.sources.map((s) => (
              <li key={s.chunk_id}>
                <Link
                  href={`/docs/${s.doc_id}`}
                  className="inline-block rounded-md border px-2 py-1 text-xs hover:border-teal/60"
                >
                  {s.title} <span className="text-muted-foreground">· {s.section}</span>
                </Link>
              </li>
            ))}
          </ul>
        </Section>
      )}
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-t pt-3 text-xs text-muted-foreground">
        <span>{report.specialist.replace("_", "-")} agent</span>
        {report.review_note && <span>reviewer note: {report.review_note}</span>}
        <Link href={`/incidents/${report.id}`} className="hover:text-foreground">
          permalink
        </Link>
        <Link href={`/traces/${report.run_id}`} className="hover:text-foreground">
          run trace
        </Link>
        {report.trace_url && (
          <a href={report.trace_url} target="_blank" rel="noreferrer" className="flex items-center gap-1 hover:text-foreground">
            LangFuse <ExternalLink className="size-3" />
          </a>
        )}
      </div>
    </div>
  );
}

export function ReportSummary({ report }: { report: IncidentReport }) {
  const model = modelOf(report);
  return (
    <div className="flex min-w-0 flex-1 flex-wrap items-center gap-x-3 gap-y-1">
      <SeverityBadge severity={report.severity} />
      <span className="min-w-0 flex-1 truncate text-sm font-medium">{report.title}</span>
      <span className="font-mono text-[11px] text-muted-foreground">{report.finding_type}</span>
      <span className="font-mono text-[11px] text-muted-foreground">{model ? model.provider : "template only"}</span>
      {(report.seen_count ?? 1) > 1 && (
        <span className="text-[11px] text-muted-foreground" title={report.last_seen_at ? `last seen ${ago(report.last_seen_at)}` : undefined}>
          seen by {report.seen_count} scans
        </span>
      )}
      <StatusText status={report.status} />
    </div>
  );
}
