const STEPS = [
  { key: "downloading",  label: "Download",    icon: "⬇️" },
  { key: "transcribing", label: "Transcrição", icon: "🎙" },
  { key: "analyzing",    label: "Análise IA",  icon: "🧠" },
  { key: "processing",   label: "Corte",       icon: "✂️" },
  { key: "done",         label: "Pronto",      icon: "✅" },
];

const STATUS_META = {
  downloading:  { icon: "⬇️", cls: "pulse",    bg: "rgba(99,102,241,0.12)",  color: "#818cf8" },
  transcribing: { icon: "🎙", cls: "pulse",    bg: "rgba(200,241,53,0.10)",  color: "#c8f135" },
  analyzing:    { icon: "🧠", cls: "pulse",    bg: "rgba(200,241,53,0.10)",  color: "#c8f135" },
  processing:   { icon: "✂️", cls: "spinning", bg: "rgba(200,241,53,0.10)",  color: "#c8f135" },
  done:         { icon: "✅", cls: "",         bg: "rgba(74,222,128,0.12)",  color: "#4ade80" },
  error:        { icon: "❌", cls: "",         bg: "rgba(255,77,109,0.12)",  color: "#ff4d6d" },
  idle:         { icon: "⏳", cls: "pulse",    bg: "rgba(200,200,200,0.08)", color: "#7a7a8e" },
};

const STEP_ORDER = ["downloading", "transcribing", "analyzing", "processing", "done"];

function getStepState(stepKey, currentStatus) {
  if (currentStatus === "error") return "error";
  const currentIdx = STEP_ORDER.indexOf(currentStatus);
  const stepIdx    = STEP_ORDER.indexOf(stepKey);
  if (stepIdx < currentIdx)  return "done";
  if (stepIdx === currentIdx) return "active";
  return "pending";
}

export default function StatusPanel({ job, onReset }) {
  const { status, progress, message, error } = job;
  const meta = STATUS_META[status] || STATUS_META.idle;

  const isError = status === "error";
  const isDone  = status === "done";

  return (
    <div className="status-panel">
      <div className="card">
        {/* Header */}
        <div className="status-header">
          <div
            className={`status-icon ${meta.cls}`}
            style={{ background: meta.bg }}
          >
            {meta.icon}
          </div>
          <div style={{ flex: 1 }}>
            <div className="status-title">
              {isDone  ? "Clipes prontos!" :
               isError ? "Erro no processamento" :
               status === "downloading" ? "Baixando vídeo..." :
               "Processando vídeo..."}
            </div>
            <div className="status-msg">{message}</div>
          </div>
          {(isDone || isError) && (
            <button className="reset-btn" onClick={onReset}>
              ↩ Novo vídeo
            </button>
          )}
        </div>

        {/* Progress bar */}
        {!isError && (
          <>
            <div className="progress-bar-wrap">
              <div
                className="progress-bar"
                style={{ width: `${Math.max(2, progress)}%` }}
              />
            </div>

            {/* Steps */}
            <div className="progress-steps">
              {STEPS.map((step) => {
                const state = getStepState(step.key, status);
                return (
                  <div
                    key={step.key}
                    className={`progress-step ${
                      state === "active" ? "active" :
                      state === "done"   ? "done"   : ""
                    }`}
                  >
                    <span style={{ fontSize: "0.9em" }}>
                      {state === "done" ? "✓" : step.icon}
                    </span>
                    <br />
                    {step.label}
                  </div>
                );
              })}
            </div>
          </>
        )}

        {/* Error detail */}
        {isError && error && (
          <div className="error-box" style={{ marginTop: 16 }}>
            <span>⚠️</span>
            <span style={{ wordBreak: "break-word", flex: 1 }}>{error}</span>
          </div>
        )}
      </div>
    </div>
  );
}
