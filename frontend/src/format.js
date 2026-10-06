// Small formatting helpers shared by every page.

export function fmtInt(n) {
  if (n === null || n === undefined) return "-";
  return n.toLocaleString("en-US");
}

export function fmtSigned(n) {
  if (n === null || n === undefined) return "-";
  return n > 0 ? `+${fmtInt(n)}` : fmtInt(n);
}

export function fmtPct(x) {
  if (x === null || x === undefined) return "-";
  return `${(x * 100).toFixed(1)}%`;
}

export function fmtRatio(x) {
  if (x === null || x === undefined) return "-";
  return x.toFixed(4);
}

export function fmtDate(ts) {
  if (!ts) return "-";
  return new Date(ts * 1000).toLocaleDateString("en-GB", {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

export function fmtDateTime(ts) {
  if (!ts) return "-";
  return new Date(ts * 1000).toLocaleString("en-GB", {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function shortHash(h) {
  return h ? h.slice(0, 8) : "-";
}

export function prNumber(n) {
  return n > 0 ? `+${fmtInt(n)}` : fmtInt(n);
}
