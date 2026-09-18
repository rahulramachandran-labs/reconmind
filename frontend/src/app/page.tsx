import { AskPanel } from "@/components/ask-panel";

export default function Home() {
  return (
    <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-8 px-4 py-8 sm:py-12">
      <header className="flex flex-col gap-2">
        <h1 className="text-2xl font-semibold sm:text-3xl">
          Ask the runbooks before you page someone.
        </h1>
        <p className="text-muted-foreground">
          Answers come from the pipeline&apos;s runbooks, schema docs, dbt models and past incident
          write-ups, with every claim tied to a source. Follow-up questions keep the conversation.
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
