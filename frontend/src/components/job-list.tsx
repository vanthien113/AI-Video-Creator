import { displayName, GATE_LABELS, STATUS_LABELS, thumbUrl, type Job } from "../api-client";
import StepProgressBar from "./step-progress-bar";

function subtitle(job: Job): string {
  if (job.status === "awaiting_review" && job.gate) return GATE_LABELS[job.gate];
  if (job.status === "failed" && job.error) return job.error.reason;
  if (job.status === "running") return job.message || "Đang xử lý…";
  return STATUS_LABELS[job.status];
}

export default function JobList({ jobs, selectedId, onSelect }: {
  jobs: Job[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  if (!jobs.length) return null;
  return (
    <ul className="job-list">
      {jobs.map((job) => (
        <li key={job.id}>
          <button
            className={`job-item ${job.id === selectedId ? "job-item-selected" : ""} job-${job.status}`}
            onClick={() => onSelect(job.id)}
          >
            {thumbUrl(job) ? (
              <img className="job-thumb" src={thumbUrl(job)!} alt="" loading="lazy"
                onError={(e) => { e.currentTarget.style.visibility = "hidden"; }} />
            ) : <span className="job-thumb job-thumb-link">🔗</span>}
            <span className="job-text">
              <span className="job-name">{displayName(job)}</span>
              <span className={`badge badge-${job.status}`}>{STATUS_LABELS[job.status]}</span>
              <span className="job-sub">{subtitle(job)}</span>
              <StepProgressBar job={job} compact />
            </span>
          </button>
        </li>
      ))}
    </ul>
  );
}
