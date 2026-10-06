// Tiny shared building blocks used across pages.

export function StatusBadge({ status }) {
  const kind =
    status === "ready"
      ? "badge-ready"
      : status === "error"
        ? "badge-error"
        : "badge-busy";
  return <span className={`badge ${kind}`}>{status}</span>;
}

export function Banner({ kind = "info", children }) {
  return <div className={`banner banner-${kind}`}>{children}</div>;
}

export function Loading({ label = "Loading..." }) {
  return <div className="loading">{label}</div>;
}

export function EmptyState({ children }) {
  return <div className="empty-state">{children}</div>;
}

export function MetricCard({ label, value, hint, valueClass = "" }) {
  return (
    <div className="metric-card">
      <div className="metric-label">{label}</div>
      <div className={`metric-value ${valueClass}`}>{value}</div>
      {hint ? <div className="metric-hint">{hint}</div> : null}
    </div>
  );
}

export function ChartCard({ title, sub, children }) {
  return (
    <div className="card">
      <h3 className="chart-title">{title}</h3>
      {sub ? <p className="card-sub">{sub}</p> : null}
      <div className="chart-box">{children}</div>
    </div>
  );
}
