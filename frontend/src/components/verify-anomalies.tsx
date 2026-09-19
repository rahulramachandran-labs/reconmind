"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { CheckCircle2, CircleAlert, FlaskConical, Loader2 } from "lucide-react";

import { ModelChip, modelOf, templateOf } from "@/components/incident-report";
import { SeverityBadge } from "@/components/severity";
import { listIncidents, type IncidentReport } from "@/lib/api";
import { ANOMALIES, ANOMALY_LABEL, chaosTest, describePlanted, type Planted } from "@/lib/verify";

function newest(reports: IncidentReport[], kind: string) {
  return reports
    .filter((r) => r.finding_type === kind && r.status !== "rejected")
    .sort((a, b) => (b.last_seen_at ?? b.created_at ?? "").localeCompare(a.last_seen_at ?? a.created_at ?? ""))[0];
}

export function VerifyAnomalies({ planted }: { planted: Planted | null }) {
  const [reports, setReports] = useState<IncidentReport[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listIncidents()
      .then(setReports)
      .catch((e: Error) => setError(e.message));
  }, []);

  return (
    <ol className="flex flex-col gap-4">
      {ANOMALIES.map((kind) => {
        const spec = planted?.[kind];
        const report = reports ? newest(reports, kind) : undefined;
        const template = report && templateOf(report);
        const model = report && modelOf(report);
        const test = chaosTest(kind);
        const matches =
          report && spec && report.specialist === spec.expected_agent && report.severity === spec.expected_severity;
        return (
          <li key={kind} className="flex flex-col gap-4 rounded-xl border bg-card p-4">
            <div className="grid gap-4 md:grid-cols-3">
              <div className="flex flex-col gap-1">
                <p className="text-xs text-muted-foreground uppercase">Planted by the generator</p>
                <p className="font-medium">{ANOMALY_LABEL[kind]}</p>
                <p className="text-sm text-muted-foreground">{spec ? describePlanted(kind, spec) : "…"}</p>
                {spec && (
                  <p className="font-mono text-[11px] text-muted-foreground">
                    expected: {String(spec.expected_agent).replace("_", "-")} agent, {String(spec.expected_severity)}
                  </p>
                )}
              </div>
              <div className="flex flex-col gap-1">
                <p className="text-xs text-muted-foreground uppercase">Finding on this deployment</p>
                {!reports && !error && <Loader2 className="size-4 animate-spin text-muted-foreground" />}
                {error && <p className="text-sm text-destructive">{error}</p>}
                {reports && !report && (
                  <p className="text-sm text-muted-foreground">Not found yet. Run a scan from the dashboard.</p>
                )}
                {report && (
                  <>
                    <Link href={`/incidents/${report.id}`} className="flex items-start gap-2 text-sm hover:underline">
                      <SeverityBadge severity={report.severity} />
                      <span>{report.title}</span>
                    </Link>
                    <p className="flex items-center gap-1 font-mono text-[11px]">
                      {matches ? (
                        <CheckCircle2 className="size-3 text-teal" />
                      ) : (
                        <CircleAlert className="size-3 text-amber" />
                      )}
                      {report.specialist.replace("_", "-")} agent, {report.severity},{" "}
                      {report.affected_records.count.toLocaleString()} records
                    </p>
                  </>
                )}
              </div>
              <div className="flex flex-col gap-1">
                <p className="text-xs text-muted-foreground uppercase">Test that proves it</p>
                <a href={test.href} className="flex items-start gap-1.5 font-mono text-[11px] break-all text-teal hover:underline">
                  <FlaskConical className="mt-0.5 size-3 shrink-0" />
                  {test.label}
                </a>
                <p className="text-xs text-muted-foreground">
                  Plants this anomaly alone into a fresh database and fails unless the right agent reports it at the right
                  severity. Runs in CI on every push.
                </p>
              </div>
            </div>
            {report && (
              <div className="grid gap-4 border-t pt-4 md:grid-cols-2">
                <div className="flex flex-col gap-1.5">
                  <p className="text-xs text-muted-foreground uppercase">Root cause, deterministic template</p>
                  <p className="text-sm">{template?.root_cause_hypothesis ?? "Not kept for this report."}</p>
                </div>
                <div className="flex flex-col gap-1.5">
                  <p className="text-xs text-muted-foreground uppercase">Root cause, model analysis</p>
                  {model ? (
                    <>
                      <p className="text-sm">{model.root_cause_hypothesis}</p>
                      <ModelChip w={model} />
                    </>
                  ) : (
                    <p className="text-sm text-muted-foreground">No model write-up yet.</p>
                  )}
                </div>
              </div>
            )}
          </li>
        );
      })}
    </ol>
  );
}
