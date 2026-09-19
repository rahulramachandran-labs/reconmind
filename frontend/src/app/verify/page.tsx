import { AskPanel } from "@/components/ask-panel";
import { ModelPill } from "@/components/model-pill";
import { VerifyAnomalies } from "@/components/verify-anomalies";
import { REPO_URL } from "@/lib/api";
import { DATA_DICTIONARY, latestEvals, RAW_URL, type EvalRow, type Planted } from "@/lib/verify";

export const metadata = { title: "Verify · ReconMind" };
export const revalidate = 3600;

async function fetchText(path: string): Promise<string | null> {
  try {
    const res = await fetch(`${RAW_URL}/${path}`, { next: { revalidate: 3600 } });
    return res.ok ? await res.text() : null;
  } catch {
    return null;
  }
}

const PROBE_QUESTIONS = [
  "Why would a resent ECOMM file double count revenue, and how do I fix 2026-06-12?",
  "Did anything go wrong with S1001's file on 2026-06-18?",
  "Explain the difference between key drift and a duplicate submission in this pipeline.",
];

const f3 = (x: number) => x.toFixed(3);

function EvalTable({ rows }: { rows: EvalRow[] }) {
  return (
    <div className="overflow-x-auto rounded-xl border bg-card">
      <table className="w-full text-sm tabular-nums">
        <thead className="text-left text-xs text-muted-foreground">
          <tr className="border-b">
            <th className="px-3 py-2 font-medium">Retriever</th>
            <th className="px-3 py-2 font-medium">Answers by</th>
            <th className="px-3 py-2 font-medium">Judged by</th>
            <th className="px-3 py-2 font-medium">Faithfulness</th>
            <th className="px-3 py-2 font-medium">Relevancy</th>
            <th className="px-3 py-2 font-medium">Ctx precision</th>
            <th className="px-3 py-2 font-medium">Ctx recall</th>
            <th className="px-3 py-2 font-medium">Gate</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={`${r.retriever}${r.answerer}${r.judge}`} className="border-b last:border-0">
              <td className="px-3 py-2 font-mono text-xs">{r.retriever}</td>
              <td className="px-3 py-2 font-mono text-xs">{r.answerer}</td>
              <td className="px-3 py-2 font-mono text-xs">{r.judge}</td>
              <td className="px-3 py-2">{f3(r.faithfulness)}</td>
              <td className="px-3 py-2">{f3(r.answer_relevancy)}</td>
              <td className="px-3 py-2">{f3(r.context_precision)}</td>
              <td className="px-3 py-2">{f3(r.context_recall)}</td>
              <td className={r.gate === "pass" ? "px-3 py-2 text-teal" : "px-3 py-2 text-amber"}>{r.gate}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default async function VerifyPage() {
  const [plantedJson, historyCsv] = await Promise.all([
    fetchText("data/sample/expected_anomalies.json"),
    fetchText("evals/history.csv"),
  ]);
  const planted = plantedJson ? (JSON.parse(plantedJson) as Planted) : null;
  const evals = historyCsv ? latestEvals(historyCsv) : [];

  return (
    <main className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-10 px-4 py-8">
      <header className="flex flex-col gap-3">
        <h1 className="text-2xl font-semibold">Verify it yourself</h1>
        <p className="max-w-3xl text-muted-foreground">
          The sample pipeline is generated with four problems planted at exact, documented sizes. This page lines each one
          up with the finding this deployment produced, the test that proves the agents catch it, and what the checks and
          the model each wrote about it. Then ask the model anything and read the trace.
        </p>
        <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
          <span>Model on the API right now:</span>
          <ModelPill />
          <a href={DATA_DICTIONARY} className="underline underline-offset-4 hover:text-foreground">
            data dictionary
          </a>
          <a href={`${REPO_URL}/blob/main/docs/VERIFY.md`} className="underline underline-offset-4 hover:text-foreground">
            docs/VERIFY.md
          </a>
          <a href={`${REPO_URL}/blob/main/docs/REVIEWER_GUIDE.md`} className="underline underline-offset-4 hover:text-foreground">
            reviewer guide
          </a>
        </div>
      </header>

      <section className="flex flex-col gap-3">
        <h2 className="text-lg font-semibold">
          Four planted anomalies, four findings
          {planted && (
            <span className="ml-2 text-sm font-normal text-muted-foreground">
              seed {planted.summary.seed}, {planted.summary.files} files, {planted.summary.rows.toLocaleString()} rows over{" "}
              {planted.summary.days} days
            </span>
          )}
        </h2>
        <VerifyAnomalies planted={planted} />
      </section>

      <section className="flex flex-col gap-3">
        <h2 className="text-lg font-semibold">Prove the model is real</h2>
        <p className="max-w-3xl text-sm text-muted-foreground">
          Ask your own question about the pipeline. It goes through the same agent graph as everything else: the answer
          names the provider and model that wrote it, says so plainly if it fell back to an extractive answer, and links to
          the trace of every step.
        </p>
        <AskPanel examples={PROBE_QUESTIONS} inline />
      </section>

      <section className="flex flex-col gap-3">
        <h2 className="text-lg font-semibold">Retrieval and answer quality (RAGAS)</h2>
        <p className="max-w-3xl text-sm text-muted-foreground">
          The latest scores for each way the 46-question golden set has been run, straight from{" "}
          <a href={`${REPO_URL}/blob/main/evals/history.csv`} className="underline underline-offset-4">
            evals/history.csv
          </a>
          . <span className="font-mono">extractive</span> answers need no model and gate CI on every push;{" "}
          <span className="font-mono">model</span> rows name the provider that answered and judged.
        </p>
        {evals.length ? (
          <EvalTable rows={evals} />
        ) : (
          <p className="text-sm text-muted-foreground">Couldn&apos;t load evals/history.csv from GitHub just now.</p>
        )}
      </section>
    </main>
  );
}
