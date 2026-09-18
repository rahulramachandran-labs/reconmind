import { redirect } from "next/navigation";

import { auth, authOptions, signIn } from "@/auth";
import { Button } from "@/components/ui/button";

export const metadata = { title: "Sign in · ReconMind" };

export default async function SignInPage({ searchParams }: PageProps<"/signin">) {
  const params = await searchParams;
  const next = typeof params.callbackUrl === "string" && params.callbackUrl.startsWith("/") ? params.callbackUrl : "/review";
  if ((await auth())?.user) redirect(next);
  return (
    <main className="mx-auto flex w-full max-w-sm flex-1 flex-col justify-center gap-6 px-4 py-16">
      <div className="flex flex-col gap-2">
        <h1 className="text-2xl font-semibold">Sign in to act</h1>
        <p className="text-sm text-muted-foreground">
          Anyone can read. Starting scans and signing off findings needs a reviewer, and every
          decision goes into the audit ledger under your name.
        </p>
      </div>
      {authOptions.github && (
        <form
          action={async () => {
            "use server";
            await signIn("github", { redirectTo: next });
          }}
        >
          <Button type="submit" className="w-full">
            Sign in with GitHub
          </Button>
        </form>
      )}
      {authOptions.demoMode && (
        <form
          action={async () => {
            "use server";
            await signIn("demo", { redirectTo: next });
          }}
        >
          <Button type="submit" variant={authOptions.github ? "outline" : "default"} className="w-full">
            Continue as the demo reviewer
          </Button>
        </form>
      )}
      {!authOptions.github && !authOptions.demoMode && (
        <p className="text-sm text-destructive">No sign-in method is configured on this deployment.</p>
      )}
    </main>
  );
}
