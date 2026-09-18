import Link from "next/link";
import { ExternalLink } from "lucide-react";

import { SeverityBadge, StatusText } from "@/components/severity";
import type { IncidentReport } from "@/lib/api";

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="flex flex-col gap-1.5">
      <h3 className="text-xs font-medium tracking-wide text-muted-foreground uppercase">{title}</h3>
      <div className="text-sm leading-relaxed">{children}</div>
    </section>
  );
}

export function ReportBody({ report }: { report: IncidentReport }) {
  const pct = Math.round(report.confidence * 100);
  return (
    <div className="flex flex-col gap-5">
      <Section title="Problem">{report.problem_statement}</Section>
      <div className="grid gap-5 sm:grid-cols-2">
        <Section title="Affected records">
          <span className="font-mono text-lg">{report.affected_records.count.toLocaleString()}</span>{" "}
          <span className="text-muted-foreground">{report.affected_records.detail.replace(/^\d+ records/, "")}</span>
        </Section>
        <Section title="Confidence in root cause">
          <div className="flex items-center gap-2">
            <div className="h-1.5 w-32 overflow-hidden rounded-full bg-secondary">
              <div className="h-full rounded-full bg-teal" style={{ width: `${pct}%` }} />
            </div>
            <span className="font-mono text-xs">{pct}%</span>
            <span className="text-xs text-muted-foreground">{report.confidence_label}</span>
          </div>
        </Section>
      </div>
      <Section title="Root-cause hypothesis">{report.root_cause_hypothesis}</Section>
      <Section title="Recommended fix">
        <ol className="list-decimal space-y-1 pl-5">
          {report.recommended_fix.map((s, i) => (
            <li key={i}>{s}</li>
          ))}
        </ol>
      </Section>
      {report.open_questions.length > 0 && (
        <Section title="Open questions">
          <ul className="list-disc space-y-1 pl-5">
            {report.open_questions.map((q, i) => (
              <li key={i}>{q}</li>
            ))}
          </ul>
        </Section>
      )}
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
        <span>
          written by <span className="font-mono">{report.analysis_by}</span>
        </span>
        <span>{report.specialist.replace("_", "-")} agent</span>
        {report.review_note && <span>reviewer note: {report.review_note}</span>}
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
  return (
    <div className="flex min-w-0 flex-1 flex-wrap items-center gap-x-3 gap-y-1">
      <SeverityBadge severity={report.severity} />
      <span className="min-w-0 flex-1 truncate text-sm font-medium">{report.title}</span>
      <span className="font-mono text-[11px] text-muted-foreground">{report.finding_type}</span>
      <StatusText status={report.status} />
    </div>
  );
}
