"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { FileText, Loader2, Search } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { listCorpus, search, type CorpusDoc, type SearchMode, type Source } from "@/lib/api";

const TYPE_LABEL: Record<string, string> = {
  runbook: "Runbooks",
  incident: "Past incidents",
  schema: "Schema docs",
  dbt_model: "dbt models",
};

const MODE_HELP: Record<SearchMode, string> = {
  hybrid: "BM25 and dense results fused with reciprocal rank fusion",
  dense: "embeddings only (the Phase A baseline)",
  bm25: "keyword only",
};

export function DocsBrowser() {
  const router = useRouter();
  const params = useSearchParams();
  const [q, setQ] = useState(params.get("q") ?? "");
  const [mode, setMode] = useState<SearchMode>((params.get("mode") as SearchMode) ?? "hybrid");
  const [docs, setDocs] = useState<CorpusDoc[]>([]);
  const [hits, setHits] = useState<Source[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listCorpus().then(setDocs).catch((e: Error) => setError(e.message));
  }, []);

  useEffect(() => {
    const query = q.trim();
    const t = setTimeout(() => {
      const next = new URLSearchParams();
      if (query) next.set("q", query);
      if (mode !== "hybrid") next.set("mode", mode);
      router.replace(`/docs${next.size ? `?${next}` : ""}`, { scroll: false });
      if (query.length < 2) {
        setHits(null);
        return;
      }
      setLoading(true);
      search(query, mode)
        .then((r) => {
          setHits(r);
          setError(null);
        })
        .catch((e: Error) => setError(e.message))
        .finally(() => setLoading(false));
    }, 250);
    return () => clearTimeout(t);
  }, [q, mode, router]);

  const grouped = useMemo(() => {
    const out: Record<string, CorpusDoc[]> = {};
    for (const d of docs) (out[d.doc_type] ??= []).push(d);
    return out;
  }, [docs]);

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <div className="relative flex-1">
          <Search className="absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search runbooks, schema docs, dbt models, past incidents..."
            className="pl-9"
          />
        </div>
        <Tabs value={mode} onValueChange={(v) => setMode(v as SearchMode)}>
          <TabsList>
            <TabsTrigger value="hybrid">Hybrid</TabsTrigger>
            <TabsTrigger value="dense">Dense</TabsTrigger>
            <TabsTrigger value="bm25">BM25</TabsTrigger>
          </TabsList>
        </Tabs>
      </div>
      <p className="-mt-3 text-xs text-muted-foreground">{MODE_HELP[mode]}</p>

      {error && (
        <p className="rounded-lg border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm">
          {error}. The API may be waking up on the free tier; try again in a few seconds.
        </p>
      )}

      {loading && <Loader2 className="size-4 animate-spin text-muted-foreground" />}

      {hits && !loading && (
        <ol className="flex flex-col gap-3">
          {hits.length === 0 && <p className="text-sm text-muted-foreground">No matches.</p>}
          {hits.map((h) => (
            <li key={h.chunk_id} className="rounded-lg border bg-card p-4">
              <div className="flex flex-wrap items-center gap-2 text-sm">
                <span className="font-mono text-xs text-amber">#{h.rank}</span>
                <Link href={`/docs/${h.doc_id}`} className="font-medium hover:underline">
                  {h.title}
                </Link>
                <span className="text-muted-foreground">· {h.section}</span>
                <span className="ml-auto flex gap-1">
                  {h.dense_rank != null && (
                    <Badge variant="outline" className="font-mono">dense {h.dense_rank}</Badge>
                  )}
                  {h.bm25_rank != null && (
                    <Badge variant="outline" className="font-mono">bm25 {h.bm25_rank}</Badge>
                  )}
                  <Badge variant="secondary">{h.doc_type}</Badge>
                </span>
              </div>
              <p className="mt-2 line-clamp-4 font-mono text-xs leading-relaxed whitespace-pre-wrap text-muted-foreground">
                {h.text.split("\n").slice(1).join("\n")}
              </p>
            </li>
          ))}
        </ol>
      )}

      {!hits && (
        <div className="grid gap-6 sm:grid-cols-2">
          {Object.entries(grouped).map(([type, list]) => (
            <section key={type} className="flex flex-col gap-2">
              <h2 className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
                {TYPE_LABEL[type] ?? type} <span className="text-foreground/50">({list.length})</span>
              </h2>
              <ul className="flex flex-col">
                {list.map((d) => (
                  <li key={d.doc_id}>
                    <Link
                      href={`/docs/${d.doc_id}`}
                      className="flex items-center gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-secondary"
                    >
                      <FileText className="size-3.5 shrink-0 text-teal" />
                      <span className="truncate">{d.title}</span>
                    </Link>
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
      )}
    </div>
  );
}
