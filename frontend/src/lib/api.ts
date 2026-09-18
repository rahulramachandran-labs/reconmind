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
};

export type Answer = {
  answer: string;
  sources: Source[];
  provider: string;
  model: string;
  latency_ms: number;
};

export async function ask(question: string, signal?: AbortSignal): Promise<Answer> {
  const res = await fetch(`${API_URL}/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
    signal,
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw new Error(`API ${res.status}${detail ? `: ${detail.slice(0, 200)}` : ""}`);
  }
  return res.json();
}
