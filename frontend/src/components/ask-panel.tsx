"use client";

import { useRef, useState } from "react";
import { ArrowUp, FileText, Loader2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { ask, type Answer } from "@/lib/api";

const EXAMPLES = [
  "Which file wins when a submitter resends the same day?",
  "How do I tell a renamed column from a dropped one?",
  "One store is reporting under two outlet ids. What do I check first?",
  "What severity is a volume drop of 40%?",
];

export function AskPanel() {
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const inflight = useRef<AbortController | null>(null);

  async function submit(q: string) {
    const text = q.trim();
    if (text.length < 3 || loading) return;
    inflight.current?.abort();
    const ctrl = new AbortController();
    inflight.current = ctrl;
    setLoading(true);
    setError(null);
    try {
      setAnswer(await ask(text, ctrl.signal));
    } catch (e) {
      if ((e as Error).name !== "AbortError") {
        setError(
          `${(e as Error).message}. The API may be waking up on the free tier; give it 30 seconds and try again.`,
        );
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <form
        className="relative"
        onSubmit={(e) => {
          e.preventDefault();
          submit(question);
        }}
      >
        <Textarea
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit(question);
            }
          }}
          placeholder="Ask about a pipeline incident, a runbook, or a past write-up..."
          className="min-h-28 resize-none pr-14 text-base"
          maxLength={1000}
        />
        <Button
          type="submit"
          size="icon"
          className="absolute right-3 bottom-3"
          disabled={loading || question.trim().length < 3}
          aria-label="Ask"
        >
          {loading ? <Loader2 className="animate-spin" /> : <ArrowUp />}
        </Button>
      </form>

      <div className="flex flex-wrap gap-2">
        {EXAMPLES.map((ex) => (
          <button
            key={ex}
            type="button"
            onClick={() => {
              setQuestion(ex);
              submit(ex);
            }}
            className="rounded-full border px-3 py-1 text-xs text-muted-foreground transition-colors hover:border-amber/60 hover:text-foreground"
          >
            {ex}
          </button>
        ))}
      </div>

      {error && (
        <p className="rounded-lg border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm">
          {error}
        </p>
      )}

      {answer && (
        <Card>
          <CardHeader className="flex flex-row items-center justify-between gap-2">
            <CardTitle className="text-base">Answer</CardTitle>
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <Badge variant="outline" className="font-mono">
                {answer.provider}
                {answer.model && answer.model !== "none" ? ` · ${answer.model}` : ""}
              </Badge>
              <span>{(answer.latency_ms / 1000).toFixed(1)}s</span>
            </div>
          </CardHeader>
          <CardContent className="flex flex-col gap-5">
            <div className="whitespace-pre-wrap leading-relaxed">{answer.answer}</div>
            <div className="flex flex-col gap-2">
              <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
                Sources
              </p>
              <ol className="flex flex-col gap-2">
                {answer.sources.map((s, i) => (
                  <li key={s.chunk_id}>
                    <details className="group rounded-lg border bg-background/40 px-3 py-2">
                      <summary className="flex cursor-pointer list-none items-center gap-2 text-sm">
                        <span className="font-mono text-xs text-amber">[{i + 1}]</span>
                        <FileText className="size-3.5 shrink-0 text-teal" />
                        <span className="truncate">{s.title}</span>
                        <span className="hidden truncate text-muted-foreground sm:inline">
                          · {s.section}
                        </span>
                        <Badge variant="secondary" className="ml-auto shrink-0">
                          {s.doc_type}
                        </Badge>
                      </summary>
                      <pre className="mt-2 font-mono text-xs leading-relaxed whitespace-pre-wrap text-muted-foreground">
                        {s.text}
                      </pre>
                    </details>
                  </li>
                ))}
              </ol>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
