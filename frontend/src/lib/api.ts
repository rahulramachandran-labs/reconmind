export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");
export const REPO_URL = "https://github.com/rahulramachandran-labs/reconmind";

// A free instance sleeps when idle and the first request after that can take a minute.
// Any call still waiting after five seconds flips this on; the next response flips it off.
const WAKE_AFTER_MS = 5000;
let waking = false;
const wakeListeners = new Set<() => void>();

function setWaking(value: boolean) {
  if (waking === value) return;
  waking = value;
  wakeListeners.forEach((l) => l());
}

export const apiWaking = {
  subscribe(listener: () => void) {
    wakeListeners.add(listener);
    return () => {
      wakeListeners.delete(listener);
    };
  },
  get: () => waking,
};

async function watched(url: string, init?: RequestInit): Promise<Response> {
  const timer = setTimeout(() => setWaking(true), WAKE_AFTER_MS);
  try {
    const res = await fetch(url, init);
    setWaking(false);
    return res;
  } finally {
    clearTimeout(timer);
  }
}

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
  const res = await watched(`${API_URL}${path}`, {
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

export type Severity = "S1" | "S2" | "S3" | "S4";

export type Evidence = { source: string; summary: string; data?: Record<string, unknown> };

/** The parts of a report that are written rather than measured. */
export type WriteUp = {
  problem_statement: string;
  root_cause_hypothesis: string;
  recommended_fix: string[];
  open_questions: string[];
  confidence: number;
};

export type ModelWriteUp = WriteUp & {
  provider: string;
  model: string | null;
  latency_ms: number;
  prompt_tokens: number;
  completion_tokens: number;
  cost_usd: number;
  prompt_version?: string | null;
  generated_at?: string | null;
};

export type IncidentReport = {
  id: string;
  run_id: string;
  finding_type: string;
  specialist: string;
  severity: Severity;
  title: string;
  problem_statement: string;
  affected_records: { count: number; rate: number | null; detail: string };
  root_cause_hypothesis: string;
  recommended_fix: string[];
  confidence: number;
  confidence_label: "low" | "medium" | "high";
  open_questions: string[];
  evidence: Evidence[];
  sources: { chunk_id: string; doc_id: string; title: string; section: string }[];
  analysis_by: string;
  needs_review: boolean;
  review_reason: string | null;
  trace_url: string | null;
  status: "pending_review" | "published" | "rejected";
  seen_count?: number;
  last_seen_at?: string | null;
  /** finding_type:title. Copies of one finding written before the API de-duplicated them
   * share it; duplicate_of points a copy at the report it repeats. */
  fingerprint?: string | null;
  duplicate_of?: string | null;
  repeat?: boolean;
  review_decision?: string | null;
  review_note?: string | null;
  reviewed_by?: string | null;
  created_at?: string;
  /** What the deterministic checks and the adapter's templates wrote. */
  template?: WriteUp | null;
  /** What the model wrote from the same facts, with who wrote it and what it cost. */
  model_analysis?: ModelWriteUp | null;
};

export type ModelStatus = {
  provider: string;
  model: string | null;
  chain: string[];
  fell_back: boolean | null;
  last_call_at: string | null;
};

export const getModel = () => request<ModelStatus>("/model");
export const getIncident = (id: string) => request<IncidentReport>(`/incidents/${id}`);

export type RunStep = {
  node: string;
  kind: "node" | "llm" | "tool" | "retrieval";
  name: string;
  provider: string | null;
  model: string | null;
  prompt_version: string | null;
  latency_ms: number;
  prompt_tokens: number;
  completion_tokens: number;
  cost_usd: number;
  error: string | null;
  started_at: string;
  input: Record<string, unknown>;
  output: Record<string, unknown>;
};

export type Run = {
  id: string;
  trigger: "scan" | "question" | "ask";
  question: string | null;
  status: string;
  summary: string | null;
  error: string | null;
  trace_url: string | null;
  prompt_tokens: number;
  completion_tokens: number;
  cost_usd: number;
  latency_ms: number | null;
  started_at: string;
  finished_at: string | null;
  llm_calls?: number;
  plan?: Record<string, unknown>;
  steps?: RunStep[];
  reports?: IncidentReport[];
};

export type PausedPlan = Run & {
  plan: { intent: string; specialists: string[]; confidence: number; rationale: string };
};

/** What makes two reports the same finding: the API's fingerprint, or the pair it is built
 * from. Reports written before the API de-duplicated them have no fingerprint of their own. */
type Finding = {
  finding_type?: string;
  title: string;
  status: string;
  fingerprint?: string | null;
  seen_count?: number;
  last_seen_at?: string | null;
  created_at?: string;
};

const fingerprintOf = (r: Finding) =>
  r.fingerprint ?? [r.finding_type, r.title].filter(Boolean).join(":");

const seenAt = (r: Finding) => r.last_seen_at ?? r.created_at ?? "";

/** One row per finding. The API does this itself once it has run migration 0004; until then
 * (or against an older deployment) copies of the same finding would otherwise fill the feed
 * and the review queue. Of several copies, keep the one still waiting for a reviewer, else
 * the one seen most recently, and count every copy as a sighting. */
export function onePerFinding<T extends Finding>(rows: T[]): T[] {
  const kept = new Map<string, T>();
  for (const row of rows) {
    const key = fingerprintOf(row);
    const other = kept.get(key);
    if (!other) {
      kept.set(key, row);
      continue;
    }
    const wins =
      other.status === "pending_review"
        ? false
        : row.status === "pending_review" || seenAt(row) > seenAt(other);
    const seen = (other.seen_count ?? 1) + (row.seen_count ?? 1);
    kept.set(key, { ...(wins ? row : other), seen_count: seen });
  }
  return [...kept.values()];
}

export const listIncidents = (params: { status?: string; severity?: string } = {}) => {
  const q = new URLSearchParams(Object.entries(params).filter(([, v]) => v) as [string, string][]);
  return request<IncidentReport[]>(`/incidents${q.size ? `?${q}` : ""}`);
};
export const listRuns = () => request<Run[]>("/runs");
export const getRun = (id: string) => request<Run>(`/runs/${id}`);
export class SignInRequired extends Error {
  constructor() {
    super("Sign in as a reviewer to do that");
  }
}

/** Writes go through the web app, which checks the session and adds the API token. */
async function action<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`/api/actions/${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (res.status === 401) throw new SignInRequired();
  if (res.status === 429) throw new Error("Slow down a little: rate limit reached, try again in a minute");
  if (!res.ok) throw new Error(`API ${res.status}: ${(await res.text().catch(() => "")).slice(0, 200)}`);
  return res.json() as Promise<T>;
}

export const startScan = () => action<{ run_id: string }>("scan");
export const reviewQueue = () => request<{ reports: IncidentReport[]; plans: PausedPlan[] }>("/review");
export const reviewReport = (id: string, decision: "approve" | "reject" | "annotate", note?: string) =>
  action<{ status: string }>(`review/reports/${id}`, { decision, note: note || null });
export const reviewPlan = (id: string, decision: "approve" | "reject", specialists: string[] = []) =>
  action<{ status: string }>(`review/runs/${id}`, { decision, specialists });
export const regenerateReport = (id: string) => action<IncidentReport>(`incidents/${id}/regenerate`);

export type Dashboard = {
  adapter: string;
  pipeline: {
    as_of: string | null;
    volume: {
      rows: number;
      trailing_avg_7d: number;
      pct_change: number | null;
      series: { date: string; rows: number; by_submitter: Record<string, number> }[];
    } | null;
    last_run: {
      business_date: string;
      state: string;
      duration_s: number;
      failed_tasks: string[];
      runs_failed_14d: number;
    } | null;
  };
  usage: {
    day: string;
    runs: number;
    llm_calls: number;
    tokens: number;
    cost_usd: number;
    providers: { provider: string; model: string | null; calls: number; tokens: number; cost_usd: number }[];
    last_scan: Run | null;
  };
  findings: {
    run_id: string | null;
    by_severity: Record<Severity, number>;
    pending_review: number;
    items: { id: string; severity: Severity; title: string; status: string }[];
  };
};

export const getDashboard = () => request<Dashboard>("/dashboard");

export type StreamEvent = { event: string; data: Record<string, unknown> };

/** POST that returns server-sent events; EventSource can only GET. */
export async function* chatStream(
  question: string,
  sessionId: string | undefined,
  signal?: AbortSignal,
): AsyncGenerator<StreamEvent> {
  const res = await watched(`${API_URL}/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify({ question, session_id: sessionId ?? null }),
    signal,
  });
  if (res.status === 429) throw new Error("Slow down a little: rate limit reached, try again in a minute");
  if (!res.ok || !res.body) {
    throw new Error(`API ${res.status}: ${(await res.text().catch(() => "")).slice(0, 200)}`);
  }
  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += value;
    let idx;
    while ((idx = buffer.search(/\r?\n\r?\n/)) !== -1) {
      const block = buffer.slice(0, idx);
      buffer = buffer.slice(idx).replace(/^\r?\n\r?\n/, "");
      let event = "message";
      const data: string[] = [];
      for (const line of block.split(/\r?\n/)) {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        else if (line.startsWith("data:")) data.push(line.slice(5).trim());
      }
      if (data.length) yield { event, data: JSON.parse(data.join("\n")) };
    }
  }
}
