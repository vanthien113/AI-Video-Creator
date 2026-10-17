// Types and fetch helpers for the FastAPI backend.

export type JobStatus = "queued" | "running" | "awaiting_review" | "failed" | "done" | "cancelled";
export type Gate = "cutout" | "prompt" | "flow_video";
export type JobGate = Gate | "pick_image";
export type PostMode = "now" | "schedule";

export interface Job {
  id: string;
  name: string;
  input_file: string;
  created_at: string;
  status: JobStatus;
  current_step: string;
  gate: JobGate | null;
  auto_gates: Record<Gate, boolean>;
  note: string;
  product_info: string;
  source: { url: string; title: string; description: string; candidates: string[]; product_id: string } | null;
  post: { mode: PostMode | null; scheduled_for: string | null; submitted_at: string | null; done_at: string | null };
  telegram: { chat_id: number; message_id: number | null; preview_sent: boolean; file_sent: boolean } | null;
  feedback: string;
  cutout_model_index: number;
  progress: number;
  message: string;
  history: { step: string; started_at: string; finished_at: string | null; outcome: string }[];
  flow: { project_url: string | null; submitted_at: string | null; video_ref: string | null };
  error: { step: string; reason: string; screenshot: string | null } | null;
  export_path: string | null;
  prompt: { prompt: string; summary: string } | null;
}

export interface Settings {
  auto_gates: Record<Gate, boolean>;
  export_dir: string;
  rules_file: string;
  flow: { model: string; aspect_ratio: string; max_ingredients: number };
}

export interface TelegramStatus {
  state: "off" | "no_token" | "no_user" | "starting" | "listening" | "error";
  message: string;
}

export interface FlowStatus {
  running: boolean;
  state: "closed" | "login_required" | "ready" | "open";
  tabs: string[];
}

export const STEPS = [
  "fetch_source", "cutout", "upscale", "prompt", "flow_generate", "flow_download", "enhance", "export", "hashtags",
  "send_telegram", "tiktok_draft", "tiktok_post",
];
/** Only link jobs read TikTok, only Telegram jobs send the result back, and posting shows once asked for. */
export const stepsFor = (job: Job) =>
  STEPS.filter((s) => (s !== "fetch_source" || job.source) && (s !== "send_telegram" || job.telegram)
    && (s !== "tiktok_post" || job.post.mode));
export const STEP_LABELS: Record<string, string> = {
  fetch_source: "Đọc TikTok",
  cutout: "Tách nền",
  upscale: "Upscale 2K",
  prompt: "Prompt",
  flow_generate: "Flow sinh",
  flow_download: "Tải video",
  enhance: "Nâng 60fps",
  export: "Xuất file",
  hashtags: "Hashtag",
  send_telegram: "Gửi Telegram",
  tiktok_draft: "Lưu nháp TikTok",
  tiktok_post: "Đăng TikTok",
};
export const STATUS_LABELS: Record<JobStatus, string> = {
  queued: "Chờ lượt",
  running: "Đang chạy",
  awaiting_review: "Chờ duyệt",
  failed: "Lỗi",
  done: "Xong",
  cancelled: "Đã huỷ",
};
export const GATE_LABELS: Record<JobGate, string> = {
  pick_image: "Chờ chọn ảnh",
  cutout: "Duyệt ảnh tách nền",
  prompt: "Duyệt prompt",
  flow_video: "Duyệt video Flow",
};

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init);
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      /* body was not JSON */
    }
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return res.json() as Promise<T>;
}

const post = <T>(url: string, body?: FormData | object) =>
  request<T>(url, {
    method: "POST",
    ...(body instanceof FormData
      ? { body }
      : { body: JSON.stringify(body ?? {}), headers: { "Content-Type": "application/json" } }),
  });

export const api = {
  settings: () => request<Settings>("/api/settings"),
  listJobs: () => request<Job[]>("/api/jobs"),
  getJob: (id: string) => request<Job>(`/api/jobs/${id}`),
  createJobs: (files: File[], note: string, autoGates: Record<Gate, boolean>) => {
    const form = new FormData();
    files.forEach((f) => form.append("images", f));
    form.append("note", note);
    form.append("auto_gates", JSON.stringify(autoGates));
    return post<Job[]>("/api/jobs", form);
  },
  approve: (id: string, prompt?: string) => post<Job>(`/api/jobs/${id}/approve`, { prompt }),
  retry: (id: string, step: string, opts: { feedback?: string; nextCutoutModel?: boolean; image?: File } = {}) => {
    const form = new FormData();
    form.append("step", step);
    form.append("feedback", opts.feedback ?? "");
    form.append("next_cutout_model", String(Boolean(opts.nextCutoutModel)));
    if (opts.image) form.append("image", opts.image);
    return post<Job>(`/api/jobs/${id}/retry`, form);
  },
  continueJob: (id: string) => post<Job>(`/api/jobs/${id}/continue`),
  createFromLink: (url: string) => post<Job>("/api/links", { url }),
  pick: (id: string, opts: { candidate?: string; extras?: string[]; productInfo?: string; image?: File }) => {
    const form = new FormData();
    if (opts.candidate) form.append("candidate", opts.candidate);
    for (const name of opts.extras ?? []) form.append("extra", name);
    if (opts.productInfo !== undefined) form.append("product_info", opts.productInfo);
    if (opts.image) form.append("image", opts.image);
    return post<Job>(`/api/jobs/${id}/pick`, form);
  },
  telegramStatus: () => request<TelegramStatus>("/api/telegram/status"),
  manualVideo: (id: string, video: File) => {
    const form = new FormData();
    form.append("video", video);
    return post<Job>(`/api/jobs/${id}/manual-video`, form);
  },
  cancel: (id: string) => post<Job>(`/api/jobs/${id}/cancel`),
  postOnTikTok: (id: string, mode: PostMode) => post<Job>(`/api/jobs/${id}/post`, { mode }),
  flowStatus: () => request<FlowStatus>("/api/flow/status"),
  launchChrome: () => post<{ launched: boolean; message: string }>("/api/flow/launch-chrome"),
  openExportDir: () => post<{ ok: boolean }>("/api/open-export-dir"),
};

/** URL of a file in the job folder; `version` busts the browser cache after a step re-runs. */
export function fileUrl(job: Job, name: string): string {
  return `/api/jobs/${job.id}/files/${name}?v=${job.history.length}`;
}

/** Picture for the job list: the chosen image, else the first product photo from TikTok. */
export function thumbUrl(job: Job): string | null {
  if (job.input_file) return fileUrl(job, job.input_file);
  const first = job.source?.candidates[0];
  return first ? fileUrl(job, `candidates/${first}`) : null;
}

export const displayName = (job: Job) => job.source?.title || job.name;

const WEEKDAYS = ["Chủ nhật", "thứ Hai", "thứ Ba", "thứ Tư", "thứ Năm", "thứ Sáu", "thứ Bảy"];
const pad = (n: number) => String(n).padStart(2, "0");

/** "✅ Đã đăng TikTok lúc 10:32" / "🗓 Đã lên lịch TikTok: 19:00 Chủ nhật 18/10"; null until TikTok has the post. */
export function postResult(job: Job): string | null {
  const { mode, scheduled_for, done_at } = job.post;
  if (!done_at) return null;
  if (mode === "schedule" && scheduled_for) {
    const d = new Date(scheduled_for); // no offset in the string: read as local time, like the backend wrote it
    return `🗓 Đã lên lịch TikTok: ${pad(d.getHours())}:${pad(d.getMinutes())} ${WEEKDAYS[d.getDay()]} `
      + `${pad(d.getDate())}/${pad(d.getMonth() + 1)}`;
  }
  const d = new Date(done_at);
  return `✅ Đã đăng TikTok lúc ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}
