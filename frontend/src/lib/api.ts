export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");

export type Source = {
  chunk_id: string;
  doc_id: string;
  title: string;
  path: string;
  section: string;
  doc_type: string;
  text: string;
  score: number;
  rank: number;
  dense_rank: number | null;
  bm25_rank: number | null;
};

export type Answer = {
  answer: string;
  sources: Source[];
  provider: string;
  model: string;
  latency_ms: number;
  prompt_tokens: number;
  completion_tokens: number;
  cost_usd: number;
  fallbacks: string[];
  retrieval_query: string;
  session_id: string;
};

export type CorpusDoc = { doc_id: string; title: string; path: string; doc_type: string };
export type CorpusDocBody = CorpusDoc & { body: string };
export type SearchMode = "hybrid" | "dense" | "bm25";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw new Error(`API ${res.status}${detail ? `: ${detail.slice(0, 200)}` : ""}`);
  }
  return res.json() as Promise<T>;
}

export function ask(question: string, sessionId?: string, signal?: AbortSignal) {
  return request<Answer>("/ask", {
    method: "POST",
    body: JSON.stringify({ question, session_id: sessionId ?? null }),
    signal,
  });
}

export const listCorpus = () => request<CorpusDoc[]>("/corpus");
export const getDoc = (docId: string) => request<CorpusDocBody>(`/corpus/${docId}`);
export const search = (q: string, mode: SearchMode, k = 8) =>
  request<Source[]>(`/search?${new URLSearchParams({ q, mode, k: String(k) })}`);
