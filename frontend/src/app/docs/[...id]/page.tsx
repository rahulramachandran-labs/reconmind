"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { ArrowLeft } from "lucide-react";

import { Markdown } from "@/components/markdown";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { getDoc, type CorpusDocBody } from "@/lib/api";

export default function DocPage() {
  const params = useParams<{ id: string[] }>();
  const docId = params.id.map(decodeURIComponent).join("/");
  const [doc, setDoc] = useState<CorpusDocBody | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getDoc(docId).then(setDoc).catch((e: Error) => setError(e.message));
  }, [docId]);

  return (
    <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-4 px-4 py-8">
      <Link
        href="/docs"
        className="flex w-fit items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="size-4" /> All documents
      </Link>
      {error && <p className="text-sm text-destructive">{error}</p>}
      {!doc && !error && <Skeleton className="h-64 w-full" />}
      {doc && (
        <article className="flex flex-col gap-2">
          <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
            <Badge variant="secondary">{doc.doc_type}</Badge>
            <span className="font-mono">{doc.path}</span>
          </div>
          <Markdown>{doc.body}</Markdown>
        </article>
      )}
    </main>
  );
}
