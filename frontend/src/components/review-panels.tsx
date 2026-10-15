import { useEffect, useState } from "react";
import { api, fileUrl, type Job } from "../api-client";
import { useJobAction } from "./use-job-action";

type Props = { job: Job; onChange: (job: Job) => void };

function FilePickButton({ label, accept, disabled, onPick }: {
  label: string; accept: string; disabled: boolean; onPick: (file: File) => void;
}) {
  return (
    <label className={`btn ${disabled ? "btn-disabled" : ""}`}>
      {label}
      <input type="file" accept={accept} hidden disabled={disabled}
        onChange={(e) => e.target.files?.[0] && onPick(e.target.files[0])} />
    </label>
  );
}

export function ReviewCutoutPanel({ job, onChange }: Props) {
  const { busy, error, run } = useJobAction(onChange);
  return (
    <div className="review">
      <div className="compare">
        <figure><img src={fileUrl(job, job.input_file)} alt="Ảnh gốc" /><figcaption>Ảnh gốc</figcaption></figure>
        <figure className="checker"><img src={fileUrl(job, "cutout.png")} alt="Đã tách nền" /><figcaption>Đã tách nền</figcaption></figure>
      </div>
      <div className="actions">
        <button className="btn btn-primary" disabled={busy} onClick={() => run(() => api.approve(job.id))}>Duyệt</button>
        <button className="btn" disabled={busy}
          onClick={() => run(() => api.retry(job.id, "cutout", { nextCutoutModel: true }))}>Thử mô hình khác</button>
        <FilePickButton label="Thay ảnh khác" accept=".jpg,.jpeg,.png,.webp,.heic,.heif" disabled={busy}
          onPick={(image) => run(() => api.retry(job.id, "cutout", { image }))} />
      </div>
      {error && <div className="error-text">{error}</div>}
    </div>
  );
}

export function ReviewPromptPanel({ job, onChange }: Props) {
  const { busy, error, run } = useJobAction(onChange);
  const [text, setText] = useState(job.prompt?.prompt ?? "");
  const [feedback, setFeedback] = useState("");
  useEffect(() => setText(job.prompt?.prompt ?? ""), [job.prompt?.prompt]);

  return (
    <div className="review review-prompt">
      <img className="product-preview checker" src={fileUrl(job, "product-2k.png")} alt="Ảnh gửi lên Flow" />
      <div className="prompt-edit">
        {job.prompt?.summary && <p className="summary">{job.prompt.summary}</p>}
        <label className="field-label" htmlFor="prompt-text">Prompt gửi lên Flow (sửa trực tiếp được)</label>
        <textarea id="prompt-text" className="input mono" rows={9} value={text} onChange={(e) => setText(e.target.value)} />
        <div className="actions">
          <button className="btn btn-primary" disabled={busy || !text.trim()}
            onClick={() => run(() => api.approve(job.id, text))}>Duyệt và gửi lên Flow</button>
        </div>
        <div className="actions">
          <input className="input" placeholder="Góp ý để Claude viết lại, ví dụ: thêm cảnh nước bắn" value={feedback}
            onChange={(e) => setFeedback(e.target.value)} />
          <button className="btn" disabled={busy} onClick={() => run(() => api.retry(job.id, "prompt", { feedback }))}>
            Viết lại
          </button>
        </div>
        {error && <div className="error-text">{error}</div>}
      </div>
    </div>
  );
}

export function ReviewFlowVideoPanel({ job, onChange }: Props) {
  const { busy, error, run } = useJobAction(onChange);
  const regenerate = () => {
    if (window.confirm("Sinh lại video trên Flow sẽ tốn thêm credit. Tiếp tục?")) {
      run(() => api.retry(job.id, "flow_generate"));
    }
  };
  return (
    <div className="review">
      <video className="video" src={fileUrl(job, "flow-raw.mp4")} controls loop playsInline />
      <div className="actions">
        <button className="btn btn-primary" disabled={busy} onClick={() => run(() => api.approve(job.id))}>
          Duyệt, nâng lên 60fps
        </button>
        <button className="btn" disabled={busy} onClick={regenerate}>Sinh lại (tốn credit)</button>
        <FilePickButton label="Thay bằng video tải tay" accept="video/mp4,.mp4,.mov" disabled={busy}
          onPick={(video) => run(() => api.manualVideo(job.id, video))} />
      </div>
      {error && <div className="error-text">{error}</div>}
    </div>
  );
}

export { FilePickButton };
