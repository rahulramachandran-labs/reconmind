"use client";

import { useEffect, useState } from "react";

/** Whether someone is signed in: null while it's being checked. */
export function useSignedIn(): boolean | null {
  const [signedIn, setSignedIn] = useState<boolean | null>(null);
  useEffect(() => {
    fetch("/api/auth/session")
      .then((r) => (r.ok ? r.json() : null))
      .then((s) => setSignedIn(Boolean(s?.user)))
      .catch(() => setSignedIn(false));
  }, []);
  return signedIn;
}
