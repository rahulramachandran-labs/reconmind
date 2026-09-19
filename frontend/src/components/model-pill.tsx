"use client";

import { useEffect, useState } from "react";

import { getModel, type ModelStatus } from "@/lib/api";
import { cn } from "@/lib/utils";

export function ModelPill() {
  const [status, setStatus] = useState<ModelStatus | null>(null);

  useEffect(() => {
    getModel()
      .then(setStatus)
      .catch(() => setStatus(null));
  }, []);

  if (!status) return null;
  const live = status.provider !== "extractive";
  const title = live
    ? `The API answers with ${status.provider} (${status.model}). Fallback order: ${status.chain.join(" → ")}.` +
      (status.fell_back ? " The last call fell back from an earlier provider." : "")
    : "No model is configured on the API, so answers are extractive and write-ups come from templates.";
  return (
    <span
      title={title}
      className={cn(
        "flex shrink-0 items-center gap-1.5 rounded-full border px-2.5 py-1 font-mono text-[11px]",
        live ? "border-teal/40 text-foreground" : "text-muted-foreground",
      )}
    >
      <span className={cn("size-1.5 rounded-full", live ? "bg-teal" : "bg-muted-foreground")} />
      {live ? `${status.provider} · ${status.model}` : "no model · extractive"}
      {live && status.fell_back && <span className="text-amber">fell back</span>}
    </span>
  );
}
