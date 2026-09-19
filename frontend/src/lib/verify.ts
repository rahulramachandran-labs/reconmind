import { REPO_URL } from "@/lib/api";

export const RAW_URL = "https://raw.githubusercontent.com/rahulramachandran-labs/reconmind/main";

export const ANOMALIES = ["key_drift", "duplicate_submission", "schema_drift", "volume_anomaly"] as const;
export type Anomaly = (typeof ANOMALIES)[number];

export const ANOMALY_LABEL: Record<Anomaly, string> = {
  key_drift: "Key drift",
  duplicate_submission: "Duplicate submission",
  schema_drift: "Schema drift",
  volume_anomaly: "Volume anomaly",
};

// The chaos suite plants each anomaly alone with the generator and asserts the right agent
// reports it at the right severity; the ids are pytest's parametrize ids.
const CHAOS_FILE = "tests/chaos/test_injected_anomalies.py";
const CHAOS_LINES = "L60-L72";
export const chaosTest = (kind: Anomaly) => ({
  label: `test_each_anomaly_is_caught_by_the_right_agent[${kind}]`,
  href: `${REPO_URL}/blob/main/${CHAOS_FILE}#${CHAOS_LINES}`,
});
export const DATA_DICTIONARY = `${REPO_URL}/blob/main/data/DATA_DICTIONARY.md#planted-anomalies`;

export type Planted = Record<Anomaly, Record<string, unknown>> & {
  summary: { days: number; files: number; rows: number; seed: number; start: string };
};

const pct = (x: unknown) => `${Math.round(Math.abs(Number(x)) * 1000) / 10}%`;

/** One sentence per anomaly, built from the generator's own record of what it planted. */
export function describePlanted(kind: Anomaly, p: Record<string, unknown>): string {
  switch (kind) {
    case "key_drift":
      return `${p.location_id} also reports as ${p.drifted_outlet_id} (canonical ${p.canonical_outlet_id}): ${p.drifted_rows} of ${Number(p.rows_in_window).toLocaleString()} rows, ${pct(p.drift_rate)}.`;
    case "duplicate_submission":
      return `${p.resend_file} resends ${p.original_file}: ${p.duplicate_keys} duplicate keys, ${p.changed_rows} with changed values, landed after the nightly DAG.`;
    case "schema_drift":
      return `${p.file} renames ${(p.missing_columns as string[])[0]} to ${(p.unexpected_columns as string[])[0]}: ${p.affected_rows} rows, and ${p.failed_task} fails.`;
    case "volume_anomaly":
      return `${p.file} has ${p.rows} rows against a trailing average of ${p.trailing_avg_7d} (${pct(p.pct_below_trailing)} below) and lands ${p.minutes_after_sla} minutes late.`;
  }
}

export type EvalRow = {
  timestamp: string;
  commit: string;
  retriever: string;
  judge: string;
  answerer: string;
  n: number;
  faithfulness: number;
  answer_relevancy: number;
  context_precision: number;
  context_recall: number;
  gate: string;
};

/** The latest row for each retriever, answerer and judge combination in evals/history.csv. */
export function latestEvals(csv: string): EvalRow[] {
  const [head, ...lines] = csv.trim().split(/\r?\n/);
  const cols = head.split(",");
  const latest = new Map<string, EvalRow>();
  for (const line of lines) {
    const cells = line.split(",");
    const raw = Object.fromEntries(cols.map((c, i) => [c, cells[i] ?? ""]));
    const row = {
      ...raw,
      n: Number(raw.n),
      faithfulness: Number(raw.faithfulness),
      answer_relevancy: Number(raw.answer_relevancy),
      context_precision: Number(raw.context_precision),
      context_recall: Number(raw.context_recall),
    } as EvalRow;
    latest.set(`${row.retriever}|${row.answerer}|${row.judge}`, row);
  }
  return [...latest.values()].sort((a, b) => b.timestamp.localeCompare(a.timestamp));
}
