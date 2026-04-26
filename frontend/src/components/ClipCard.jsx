function fmtTime(s) {
  const m = Math.floor(s / 60);
  return `${m}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
}

function confidenceColor(v) {
  if (v >= 0.8) return "#c8f135";
  if (v >= 0.6) return "#facc15";
  return "#fb923c";
}

function DownloadBtn({ url, filename, label, variant = "normal" }) {
  const handleDownload = () => {
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  };
  return (
    <button
      className={variant === "viral" ? "btn btn-download-viral" : "btn btn-download"}
      onClick={handleDownload}
    >
      {label}
    </button>
  );
}

export default function ClipCard({ clip, index }) {
  const {
    title, start_time, end_time, duration, reason, confidence,
    download_url, filename, viral_filename, viral_download_url,
  } = clip;

  const pct   = Math.round(confidence * 100);
  const color = confidenceColor(confidence);
  const hasViral = !!viral_download_url;

  return (
    <div className={`clip-card${hasViral ? " clip-card--viral" : ""}`}
      style={{ animationDelay: `${index * 0.07}s` }}>

      <div className="clip-card-left">
        {/* Rank + viral badge */}
        <div className="clip-rank">
          <span className="clip-rank-badge">#{index + 1}</span>
          {hasViral && <span className="viral-pill">🔥 Viral</span>}
        </div>

        <div className="clip-title">{title}</div>

        <div className="clip-meta">
          <span className="clip-time">{fmtTime(start_time)} → {fmtTime(end_time)}</span>
          <span className="clip-duration">⏱ {duration}s</span>
        </div>

        <div className="clip-reason">{reason}</div>
      </div>

      <div className="clip-card-right">
        {/* Score */}
        <div className="confidence">
          <div className="confidence-label">Score</div>
          <div className="confidence-value" style={{ color }}>{pct}%</div>
          <div className="confidence-bar">
            <div className="confidence-fill" style={{ width: `${pct}%`, background: color }} />
          </div>
        </div>

        {/* Download buttons */}
        <div className="clip-downloads">
          <DownloadBtn url={download_url} filename={filename} label="⬇ Normal" />
          {hasViral && (
            <DownloadBtn
              url={viral_download_url}
              filename={viral_filename}
              label="🔥 Viral"
              variant="viral"
            />
          )}
        </div>
      </div>
    </div>
  );
}
