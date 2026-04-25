import { useState, useRef } from "react";

const TRANSCRIPTION_OPTIONS = [
  { value: "whisper",    label: "🎙 Whisper (local)" },
  { value: "assemblyai", label: "☁️ AssemblyAI (API)" },
];

const LLM_OPTIONS = [
  { value: "ollama",      label: "🦙 Ollama (local)" },
  { value: "gemini",      label: "✨ Gemini (API)" },
  { value: "openrouter",  label: "🌐 OpenRouter (API)" },
];

export default function UploadForm({ onJobCreated, serverConfig }) {
  const [tab, setTab] = useState("file"); // "file" | "url"
  const [file, setFile] = useState(null);
  const [url, setUrl] = useState("");
  const [dragOver, setDragOver] = useState(false);
  const [transcriptionProvider, setTranscriptionProvider] = useState(
    serverConfig?.transcription_provider || "whisper"
  );
  const [llmProvider, setLlmProvider] = useState(
    serverConfig?.llm_provider || "ollama"
  );
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const fileRef = useRef(null);

  const handleFile = (f) => {
    if (!f) return;
    const allowed = ["mp4", "mov", "avi", "mkv", "webm", "m4v"];
    const ext = f.name.split(".").pop().toLowerCase();
    if (!allowed.includes(ext)) {
      setError(`Formato não suportado: .${ext}. Use: ${allowed.join(", ")}`);
      return;
    }
    setError("");
    setFile(f);
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setDragOver(false);
    const f = e.dataTransfer.files[0];
    if (f) handleFile(f);
  };

  const formatSize = (bytes) => {
    if (bytes < 1_048_576) return `${(bytes / 1024).toFixed(0)} KB`;
    return `${(bytes / 1_048_576).toFixed(1)} MB`;
  };

  const handleSubmit = async () => {
    setError("");

    if (tab === "file" && !file) {
      setError("Selecione um arquivo de vídeo.");
      return;
    }
    if (tab === "url" && !url.trim()) {
      setError("Informe a URL do vídeo.");
      return;
    }

    setLoading(true);
    try {
      let jobId;

      if (tab === "file") {
        // ── Fluxo de arquivo: upload → analyze (dois passos) ───────────────
        const form = new FormData();
        form.append("file", file);
        const res = await fetch("/api/upload", { method: "POST", body: form });
        if (!res.ok) {
          const err = await res.json().catch(() => ({}));
          throw new Error(err.detail || "Erro no upload.");
        }
        const data = await res.json();
        jobId = data.job_id;

        // Dispara análise separada após upload concluído
        const res2 = await fetch(`/api/analyze/${jobId}`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            transcription_provider: transcriptionProvider,
            llm_provider: llmProvider,
          }),
        });
        if (!res2.ok) {
          const err = await res2.json().catch(() => ({}));
          throw new Error(err.detail || "Erro ao iniciar análise.");
        }

      } else {
        // ── Fluxo de URL: pipeline encadeado automaticamente no backend ────
        // O backend baixa o vídeo e já inicia a análise sem passo extra.
        const res = await fetch("/api/upload-url", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            url: url.trim(),
            transcription_provider: transcriptionProvider,
            llm_provider: llmProvider,
          }),
        });
        if (!res.ok) {
          const err = await res.json().catch(() => ({}));
          throw new Error(err.detail || "Erro ao processar a URL.");
        }
        const data = await res.json();
        jobId = data.job_id;
      }

      onJobCreated(jobId);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const canSubmit = !loading && (tab === "file" ? !!file : !!url.trim());

  return (
    <div>
      {/* Source Selection */}
      <div className="card" style={{ animationDelay: "0.1s" }}>
        <div className="card-title">
          <span className="step-num">1</span>
          Fonte do Vídeo
        </div>

        <div className="source-tabs">
          <button
            className={`source-tab${tab === "file" ? " active" : ""}`}
            onClick={() => setTab("file")}
          >
            📁 Upload de Arquivo
          </button>
          <button
            className={`source-tab${tab === "url" ? " active" : ""}`}
            onClick={() => setTab("url")}
          >
            🔗 URL / Link
          </button>
        </div>

        {tab === "file" ? (
          file ? (
            <div className="selected-file">
              <span className="file-icon">🎬</span>
              <span className="file-name">{file.name}</span>
              <span className="file-size">{formatSize(file.size)}</span>
              <button
                className="reset-btn"
                onClick={() => setFile(null)}
                title="Remover"
              >
                ✕
              </button>
            </div>
          ) : (
            <div
              className={`drop-zone${dragOver ? " drag-over" : ""}`}
              onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
              onDragLeave={() => setDragOver(false)}
              onDrop={handleDrop}
              onClick={() => fileRef.current?.click()}
            >
              <span className="drop-icon">📽️</span>
              <p><strong>Clique para selecionar</strong> ou arraste aqui</p>
              <p className="file-hint">MP4, MOV, AVI, MKV, WebM · Máx. 2 GB</p>
              <input
                ref={fileRef}
                type="file"
                accept="video/*"
                onChange={(e) => handleFile(e.target.files[0])}
                style={{ display: "none" }}
              />
            </div>
          )
        ) : (
          <div className="url-input-wrap">
            <input
              className="url-input"
              type="url"
              placeholder="https://youtube.com/watch?v=... ou qualquer URL de vídeo"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && canSubmit && handleSubmit()}
            />
          </div>
        )}
      </div>

      {/* Providers */}
      <div className="card" style={{ animationDelay: "0.15s" }}>
        <div className="card-title">
          <span className="step-num">2</span>
          Provedores de IA
        </div>

        <div className="provider-grid">
          <div className="provider-group">
            <label>Transcrição</label>
            <select
              className="provider-select"
              value={transcriptionProvider}
              onChange={(e) => setTranscriptionProvider(e.target.value)}
            >
              {TRANSCRIPTION_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          </div>
          <div className="provider-group">
            <label>Análise de Conteúdo</label>
            <select
              className="provider-select"
              value={llmProvider}
              onChange={(e) => setLlmProvider(e.target.value)}
            >
              {LLM_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          </div>
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="error-box" style={{ marginBottom: 16 }}>
          <span>⚠️</span>
          <span>{error}</span>
        </div>
      )}

      {/* Submit */}
      <button
        className="btn btn-primary"
        onClick={handleSubmit}
        disabled={!canSubmit}
        style={{ animationDelay: "0.2s" }}
      >
        {loading ? (
          <>
            <span style={{ display: "inline-block", animation: "spin 1s linear infinite" }}>⟳</span>
            {tab === "url" ? "Enviando URL..." : "Enviando arquivo..."}
          </>
        ) : (
          <>✂️ Analisar e Gerar Clipes</>
        )}
      </button>
    </div>
  );
}
