import { api, displayName, fileUrl, GATE_LABELS, postResult, STATUS_LABELS, STEP_LABELS, type Job } from "../api-client";
import PickImagePanel from "./pick-image-panel";
import { FilePickButton, ReviewCutoutPanel, ReviewFlowVideoPanel, ReviewPromptPanel } from "./review-panels";
import StepProgressBar from "./step-progress-bar";
import { useJobAction } from "./use-job-action";

type Props = { job: Job; onChange: (job: Job) => void };
const FLOW_STEPS = ["flow_generate", "flow_download"];

function ErrorPanel({ job, onChange }: Props) {
  const { busy, error, run } = useJobAction(onChange);
  const err = job.error!;
  const isFlow = FLOW_STEPS.includes(err.step);
  const retry = () => {
    if (err.step === "flow_generate" && !window.confirm("Thử lại bước sinh video sẽ gửi lại lên Flow và tốn credit. Tiếp tục?")) return;
    if (err.step === "tiktok_post" && job.post.submitted_at && !job.post.done_at
      && !window.confirm("Tool đã bấm Post/Schedule trước đó. Tool sẽ tìm bài đó trên TikTok Studio trước; không thấy thì đăng lại và có thể thành 2 bài. Tiếp tục?")) return;
    run(() => api.retry(job.id, err.step));
  };
  return (
    <div className="review">
      <div className="error-box">
        <strong>Lỗi ở bước {STEP_LABELS[err.step]}</strong>
        <p>{err.reason}</p>
      </div>
      {err.screenshot && <img className="screenshot" src={fileUrl(job, err.screenshot)} alt="Ảnh chụp màn hình lúc lỗi" />}
      <div className="actions">
        <button className="btn btn-primary" disabled={busy} onClick={retry}>Thử lại</button>
        {err.step === "fetch_source" && (
          <FilePickButton label="Dùng ảnh của tôi" accept=".jpg,.jpeg,.png,.webp,.heic,.heif" disabled={busy}
            onPick={(image) => run(() => api.pick(job.id, { image }))} />
        )}
        {isFlow && (
          <>
            <button className="btn" disabled={busy} onClick={() => run(() => api.continueJob(job.id))}>
              Tôi đã sửa tay, tiếp tục
            </button>
            <FilePickButton label="Tải video lên thủ công" accept="video/mp4,.mp4,.mov" disabled={busy}
              onPick={(video) => run(() => api.manualVideo(job.id, video))} />
          </>
        )}
      </div>
      {error && <div className="error-text">{error}</div>}
    </div>
  );
}

function DonePanel({ job, onChange }: Props) {
  const { busy, error, run } = useJobAction(onChange);
  const result = postResult(job);
  const canPost = Boolean(job.source) && !job.post.mode;
  return (
    <div className="review">
      <video className="video" src={fileUrl(job, "final-4k60.mp4")} controls loop playsInline />
      <p className="muted">Đã xuất: <code>{job.export_path}</code></p>
      {result && <p className="post-result">{result}</p>}
      <div className="actions">
        {canPost && (
          <>
            <button className="btn btn-primary" disabled={busy}
              onClick={() => run(() => api.postOnTikTok(job.id, "now"))}>📤 Đăng ngay</button>
            <button className="btn" disabled={busy}
              onClick={() => run(() => api.postOnTikTok(job.id, "schedule"))}>🗓 Lên lịch</button>
          </>
        )}
        <button className={canPost ? "btn" : "btn btn-primary"} onClick={() => api.openExportDir()}>Mở thư mục xuất</button>
      </div>
      {error && <div className="error-text">{error}</div>}
    </div>
  );
}

function ProgressPanel({ job }: { job: Job }) {
  return (
    <div className="review">
      <div className="progress-line">
        <strong>{STEP_LABELS[job.current_step]}</strong>
        <span className="muted">{job.status === "queued" ? "Đang chờ lượt…" : job.message}</span>
      </div>
      {job.status === "running" && (
        <div className="progress"><div className="progress-fill" style={{ width: `${Math.round(job.progress * 100)}%` }} /></div>
      )}
      {job.input_file && (
        <div className="compare">
          <figure><img src={fileUrl(job, job.input_file)} alt="Ảnh gốc" /><figcaption>Ảnh gốc</figcaption></figure>
        </div>
      )}
    </div>
  );
}

export default function JobDetailPanel({ job, onChange }: Props) {
  const { busy, run } = useJobAction(onChange);
  const clickedPost = job.current_step === "tiktok_post" && Boolean(job.post.submitted_at) && !job.post.done_at;
  const cancellable = !["done", "cancelled"].includes(job.status) && !clickedPost;

  let body;
  if (job.status === "awaiting_review" && job.gate === "pick_image") body = <PickImagePanel job={job} onChange={onChange} />;
  else if (job.status === "awaiting_review" && job.gate === "cutout") body = <ReviewCutoutPanel job={job} onChange={onChange} />;
  else if (job.status === "awaiting_review" && job.gate === "prompt") body = <ReviewPromptPanel job={job} onChange={onChange} />;
  else if (job.status === "awaiting_review" && job.gate === "flow_video") body = <ReviewFlowVideoPanel job={job} onChange={onChange} />;
  else if (job.status === "failed" && job.error) body = <ErrorPanel job={job} onChange={onChange} />;
  else if (job.status === "done") body = <DonePanel job={job} onChange={onChange} />;
  else if (job.status === "cancelled") body = <p className="muted">Job đã huỷ.</p>;
  else body = <ProgressPanel job={job} />;

  return (
    <div className="card detail-card">
      <div className="detail-head">
        <div>
          <h2>{displayName(job)}</h2>
          <span className={`badge badge-${job.status}`}>
            {job.status === "awaiting_review" && job.gate ? GATE_LABELS[job.gate] : STATUS_LABELS[job.status]}
          </span>
          {job.note && <span className="muted note">Ghi chú: {job.note}</span>}
        </div>
        <div className="actions">
          <a className="btn btn-small" href={fileUrl(job, "log.txt")} target="_blank" rel="noreferrer">Xem log</a>
          {cancellable && (
            <button className="btn btn-small btn-danger" disabled={busy}
              onClick={() => window.confirm("Huỷ job này?") && run(() => api.cancel(job.id))}>Huỷ job</button>
          )}
        </div>
      </div>
      <StepProgressBar job={job} />
      {body}
    </div>
  );
}
