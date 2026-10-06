import { useEffect, useState } from "react";
import { listCommits } from "../api";
import { fmtDate, fmtInt, shortHash } from "../format";

const PAGE = 500;

/**
 * Scrollable list of the repository's measured commits with checkboxes,
 * used to build a manual commit set (spec item 45). Fetches its own pages
 * lazily; selection state lives in the parent (the filter draft).
 */
export default function CommitPicker({ repoId, selected, onToggle, onSetAsOf, asOf }) {
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError("");
    listCommits(repoId, PAGE, 0)
      .then((page) => {
        if (cancelled) return;
        setItems(page.items);
        setTotal(page.total);
      })
      .catch((err) => {
        if (!cancelled) setError(err.detail);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [repoId]);

  const loadMore = () => {
    setLoading(true);
    listCommits(repoId, PAGE, items.length)
      .then((page) => {
        setItems((prev) => [...prev, ...page.items]);
        setTotal(page.total);
        setError("");
      })
      .catch((err) => setError(err.detail))
      .finally(() => setLoading(false));
  };

  const needle = search.trim().toLowerCase();
  const visible = needle
    ? items.filter(
        (c) =>
          c.hash.startsWith(needle) ||
          c.author_name.toLowerCase().includes(needle) ||
          c.author_email.toLowerCase().includes(needle)
      )
    : items;

  return (
    <div className="commit-picker">
      <div className="commit-picker-head">
        <strong>Pick commits</strong>
        <input
          className="input"
          style={{ maxWidth: 260 }}
          placeholder="Filter by hash, author..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <span className="commit-meta">
          {selected.length} selected · {visible.length} shown · {items.length} of {total} loaded
        </span>
        {selected.length > 0 ? (
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            onClick={() => selected.forEach((h) => onToggle(h))}
          >
            Clear selection
          </button>
        ) : null}
      </div>

      {error ? <div className="banner banner-error">{error}</div> : null}

      <div className="commit-scroll">
        {visible.map((commit) => (
          <label key={commit.hash} className="commit-row">
            <input
              type="checkbox"
              checked={selected.includes(commit.hash)}
              onChange={() => onToggle(commit.hash)}
            />
            <span className="mono" title={commit.hash}>
              {shortHash(commit.hash)}
            </span>
            <span className="commit-meta" style={{ width: 92 }}>
              {fmtDate(commit.committer_ts)}
            </span>
            <span style={{ maxWidth: 200, overflow: "hidden", textOverflow: "ellipsis" }}>
              {commit.author_name}
            </span>
            <span className="commit-meta" style={{ maxWidth: 220, overflow: "hidden", textOverflow: "ellipsis" }}>
              {commit.author_email}
            </span>
            <span className="num">
              <span className="pos">+{fmtInt(commit.added)}</span>{" "}
              <span className="neg">-{fmtInt(commit.removed)}</span>{" "}
              <span className="commit-meta">({fmtInt(commit.files_changed)} files)</span>
            </span>
            <span className="commit-msg-spacer" />
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              title="Measure the repository as of this commit"
              disabled={asOf === commit.hash}
              onClick={(e) => {
                e.preventDefault();
                onSetAsOf(commit.hash);
              }}
            >
              {asOf === commit.hash ? "as of ✓" : "as of"}
            </button>
          </label>
        ))}
        {!loading && visible.length === 0 ? (
          <div className="loading" style={{ padding: 14 }}>
            No commits match.
          </div>
        ) : null}
      </div>

      {items.length < total ? (
        <button
          type="button"
          className="btn btn-secondary btn-sm"
          style={{ marginTop: 8 }}
          disabled={loading}
          onClick={loadMore}
        >
          {loading ? "Loading..." : `Load more (${total - items.length} left)`}
        </button>
      ) : null}
    </div>
  );
}
