import { useState, useEffect, useCallback, useRef } from "react";
import UploadForm from "./components/UploadForm.jsx";
import StatusPanel from "./components/StatusPanel.jsx";
import ClipCard from "./components/ClipCard.jsx";

const POLL_INTERVAL = 2500; // ms

export default function App() {
  const [view, setView] = useState("upload"); // "upload" | "processing" | "results"
  const [jobId, setJobId] = useState(null);
  const [job, setJob] = useState(null);
  const [serverConfig, setServerConfig] = useState(null);
  const pollRef = useRef(null);

  // Carrega config do servidor ao iniciar
  useEffect(() => {
    fetch("/api/config")
      .then((r) => r.json())
      .then(setServerConfig)
      .catch(() => {}); // silencia erro se backend ainda não está rodando
  }, []);

  // Polling de status
  const startPolling = useCallback((id) => {
    if (pollRef.current) clearInterval(pollRef.current);

    pollRef.current = setInterval(async () => {
      try {
        const res = await fetch(`/api/status/${id}`);
        if (!res.ok) return;
        const data = await res.json();
        setJob(data);

        if (data.status === "done") {
          clearInterval(pollRef.current);
          setView("results");
        } else if (data.status === "error") {
          clearInterval(pollRef.current);
          // Mantém view "processing" para mostrar o erro
        }
      } catch (e) {
        console.error("Erro no polling:", e);
      }
    }, POLL_INTERVAL);
  }, []);

  useEffect(() => () => clearInterval(pollRef.current), []);

  const handleJobCreated = useCallback((id) => {
    setJobId(id);
    setJob({ job_id: id, status: "transcribing", progress: 5, message: "Iniciando..." });
    setView("processing");
    startPolling(id);
  }, [startPolling]);

  const handleReset = () => {
    clearInterval(pollRef.current);
    setView("upload");
    setJobId(null);
    setJob(null);
  };

  const clips = job?.clips || [];

  return (
    <>
      {/* Header */}
      <header className="header">
        <div className="logo">
          <div className="logo-icon">✂️</div>
          <span className="logo-text">Clip<span>Forge</span></span>
        </div>
        <span className="header-badge">Self-hosted · Local</span>
      </header>

      {/* Main */}
      <main className="main">
        {view === "upload" && (
          <>
            <div className="hero">
              <div className="section-label">Gerador de Clipes Virais</div>
              <h1>
                Transforme vídeos em<br />
                <em>Shorts prontos</em>
              </h1>
              <p>
                Upload ou URL → Transcrição → Análise por IA → Clipes verticais 9:16
                para YouTube Shorts, Reels e TikTok. Tudo local, sem enviar dados para fora.
              </p>
            </div>

            <UploadForm
              onJobCreated={handleJobCreated}
              serverConfig={serverConfig}
            />
          </>
        )}

        {view === "processing" && job && (
          <>
            <div className="hero" style={{ marginBottom: 32 }}>
              <div className="section-label">Processando</div>
              <h1>Analisando seu<br /><em>vídeo...</em></h1>
            </div>

            <StatusPanel job={job} onReset={handleReset} />
          </>
        )}

        {view === "results" && (
          <>
            <div className="results-header">
              <div>
                <div className="section-label">Resultado</div>
                <div className="results-title">
                  {clips.length} clipe{clips.length !== 1 ? "s" : ""} gerado{clips.length !== 1 ? "s" : ""}
                </div>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <span className="results-count">
                  Job: {jobId?.slice(0, 8)}
                </span>
                <button className="btn btn-ghost" onClick={handleReset} style={{ fontSize: "0.82rem", padding: "8px 14px" }}>
                  ↩ Novo vídeo
                </button>
              </div>
            </div>

            {clips.length === 0 ? (
              <div className="empty-state">
                <div className="empty-icon">😕</div>
                <p>Nenhum clipe encontrado. Tente com outro vídeo ou ajuste as configurações no .env.</p>
              </div>
            ) : (
              <div className="clips-grid">
                {clips.map((clip, i) => (
                  <ClipCard key={clip.id || i} clip={clip} index={i} />
                ))}
              </div>
            )}

            <div className="divider" />

            <StatusPanel job={job} onReset={handleReset} />
          </>
        )}
      </main>
    </>
  );
}
