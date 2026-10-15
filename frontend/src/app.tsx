import { useEffect, useState } from "react";
import { api, type Settings } from "./api-client";
import FlowStatusBar from "./components/flow-status-bar";
import JobDetailPanel from "./components/job-detail-panel";
import JobList from "./components/job-list";
import UploadPanel from "./components/upload-panel";
import { useJobs } from "./use-jobs";

export default function App() {
  const { jobs, byId, upsert, connected } = useJobs();
  const [settings, setSettings] = useState<Settings | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  useEffect(() => {
    api.settings().then(setSettings).catch(() => undefined);
  }, []);

  // Auto-select the newest job that needs attention when nothing is selected.
  useEffect(() => {
    if (selectedId && byId[selectedId]) return;
    const pick = jobs.find((j) => j.status === "awaiting_review" || j.status === "failed") ?? jobs[0];
    if (pick) setSelectedId(pick.id);
  }, [jobs, byId, selectedId]);

  const selected = selectedId ? byId[selectedId] : undefined;

  return (
    <div className="app">
      <FlowStatusBar connected={connected} />
      <main className="layout">
        <aside className="sidebar">
          {settings && (
            <UploadPanel
              settings={settings}
              onCreated={(created) => {
                created.forEach(upsert);
                if (created[0]) setSelectedId(created[0].id);
              }}
            />
          )}
          <JobList jobs={jobs} selectedId={selectedId} onSelect={setSelectedId} />
        </aside>
        <section className="detail">
          {selected ? (
            <JobDetailPanel job={selected} onChange={upsert} />
          ) : (
            <div className="empty">Kéo ảnh sản phẩm vào khung bên trái để bắt đầu.</div>
          )}
        </section>
      </main>
    </div>
  );
}
