"use client";

import Link from "next/link";
import { Loader2, LogIn, Radar } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useSignedIn } from "@/lib/session";

/** Scans are a write, so signed-out visitors get the way in rather than a button that fails. */
export function ScanButton({ scanning, onScan, from }: { scanning: boolean; onScan: () => void; from: string }) {
  const signedIn = useSignedIn();
  if (signedIn === false) {
    return (
      <Button asChild variant="outline">
        <Link href={`/signin?callbackUrl=${encodeURIComponent(from)}`}>
          <LogIn /> Sign in as demo reviewer to scan
        </Link>
      </Button>
    );
  }
  return (
    <Button onClick={onScan} disabled={scanning || signedIn === null}>
      {scanning ? <Loader2 className="animate-spin" /> : <Radar />}
      {scanning ? "Scanning..." : "Run a scan"}
    </Button>
  );
}
