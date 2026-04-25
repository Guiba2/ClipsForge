function fmtTime(seconds) {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${String(s).padStart(2, "0")}`;
}

function confidenceColor(v) {
  if (v >= 0.8) return "#c8f135";
  if (v >= 0.6) return "#facc15";
  return "#fb923c";
}

export default function ClipCard({ clip, index }) {
  const { title, start_time, end_time, duration, reason, confidence, download_url, filename } = clip;
  const pct = Math.round(confidence * 100);
  const color = confidenceColor(confidence);

  const handleDownload = () => {
    const a = document.createElement("a");
    a.href = download_url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  };

  return (
    <div className="clip-card" style={{ animationDelay: `${index * 0.07}s` }}>
      <div className="clip-card-left">
        <div className="clip-rank">
          <span style={{
            background: "rgba(200,241,53,0.12)",
            color: "#c8f135",
            padding: "2px 8px",
            borderRadius: "4px",
            fontWeight: 800,
          }}>
            #{index + 1}
          </span>
        </div>

        <div className="clip-title">{title}</div>

        <div className="clip-meta">
          <span className="clip-time">
            {fmtTime(start_time)} → {fmtTime(end_time)}
          </span>
          <span className="clip-duration">
            ⏱ {duration}s
          </span>
        </div>

        <div className="clip-reason">{reason}</div>
      </div>

      <div className="clip-card-right">
        <div className="confidence">
          <div className="confidence-label">Score</div>
          <div className="confidence-value" style={{ color }}>
            {pct}%
          </div>
          <div className="confidence-bar">
            <div
              className="confidence-fill"
              style={{ width: `${pct}%`, background: color }}
            />
          </div>
        </div>

        <button className="btn btn-download" onClick={handleDownload}>
          ⬇ Baixar
        </button>
      </div>
    </div>
  );
}
