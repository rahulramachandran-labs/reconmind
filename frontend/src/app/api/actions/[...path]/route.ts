import { NextResponse } from "next/server";

import { auth } from "@/auth";

// Writes go through here so the API token never reaches the browser and every
// scan or review decision carries the name of the signed-in reviewer.
const API = (process.env.RECONMIND_API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");
const UUID = "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}";
const ALLOWED = [
  new RegExp("^scan$"),
  new RegExp(`^review/reports/${UUID}$`),
  new RegExp(`^review/runs/${UUID}$`),
  new RegExp(`^incidents/${UUID}/regenerate$`),
];
const NO_BODY = [new RegExp("^scan$"), new RegExp(`^incidents/${UUID}/regenerate$`)];

export async function POST(request: Request, ctx: RouteContext<"/api/actions/[...path]">) {
  const session = await auth();
  if (!session?.user) {
    return NextResponse.json({ detail: "sign in to do that" }, { status: 401 });
  }
  const { path } = await ctx.params;
  const target = path.join("/");
  if (!ALLOWED.some((re) => re.test(target))) {
    return NextResponse.json({ detail: "not found" }, { status: 404 });
  }
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    "X-Reviewer": session.user.name ?? session.user.email ?? "reviewer",
    "X-Forwarded-For": request.headers.get("x-forwarded-for") ?? "",
  };
  if (process.env.RECONMIND_WRITE_TOKEN) {
    headers.Authorization = `Bearer ${process.env.RECONMIND_WRITE_TOKEN}`;
  }
  const res = await fetch(`${API}/${target}`, {
    method: "POST",
    headers,
    body: NO_BODY.some((re) => re.test(target)) ? undefined : await request.text(),
    cache: "no-store",
  });
  return new NextResponse(await res.text(), {
    status: res.status,
    headers: { "Content-Type": res.headers.get("content-type") ?? "application/json" },
  });
}
