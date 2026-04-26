import { useState, useRef } from "react";

const TRANSCRIPTION_OPTIONS = [
  { value: "whisper",    label: "🎙 Whisper (local)" },
  { value: "assemblyai", label: "☁️ AssemblyAI (API)" },
];

const LLM_OPTIONS = [
  { value: "ollama",     label: "🦙 Ollama (local)" },
  { value: "gemini",     label: "✨ Gemini (API)" },
  { value: "openrouter", label: "🌐 OpenRouter (API)" },
];

const CAPTION_STYLE_OPTIONS = [
  { value: "tiktok", label: "🎵 TikTok (branco + borda)" },
  { value: "bold",   label: "💥 Bold (amarelo uppercase)" },
];

export default function UploadForm({ onJobCreated, serverConfig }) {
  const [tab, setTab] = useState("file");
  const [file, setFile] = useState(null);
  const [url, setUrl] = useState("");
  const [dragOver, setDragOver] = useState(false);

  // Providers
  const [transcriptionProvider, setTranscriptionProvider] = useState(
    serverConfig?.transcription_provider || "whisper"
  );
  const [llmProvider, setLlmProvider] = useState(
    serverConfig?.llm_provider || "ollama"
  );

  // Viral mode
  const [viralEnabled, setViralEnabled]     = useState(
    serverConfig?.viral_edit_enabled ?? false
  );
  const [faceDetection, setFaceDetection]   = useState(
    serverConfig?.viral_face_detection ?? true
  );
  const [addCaptions, setAddCaptions]       = useState(
    serverConfig?.viral_add_captions ?? true
  );
  const [captionStyle, setCaptionStyle]     = useState(
    serverConfig?.viral_caption_style || "tiktok"
  );
  const [gameplayFile, setGameplayFile]     = useState(null);
  const [gameplayPath, setGameplayPath]     = useState(null); // path no servidor após upload
  const [gameplayLoading, setGameplayLoading] = useState(false);

  // Center Blur state
  const [blurEnabled, setBlurEnabled]       = useState(
    serverConfig?.center_blur_enabled ?? false
  );
  const [blurRatio, setBlurRatio]           = useState(
    serverConfig?.center_blur_ratio ?? 0.70
  );
  const [blurStrength, setBlurStrength]     = useState(
    serverConfig?.center_blur_strength ?? 20
  );
  const [blurCaptions, setBlurCaptions]     = useState(true);
  const [blurCaptionStyle, setBlurCaptionStyle] = useState("tiktok");

  const [loading, setLoading] = useState(false);
  const [error, setError]     = useState("");
  const fileRef     = useRef(null);
  const gameplayRef = useRef(null);

  // ── Handlers ────────────────────────────────────────────────────────────────

  const handleFile = (f) => {
    if (!f) return;
    const allowed = ["mp4", "mov", "avi", "mkv", "webm", "m4v"];
    const ext = f.name.split(".").pop().toLowerCase();
    if (!allowed.includes(ext)) {
      setError(`Formato não suportado: .${ext}`);
      return;
    }
    setError("");
    setFile(f);
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setDragOver(false);
    handleFile(e.dataTransfer.files[0]);
  };

  const handleGameplayFile = async (f) => {
    if (!f) return;
    setGameplayFile(f);
    setGameplayPath(null);
    // Faz upload imediato do gameplay para obter o path do servidor
    // (precisamos do job_id, então guardamos o File e fazemos upload depois)
    // O upload real acontece em handleSubmit após criar o job
  };

  const formatSize = (b) =>
    b < 1_048_576 ? `${(b / 1024).toFixed(0)} KB` : `${(b / 1_048_576).toFixed(1)} MB`;

  // ── Submit ───────────────────────────────────────────────────────────────────

  const handleSubmit = async () => {
    setError("");
    if (tab === "file" && !file)      { setError("Selecione um arquivo de vídeo."); return; }
    if (tab === "url" && !url.trim()) { setError("Informe a URL do vídeo."); return; }

    setLoading(true);
    try {
      let jobId;

      // ── Passo 1: criar job ─────────────────────────────────────────────────
      if (tab === "file") {
        const form = new FormData();
        form.append("file", file);
        const res = await fetch("/api/upload", { method: "POST", body: form });
        if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || "Erro no upload.");
        jobId = (await res.json()).job_id;
      }

      // ── Passo 2: upload gameplay (se viral + arquivo de gameplay) ──────────
      let bgPath = null;
      if (viralEnabled && gameplayFile && tab === "file" && jobId) {
        setGameplayLoading(true);
        try {
          const gf = new FormData();
          gf.append("file", gameplayFile);
          const gr = await fetch(`/api/gameplay/${jobId}`, { method: "POST", body: gf });
          if (gr.ok) {
            bgPath = (await gr.json()).gameplay_path;
          }
        } catch (e) {
          console.warn("Erro no upload do gameplay:", e);
        } finally {
          setGameplayLoading(false);
        }
      }

      // ── Passo 3: montar viral options ──────────────────────────────────────
      const viral = viralEnabled ? {
        enabled: true,
        face_detection: faceDetection,
        add_captions: addCaptions,
        caption_style: captionStyle,
        background_video_path: bgPath,
      } : null;

      // ── Passo 3b: montar center_blur options ─────────────────────────────────
      const center_blur = blurEnabled ? {
        enabled: true,
        video_height_ratio: blurRatio,
        blur_strength: blurStrength,
        add_captions: blurCaptions,
        caption_style: blurCaptionStyle,
      } : null;

      // ── Passo 4: iniciar análise ───────────────────────────────────────────
      if (tab === "file") {
        const r2 = await fetch(`/api/analyze/${jobId}`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            transcription_provider: transcriptionProvider,
            llm_provider: llmProvider,
            viral,
            center_blur,
          }),
        });
        if (!r2.ok) throw new Error((await r2.json().catch(() => ({}))).detail || "Erro ao iniciar análise.");

      } else {
        // URL: pipeline encadeado automaticamente
        const r = await fetch("/api/upload-url", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            url: url.trim(),
            transcription_provider: transcriptionProvider,
            llm_provider: llmProvider,
            viral,
            center_blur,
          }),
        });
        if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || "Erro ao processar URL.");
        jobId = (await r.json()).job_id;
      }

      onJobCreated(jobId);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const canSubmit = !loading && (tab === "file" ? !!file : !!url.trim());
  const anyEffect  = viralEnabled || blurEnabled;

  // ── Render ───────────────────────────────────────────────────────────────────

  return (
    <div>
      {/* ── Fonte do vídeo ── */}
      <div className="card" style={{ animationDelay: "0.1s" }}>
        <div className="card-title"><span className="step-num">1</span>Fonte do Vídeo</div>

        <div className="source-tabs">
          <button className={`source-tab${tab === "file" ? " active" : ""}`} onClick={() => setTab("file")}>
            📁 Upload de Arquivo
          </button>
          <button className={`source-tab${tab === "url" ? " active" : ""}`} onClick={() => setTab("url")}>
            🔗 URL / Link
          </button>
        </div>

        {tab === "file" ? (
          file ? (
            <div className="selected-file">
              <span className="file-icon">🎬</span>
              <span className="file-name">{file.name}</span>
              <span className="file-size">{formatSize(file.size)}</span>
              <button className="reset-btn" onClick={() => setFile(null)}>✕</button>
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
              <input ref={fileRef} type="file" accept="video/*"
                onChange={(e) => handleFile(e.target.files[0])} style={{ display: "none" }} />
            </div>
          )
        ) : (
          <input
            className="url-input"
            type="url"
            placeholder="https://youtube.com/watch?v=..."
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && canSubmit && handleSubmit()}
          />
        )}
      </div>

      {/* ── Provedores de IA ── */}
      <div className="card" style={{ animationDelay: "0.15s" }}>
        <div className="card-title"><span className="step-num">2</span>Provedores de IA</div>
        <div className="provider-grid">
          <div className="provider-group">
            <label>Transcrição</label>
            <select className="provider-select" value={transcriptionProvider}
              onChange={(e) => setTranscriptionProvider(e.target.value)}>
              {TRANSCRIPTION_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          </div>
          <div className="provider-group">
            <label>Análise de Conteúdo</label>
            <select className="provider-select" value={llmProvider}
              onChange={(e) => setLlmProvider(e.target.value)}>
              {LLM_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          </div>
        </div>
      </div>

      {/* ── Modo Viral ── */}
      <div className={`card viral-card${viralEnabled ? " viral-card--active" : ""}`} style={{ animationDelay: "0.2s" }}>
        <div className="viral-header">
          <div style={{ flex: 1 }}>
            <div className="card-title" style={{ marginBottom: 4 }}>
              <span className="step-num" style={{ background: viralEnabled ? "#ff3b6b" : undefined }}>3</span>
              Modo Viral
              <span className="viral-badge">TikTok / Reels</span>
            </div>
            <p className="viral-desc">
              Layout dual-panel, detecção de rosto e legendas estilo TikTok automáticas.
            </p>
          </div>
          {/* Toggle switch */}
          <button
            className={`toggle-switch${viralEnabled ? " toggle-switch--on" : ""}`}
            onClick={() => setViralEnabled(v => !v)}
            aria-label="Ativar modo viral"
          >
            <span className="toggle-knob" />
          </button>
        </div>

        {viralEnabled && (
          <div className="viral-options">
            <div className="viral-options-grid">
              {/* Caption style */}
              <div className="provider-group">
                <label>Estilo de Legenda</label>
                <select className="provider-select" value={captionStyle}
                  onChange={(e) => setCaptionStyle(e.target.value)}>
                  {CAPTION_STYLE_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                </select>
              </div>

              {/* Checkboxes */}
              <div className="viral-checks">
                <label className="viral-check">
                  <input type="checkbox" checked={faceDetection}
                    onChange={(e) => setFaceDetection(e.target.checked)} />
                  <span>Detecção de rosto</span>
                </label>
                <label className="viral-check">
                  <input type="checkbox" checked={addCaptions}
                    onChange={(e) => setAddCaptions(e.target.checked)} />
                  <span>Legendas automáticas</span>
                </label>
              </div>
            </div>

            {/* Gameplay upload (só para arquivo, não para URL pois não temos job_id ainda) */}
            <div className="gameplay-section">
              <div className="gameplay-label">
                🎮 Vídeo de fundo (gameplay)
                <span className="optional-tag">opcional</span>
              </div>
              <p className="gameplay-hint">
                Aparece no painel inferior. Se não enviar, usa loop do próprio vídeo com blur.
              </p>
              {gameplayFile ? (
                <div className="selected-file" style={{ marginTop: 10 }}>
                  <span className="file-icon">🎮</span>
                  <span className="file-name">{gameplayFile.name}</span>
                  <span className="file-size">{formatSize(gameplayFile.size)}</span>
                  <button className="reset-btn" onClick={() => { setGameplayFile(null); setGameplayPath(null); }}>✕</button>
                </div>
              ) : (
                <div
                  className="drop-zone drop-zone--sm"
                  onClick={() => gameplayRef.current?.click()}
                >
                  <span style={{ fontSize: "1.4rem" }}>🎮</span>
                  <p style={{ fontSize: "0.82rem" }}><strong>Adicionar gameplay</strong></p>
                  <input ref={gameplayRef} type="file" accept="video/*"
                    onChange={(e) => handleGameplayFile(e.target.files[0])}
                    style={{ display: "none" }} />
                </div>
              )}
            </div>
          </div>
        )}
      </div>


      {/* ── Center Blur Layout ── */}
      <div className={`card blur-card${blurEnabled ? " blur-card--active" : ""}`} style={{ animationDelay: "0.25s" }}>
        <div className="viral-header">
          <div style={{ flex: 1 }}>
            <div className="card-title" style={{ marginBottom: 4 }}>
              <span className="step-num" style={{ background: blurEnabled ? "#38bdf8" : undefined }}>4</span>
              Fundo Desfocado
              <span className="blur-badge">Center Blur</span>
            </div>
            <p className="viral-desc">
              Vídeo central nítido com o mesmo vídeo desfocado preenchendo o fundo. Visual limpo e 9:16.
            </p>
          </div>
          <button
            className={`toggle-switch${blurEnabled ? " toggle-switch--blur-on" : ""}`}
            onClick={() => setBlurEnabled(v => !v)}
            aria-label="Ativar fundo desfocado"
          >
            <span className="toggle-knob" />
          </button>
        </div>

        {blurEnabled && (
          <div className="viral-options">
            <div className="viral-options-grid">
              {/* Altura do vídeo central */}
              <div className="provider-group">
                <label>Altura do vídeo central — {Math.round(blurRatio * 100)}%</label>
                <input
                  type="range" min="0.40" max="0.90" step="0.05"
                  value={blurRatio}
                  onChange={(e) => setBlurRatio(parseFloat(e.target.value))}
                  className="blur-slider"
                />
              </div>

              {/* Força do blur */}
              <div className="provider-group">
                <label>Intensidade do desfoque — {blurStrength}</label>
                <input
                  type="range" min="5" max="60" step="5"
                  value={blurStrength}
                  onChange={(e) => setBlurStrength(parseInt(e.target.value))}
                  className="blur-slider"
                />
              </div>

              {/* Caption style */}
              <div className="provider-group">
                <label>Estilo de Legenda</label>
                <select className="provider-select" value={blurCaptionStyle}
                  onChange={(e) => setBlurCaptionStyle(e.target.value)}>
                  <option value="tiktok">🎵 TikTok (branco + borda)</option>
                  <option value="bold">💥 Bold (amarelo uppercase)</option>
                </select>
              </div>

              {/* Toggle legendas */}
              <div className="viral-checks" style={{ justifyContent: "flex-start", paddingTop: 20 }}>
                <label className="viral-check">
                  <input type="checkbox" checked={blurCaptions}
                    onChange={(e) => setBlurCaptions(e.target.checked)} />
                  <span>Legendas automáticas</span>
                </label>
              </div>
            </div>

            {/* Preview visual do ratio */}
            <div className="blur-preview">
              <div className="blur-preview-bg" />
              <div className="blur-preview-fg" style={{ height: `${blurRatio * 100}%` }} />
              <span className="blur-preview-label">{Math.round(blurRatio * 100)}%</span>
            </div>
          </div>
        )}
      </div>

      {/* Erro */}
      {error && (
        <div className="error-box" style={{ marginBottom: 16 }}>
          <span>⚠️</span><span>{error}</span>
        </div>
      )}

      {/* Submit */}
      <button className="btn btn-primary" onClick={handleSubmit} disabled={!canSubmit}
        style={{ animationDelay: "0.25s" }}>
        {loading ? (
          <><span style={{ display: "inline-block", animation: "spin 1s linear infinite" }}>⟳</span>
            {gameplayLoading ? "Enviando gameplay..." : "Enviando..."}</>
        ) : (
          <>{viralEnabled && blurEnabled ? "🔥🌫 Gerar Clipes (Viral + Blur)" : viralEnabled ? "🔥 Gerar Clipes Virais" : blurEnabled ? "🌫 Gerar Clipes com Blur" : "✂️ Analisar e Gerar Clipes"}</>
        )}
      </button>
    </div>
  );
}
