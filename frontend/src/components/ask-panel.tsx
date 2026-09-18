"use client";

import { useEffect, useRef, useState } from "react";
import { ArrowUp, FileText, Loader2, RotateCcw } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { ask, type Answer } from "@/lib/api";

const EXAMPLES = [
  "Which file wins when a submitter resends the same day?",
  "How do I tell a renamed column from a dropped one?",
  "One store is reporting under two outlet ids. What do I check first?",
  "What severity is a volume drop of 40%?",
];

type Turn = { question: string; answer?: Answer; error?: string };

function Sources({ answer }: { answer: Answer }) {
  return (
    <ol className="flex flex-col gap-2">
      {answer.sources.map((s, i) => (
        <li key={s.chunk_id}>
          <details className="rounded-lg border bg-background/40 px-3 py-2">
            <summary className="flex cursor-pointer list-none items-center gap-2 text-sm">
              <span className="font-mono text-xs text-amber">[{i + 1}]</span>
              <FileText className="size-3.5 shrink-0 text-teal" />
              <span className="truncate">{s.title}</span>
              <span className="hidden truncate text-muted-foreground sm:inline">· {s.section}</span>
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
  );
}

export function AskPanel() {
  const [question, setQuestion] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [sessionId, setSessionId] = useState<string | undefined>();
  const [loading, setLoading] = useState(false);
  const inflight = useRef<AbortController | null>(null);
  const bottom = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turns]);

  async function submit(q: string) {
    const text = q.trim();
    if (text.length < 3 || loading) return;
    inflight.current?.abort();
    const ctrl = new AbortController();
    inflight.current = ctrl;
    setLoading(true);
    setQuestion("");
    setTurns((t) => [...t, { question: text }]);
    try {
      const answer = await ask(text, sessionId, ctrl.signal);
      setSessionId(answer.session_id);
      setTurns((t) => t.map((turn, i) => (i === t.length - 1 ? { ...turn, answer } : turn)));
    } catch (e) {
      if ((e as Error).name !== "AbortError") {
        const error = `${(e as Error).message}. The API may be waking up on the free tier; give it 30 seconds and try again.`;
        setTurns((t) => t.map((turn, i) => (i === t.length - 1 ? { ...turn, error } : turn)));
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      {turns.length === 0 && (
        <div className="flex flex-wrap gap-2">
          {EXAMPLES.map((ex) => (
            <button
              key={ex}
              type="button"
              onClick={() => submit(ex)}
              className="rounded-full border px-3 py-1 text-xs text-muted-foreground transition-colors hover:border-amber/60 hover:text-foreground"
            >
              {ex}
            </button>
          ))}
        </div>
      )}

      {turns.map((turn, i) => (
        <section key={i} className="flex flex-col gap-3">
          <p className="self-end rounded-2xl rounded-br-sm bg-secondary px-4 py-2 text-sm">
            {turn.question}
          </p>
          {!turn.answer && !turn.error && (
            <Loader2 className="size-4 animate-spin text-muted-foreground" />
          )}
          {turn.error && (
            <p className="rounded-lg border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm">
              {turn.error}
            </p>
          )}
          {turn.answer && (
            <div className="flex flex-col gap-3 rounded-xl border bg-card p-4">
              <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                <Badge variant="outline" className="font-mono">
                  {turn.answer.provider}
                  {turn.answer.model !== "none" ? ` · ${turn.answer.model}` : ""}
                </Badge>
                <span>{(turn.answer.latency_ms / 1000).toFixed(1)}s</span>
                {turn.answer.fallbacks.length > 0 && (
                  <span title={turn.answer.fallbacks.join(", ")}>
                    after {turn.answer.fallbacks.length} fallback
                    {turn.answer.fallbacks.length > 1 ? "s" : ""}
                  </span>
                )}
              </div>
              <div className="leading-relaxed whitespace-pre-wrap">{turn.answer.answer}</div>
              <Sources answer={turn.answer} />
            </div>
          )}
        </section>
      ))}
      <div ref={bottom} />

      <form
        className="sticky bottom-4 flex flex-col gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          submit(question);
        }}
      >
        <div className="relative">
          <Textarea
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                submit(question);
              }
            }}
            placeholder={
              turns.length ? "Ask a follow-up..." : "Ask about a pipeline incident, a runbook, or a past write-up..."
            }
            className="min-h-24 resize-none bg-card pr-14 text-base shadow-lg"
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
        </div>
        {sessionId && (
          <button
            type="button"
            onClick={() => {
              setTurns([]);
              setSessionId(undefined);
            }}
            className="flex w-fit items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
          >
            <RotateCcw className="size-3" /> New conversation
          </button>
        )}
      </form>
    </div>
  );
}
