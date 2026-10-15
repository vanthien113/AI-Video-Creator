import { STEP_LABELS, stepsFor, type Job } from "../api-client";

type StepState = "done" | "active" | "review" | "failed" | "todo";

function stepState(job: Job, steps: string[], index: number): StepState {
  const current = steps.indexOf(job.current_step);
  if (job.status === "done") return "done";
  if (job.status === "awaiting_review" && index === current - 1) return "review";
  if (index < current) return "done";
  if (index === current) {
    if (job.status === "failed") return "failed";
    if (job.status === "running" || job.status === "queued") return "active";
  }
  return "todo";
}

export default function StepProgressBar({ job, compact = false }: { job: Job; compact?: boolean }) {
  const steps = stepsFor(job);
  return (
    <ol className={`steps ${compact ? "steps-compact" : ""}`} style={{ gridTemplateColumns: `repeat(${steps.length}, 1fr)` }}>
      {steps.map((step, index) => {
        const state = stepState(job, steps, index);
        const running = state === "active" && job.status === "running";
        return (
          <li key={step} className={`step step-${state}`} title={STEP_LABELS[step]}>
            <span className="step-bar">
              {running && <span className="step-fill" style={{ width: `${Math.round(job.progress * 100)}%` }} />}
            </span>
            {!compact && <span className="step-label">{STEP_LABELS[step]}</span>}
          </li>
        );
      })}
    </ol>
  );
}
