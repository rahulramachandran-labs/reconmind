"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { ArrowLeft, Loader2 } from "lucide-react";

import { ErrorNote } from "@/components/error-note";
import { ReportBody, ReportSummary } from "@/components/incident-report";
import { getIncident, type IncidentReport } from "@/lib/api";

export default function IncidentPage() {
  const { id } = useParams<{ id: string }>();
  const [report, setReport] = useState<IncidentReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getIncident(id)
      .then(setReport)
      .catch((e: Error) => setError(e.message));
  }, [id]);

  return (
    <main className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-6 px-4 py-8">
      <Link href="/incidents" className="flex w-fit items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
        <ArrowLeft className="size-3" /> Incident feed
      </Link>
      {error && <ErrorNote message={error} />}
      {!report && !error && <Loader2 className="size-4 animate-spin text-muted-foreground" />}
      {report && (
        <article className="flex flex-col gap-5 rounded-xl border bg-card p-5">
          <ReportSummary report={report} />
          <ReportBody report={report} />
        </article>
      )}
    </main>
  );
}
