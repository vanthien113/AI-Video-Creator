import { useEffect, useState } from "react";
import { api, fileUrl, type Job } from "../api-client";
import { FilePickButton } from "./review-panels";
import { useJobAction } from "./use-job-action";

const IMAGE_ACCEPT = ".jpg,.jpeg,.png,.webp,.heic,.heif";

/** Choose the product photos for a job that came from a TikTok Shop link; the rest then runs on its own.
 *  The first photo picked is the main one (cut out); the others go to Flow as extra references. */
export default function PickImagePanel({ job, onChange }: { job: Job; onChange: (job: Job) => void }) {
  const { busy, error, run } = useJobAction(onChange);
  const candidates = job.source?.candidates ?? [];
  // Nothing pre-selected: the first photo clicked is the main one (a pre-selected first photo turned the
  // photo people actually wanted into an extra).
  const [selected, setSelected] = useState<string[]>([]);
  const [maxImages, setMaxImages] = useState(3);
  const [info, setInfo] = useState(job.product_info);
  useEffect(() => setInfo(job.product_info), [job.product_info]);
  useEffect(() => {
    api.settings().then((s) => setMaxImages(s.flow.max_ingredients)).catch(() => undefined);
  }, []);

  const toggle = (name: string) =>
    setSelected((current) =>
      current.includes(name) ? current.filter((n) => n !== name)
        : current.length < maxImages ? [...current, name] : current);

  return (
    <div className="review">
      {job.source && (
        <p className="muted">
          Từ <a href={job.source.url} target="_blank" rel="noreferrer">{job.source.title || job.source.url}</a>
          {" "}— bấm chọn tối đa {maxImages} ảnh. Ảnh số 1 là ảnh chính (được tách nền); các ảnh sau gửi kèm cho
          Flow làm tham khảo (góc khác, người mẫu mang thử...). Chọn xong tool tự chạy đến khi xuất video.
        </p>
      )}
      {candidates.length > 0 && (
        <div className="candidate-grid" role="listbox" aria-multiselectable="true" aria-label="Ảnh sản phẩm">
          {candidates.map((name) => {
            const order = selected.indexOf(name) + 1;
            return (
              <button key={name} role="option" aria-selected={order > 0}
                className={`candidate ${order ? "candidate-selected" : ""}`} onClick={() => toggle(name)}>
                <img src={fileUrl(job, `candidates/${name}`)} alt={`Ảnh ${name}`} loading="lazy" />
                {order > 0 && <span className="candidate-order">{order === 1 ? "1 · chính" : order}</span>}
              </button>
            );
          })}
        </div>
      )}
      <label className="field-label" htmlFor="product-info">Thông tin sản phẩm gửi kèm cho Claude (sửa được)</label>
      <textarea id="product-info" className="input" rows={3} value={info} onChange={(e) => setInfo(e.target.value)} />
      <div className="actions">
        <button className="btn btn-primary" disabled={busy || selected.length === 0}
          onClick={() => run(() => api.pick(job.id, { candidate: selected[0], extras: selected.slice(1), productInfo: info }))}>
          {selected.length > 1 ? `Bắt đầu với ${selected.length} ảnh` : "Bắt đầu với ảnh này"}
        </button>
        <FilePickButton label="Dùng ảnh của tôi" accept={IMAGE_ACCEPT} disabled={busy}
          onPick={(image) => run(() => api.pick(job.id, { image, productInfo: info }))} />
      </div>
      {error && <div className="error-text">{error}</div>}
    </div>
  );
}
