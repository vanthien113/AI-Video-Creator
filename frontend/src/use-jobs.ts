import { useCallback, useEffect, useRef, useState } from "react";
import { api, type Job } from "./api-client";

type ProgressEvent = { type: "progress"; id: string; progress: number; message: string };
type JobEvent = { type: "job"; job: Job };

/** Job list kept live through the SSE stream at /api/events. */
export function useJobs() {
  const [jobs, setJobs] = useState<Record<string, Job>>({});
  const [connected, setConnected] = useState(false);

  const upsert = useCallback((job: Job) => setJobs((prev) => ({ ...prev, [job.id]: job })), []);
  const requestSeq = useRef<Record<string, number>>({});

  const refresh = useCallback(async (id?: string) => {
    if (id) {
      // Responses can resolve out of order: only the latest request per job may write.
      const seq = (requestSeq.current[id] ?? 0) + 1;
      requestSeq.current[id] = seq;
      const job = await api.getJob(id);
      if (requestSeq.current[id] === seq) upsert(job);
      return;
    }
    const list = await api.listJobs();
    setJobs(Object.fromEntries(list.map((j) => [j.id, j])));
  }, [upsert]);

  useEffect(() => {
    refresh().catch(() => undefined);
    const source = new EventSource("/api/events");
    source.onopen = () => {
      setConnected(true);
      refresh().catch(() => undefined); // catch up on anything missed while disconnected
    };
    source.onerror = () => setConnected(false);
    source.onmessage = (msg) => {
      let event: ProgressEvent | JobEvent;
      try {
        event = JSON.parse(msg.data);
      } catch {
        return;
      }
      if (event.type === "progress") {
        setJobs((prev) => {
          const job = prev[event.id];
          return job ? { ...prev, [event.id]: { ...job, progress: event.progress, message: event.message } } : prev;
        });
      } else {
        // The event carries state only; refetch to pick up prompt.json as well.
        refresh(event.job.id).catch(() => upsert({ ...event.job, prompt: null }));
      }
    };
    return () => source.close();
  }, [refresh, upsert]);

  const sorted = Object.values(jobs).sort((a, b) => b.created_at.localeCompare(a.created_at));
  return { jobs: sorted, byId: jobs, upsert, connected };
}
