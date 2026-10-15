import { useEffect, useState } from "react";
import { api, type FlowStatus, type TelegramStatus } from "../api-client";

const FLOW_TEXT: Record<FlowStatus["state"], string> = {
  closed: "Chrome cho Flow chưa mở",
  login_required: "Cần đăng nhập Google trong cửa sổ Chrome",
  ready: "Flow sẵn sàng",
  open: "Chrome đang mở (chưa ở trang Flow)",
};

const TELEGRAM_TEXT: Record<TelegramStatus["state"], string> = {
  off: "Telegram tắt",
  no_token: "Telegram chưa cài",
  no_user: "Telegram chờ ID",
  starting: "Telegram đang kết nối",
  listening: "Telegram đang nghe",
  error: "Telegram lỗi",
};

const dotClass = (ok: boolean, bad: boolean) => `dot dot-${ok ? "ok" : bad ? "bad" : "warn"}`;

export default function FlowStatusBar({ connected }: { connected: boolean }) {
  const [flow, setFlow] = useState<FlowStatus | null>(null);
  const [telegram, setTelegram] = useState<TelegramStatus | null>(null);
  const [notice, setNotice] = useState("");

  useEffect(() => {
    const load = () => {
      api.flowStatus().then(setFlow).catch(() => setFlow(null));
      api.telegramStatus().then(setTelegram).catch(() => setTelegram(null));
    };
    load();
    const timer = window.setInterval(load, 5000);
    return () => window.clearInterval(timer);
  }, []);

  const launch = async () => {
    try {
      setNotice((await api.launchChrome()).message);
    } catch (err) {
      setNotice((err as Error).message);
    }
  };

  const flowState = flow?.state ?? "closed";
  const tgState = telegram?.state ?? "off";
  return (
    <header className="topbar">
      <div className="brand">AI Video Creator</div>
      <div className="topbar-status">
        <span className={dotClass(connected, !connected)} title={connected ? "Đã kết nối server" : "Mất kết nối server"} />
        <span className={dotClass(flowState === "ready", flowState === "closed")} />
        <span>{FLOW_TEXT[flowState]}</span>
        {flowState === "closed" && (
          <button className="btn btn-small" onClick={launch}>Mở Chrome cho Flow</button>
        )}
        <span className={dotClass(tgState === "listening", tgState === "error")} />
        <span title={telegram?.message || ""}>{TELEGRAM_TEXT[tgState]}</span>
        {notice && <span className="muted">{notice}</span>}
      </div>
    </header>
  );
}
