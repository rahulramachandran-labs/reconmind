import NextAuth from "next-auth";
import type { Provider } from "next-auth/providers";
import Credentials from "next-auth/providers/credentials";
import GitHub from "next-auth/providers/github";

// Demo mode signs every visitor in as one shared reviewer so the public demo can be
// clicked through. Set AUTH_DEMO_MODE=false and the GitHub variables for real sign-in;
// AUTH_ALLOWED_GITHUB_LOGINS limits who can act.
const demoMode = process.env.AUTH_DEMO_MODE !== "false";
const allowed = (process.env.AUTH_ALLOWED_GITHUB_LOGINS ?? "")
  .split(",")
  .map((s) => s.trim().toLowerCase())
  .filter(Boolean);

const providers: Provider[] = [];
if (process.env.AUTH_GITHUB_ID && process.env.AUTH_GITHUB_SECRET) {
  providers.push(GitHub);
}
if (demoMode) {
  providers.push(
    Credentials({
      id: "demo",
      name: "Demo reviewer",
      credentials: {},
      authorize: async () => ({ id: "demo", name: "Demo reviewer", email: null }),
    }),
  );
}

export const { handlers, auth, signIn, signOut } = NextAuth({
  providers,
  session: { strategy: "jwt" },
  pages: { signIn: "/signin" },
  trustHost: true,
  callbacks: {
    signIn({ account, profile }) {
      if (account?.provider !== "github" || allowed.length === 0) return true;
      return allowed.includes(String(profile?.login ?? "").toLowerCase());
    },
  },
});

export const authOptions = { demoMode, github: providers.some((p) => (p as { id?: string }).id === "github") };
