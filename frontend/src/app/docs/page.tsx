import { Suspense } from "react";

import { DocsBrowser } from "@/components/docs-browser";

export const metadata = { title: "Docs & runbooks · ReconMind" };

export default function DocsPage() {
  return (
    <main className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-6 px-4 py-8">
      <header className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold">Docs &amp; runbooks</h1>
        <p className="text-sm text-muted-foreground">
          The corpus the agents retrieve from. Search it directly to check what retrieval returns,
          and compare hybrid against dense-only and keyword-only.
        </p>
      </header>
      <Suspense>
        <DocsBrowser />
      </Suspense>
    </main>
  );
}
