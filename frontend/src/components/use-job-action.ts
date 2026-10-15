import { useState } from "react";
import type { Job } from "../api-client";

/** Wrap a job API call with busy/error state and push the returned job to the list. */
export function useJobAction(onChange: (job: Job) => void) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const run = async (call: () => Promise<Job>) => {
    setBusy(true);
    setError("");
    try {
      onChange(await call());
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return { busy, error, run };
}
