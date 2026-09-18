"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { cn } from "@/lib/utils";

const LINKS = [
  { href: "/", label: "Ask ReconMind" },
  { href: "/incidents", label: "Incidents" },
  { href: "/review", label: "Review queue" },
  { href: "/docs", label: "Docs & runbooks" },
  { href: "/traces", label: "Traces" },
];

export function SiteNav() {
  const pathname = usePathname();
  return (
    <header className="sticky top-0 z-20 border-b bg-background/85 backdrop-blur">
      <div className="mx-auto flex w-full max-w-5xl items-center gap-6 overflow-x-auto px-4 py-3">
        <Link href="/" className="shrink-0 font-mono text-sm font-semibold tracking-wider">
          <span className="text-amber">Recon</span>
          <span className="text-teal">Mind</span>
        </Link>
        <nav className="flex gap-1 text-sm">
          {LINKS.map((l) => {
            const active = l.href === "/" ? pathname === "/" : pathname.startsWith(l.href);
            return (
              <Link
                key={l.href}
                href={l.href}
                className={cn(
                  "shrink-0 rounded-md px-3 py-1.5 text-muted-foreground transition-colors hover:text-foreground",
                  active && "bg-secondary text-foreground",
                )}
              >
                {l.label}
              </Link>
            );
          })}
        </nav>
        <a
          href="https://github.com/rahulramachandran-labs/reconmind"
          className="ml-auto shrink-0 text-xs text-muted-foreground hover:text-foreground"
        >
          GitHub
        </a>
      </div>
    </header>
  );
}
