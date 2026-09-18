import { cn } from "@/lib/utils";
import type { Severity } from "@/lib/api";

const STYLE: Record<Severity, string> = {
  S1: "border-red-500/50 bg-red-500/15 text-red-300",
  S2: "border-amber/50 bg-amber/15 text-amber",
  S3: "border-teal/50 bg-teal/10 text-teal",
  S4: "border-border bg-secondary text-muted-foreground",
};

export function SeverityBadge({ severity, className }: { severity: Severity; className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex h-5 shrink-0 items-center rounded-md border px-1.5 font-mono text-[11px] font-semibold",
        STYLE[severity],
        className,
      )}
    >
      {severity}
    </span>
  );
}

const STATUS: Record<string, string> = {
  pending_review: "waiting for review",
  published: "published",
  rejected: "rejected",
  paused_review: "paused for review",
  paused_plan: "paused: plan check",
  running: "running",
  completed: "completed",
  failed: "failed",
};

export function StatusText({ status }: { status: string }) {
  const tone =
    status === "failed" || status === "rejected"
      ? "text-red-300"
      : status.startsWith("paused") || status === "pending_review"
        ? "text-amber"
        : status === "running"
          ? "text-teal"
          : "text-muted-foreground";
  return <span className={cn("text-xs", tone)}>{STATUS[status] ?? status}</span>;
}

export function ago(iso: string | null | undefined) {
  if (!iso) return "";
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 60) return `${Math.floor(s)}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}
