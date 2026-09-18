import Link from "next/link";

import { auth, signOut } from "@/auth";

export async function UserMenu() {
  const session = await auth();
  if (!session?.user) {
    return (
      <Link href="/signin" className="shrink-0 text-xs text-muted-foreground hover:text-foreground">
        Sign in
      </Link>
    );
  }
  return (
    <form
      className="flex shrink-0 items-center gap-2 text-xs text-muted-foreground"
      action={async () => {
        "use server";
        await signOut({ redirectTo: "/" });
      }}
    >
      <span className="hidden sm:inline">{session.user.name}</span>
      <button type="submit" className="hover:text-foreground">
        Sign out
      </button>
    </form>
  );
}
