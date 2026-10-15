import { useState, type DragEvent } from "react";
import { api, type Gate, type Job, type Settings } from "../api-client";

const ACCEPT = ".jpg,.jpeg,.png,.webp,.heic,.heif";
const GATES: Gate[] = ["cutout", "prompt", "flow_video"];
const AUTO_LABELS: Record<Gate, string> = { cutout: "Ảnh tách nền", prompt: "Prompt", flow_video: "Video Flow" };

export default function UploadPanel({ settings, onCreated }: { settings: Settings; onCreated: (jobs: Job[]) => void }) {
  const [files, setFiles] = useState<File[]>([]);
  const [note, setNote] = useState("");
  const [autoGates, setAutoGates] = useState<Record<Gate, boolean>>(settings.auto_gates);
  const [dragging, setDragging] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [link, setLink] = useState("");

  const addLink = async () => {
    setBusy(true);
    setError("");
    try {
      onCreated([await api.createFromLink(link.trim())]);
      setLink("");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const addFiles = (list: FileList | null) => {
    if (!list) return;
    const images = Array.from(list).filter((f) => /\.(jpe?g|png|webp|heic|heif)$/i.test(f.name));
    setFiles((prev) => [...prev, ...images]);
  };

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setDragging(false);
    addFiles(e.dataTransfer.files);
  };

  const start = async () => {
    setBusy(true);
    setError("");
    try {
      onCreated(await api.createJobs(files, note, autoGates));
      setFiles([]);
      setNote("");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="card upload">
      <label
        className={`dropzone ${dragging ? "dropzone-active" : ""}`}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
      >
        <input type="file" accept={ACCEPT} multiple hidden onChange={(e) => addFiles(e.target.files)} />
        <strong>Kéo thả ảnh sản phẩm vào đây</strong>
        <span className="muted">hoặc bấm để chọn — mỗi ảnh thành một video</span>
      </label>

      <div className="link-row">
        <input className="input" placeholder="Hoặc dán link sản phẩm TikTok Shop" value={link}
          onChange={(e) => setLink(e.target.value)} onKeyDown={(e) => e.key === "Enter" && link.trim() && addLink()} />
        <button className="btn" disabled={!link.trim() || busy} onClick={addLink}>Tạo từ link</button>
      </div>

      {files.length > 0 && (
        <ul className="file-chips">
          {files.map((f, i) => (
            <li key={`${f.name}-${i}`}>
              {f.name}
              <button className="chip-remove" onClick={() => setFiles(files.filter((_, j) => j !== i))} aria-label="Bỏ ảnh">
                ×
              </button>
            </li>
          ))}
        </ul>
      )}

      <textarea
        className="input"
        rows={2}
        placeholder="Ghi chú cho prompt (tuỳ chọn), ví dụ: chủ đề Tết, tông đỏ vàng"
        value={note}
        onChange={(e) => setNote(e.target.value)}
      />

      <fieldset className="gates">
        <legend>Tự động chạy tiếp, không dừng chờ duyệt:</legend>
        {GATES.map((gate) => (
          <label key={gate} className="checkbox">
            <input
              type="checkbox"
              checked={autoGates[gate]}
              onChange={(e) => setAutoGates({ ...autoGates, [gate]: e.target.checked })}
            />
            {AUTO_LABELS[gate]}
          </label>
        ))}
      </fieldset>

      {error && <div className="error-text">{error}</div>}
      <button className="btn btn-primary" disabled={!files.length || busy} onClick={start}>
        {busy ? "Đang tải lên…" : `Bắt đầu${files.length ? ` (${files.length} ảnh)` : ""}`}
      </button>
    </div>
  );
}
