"use client";

import { useSyncExternalStore } from "react";
import { Loader2 } from "lucide-react";

import { apiWaking } from "@/lib/api";

export function ColdStartNotice() {
  const waking = useSyncExternalStore(apiWaking.subscribe, apiWaking.get, () => false);
  if (!waking) return null;
  return (
    <div role="status" className="border-b border-amber/30 bg-amber/10">
      <p className="mx-auto flex w-full max-w-5xl items-center gap-2 px-4 py-2 text-sm">
        <Loader2 className="size-4 animate-spin text-amber" />
        Waking the free-tier API, usually under a minute.
      </p>
    </div>
  );
}
