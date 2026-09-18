import { AskPanel } from "@/components/ask-panel";

export const metadata = { title: "Ask ReconMind" };

export default function AskPage() {
  return (
    <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-8 px-4 py-8 sm:py-12">
      <header className="flex flex-col gap-2">
        <h1 className="text-2xl font-semibold sm:text-3xl">
          Ask the runbooks before you page someone.
        </h1>
        <p className="text-muted-foreground">
          Ask how something works and it answers from the runbooks with citations. Ask what is
          wrong and the Planner sends the specialist agents to look at the live pipeline, then the
          Reporter writes it up.
        </p>
      </header>
      <AskPanel />
      <footer className="mt-auto pt-8 text-xs text-muted-foreground">
        Synthetic data only.{" "}
        <a
          className="underline underline-offset-4 hover:text-foreground"
          href="https://github.com/rahulramachandran-labs/reconmind"
        >
          Source on GitHub
        </a>
      </footer>
    </main>
  );
}
