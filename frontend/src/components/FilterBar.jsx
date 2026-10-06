import CommitPicker from "./CommitPicker";
import { fmtInt, shortHash } from "../format";

/**
 * The filter editor: pick a commit set (time range or manual list), an
 * author, and optionally measure as of an older commit. Editing happens on
 * a draft; "Apply" commits the draft to the dashboard. All filters AND
 * together (spec item 49), which the summary row makes visible.
 */
export default function FilterBar({
  repoId,
  draft,
  setDraft,
  applied,
  onApply,
  onReset,
  onSetAsOf,
  authors,
  dirty,
  setCount,
}) {
  const patch = (p) => setDraft((d) => ({ ...d, ...p }));

  const toggleHash = (hash) =>
    setDraft((d) => ({
      ...d,
      hashes: d.hashes.includes(hash)
        ? d.hashes.filter((h) => h !== hash)
        : [...d.hashes, hash],
    }));

  const chips = [];
  if (applied.author) chips.push(`author: ${applied.author}`);
  if (applied.from || applied.to) {
    chips.push(`time: ${applied.from || "start"} to ${applied.to || "now"}`);
  }
  if (applied.asOf) chips.push(`as of: ${shortHash(applied.asOf)}`);
  if (applied.mode === "manual") {
    chips.push(`manual set: ${applied.hashes.length} commit${applied.hashes.length === 1 ? "" : "s"}`);
  }

  return (
    <div className="filters-bar">
      <div className="filters-grid">
        <div className="field">
          <span className="label">Commit set</span>
          <div className="mode-switch">
            <button
              type="button"
              className={draft.mode === "time" ? "active" : ""}
              onClick={() => patch({ mode: "time" })}
            >
              Time range
            </button>
            <button
              type="button"
              className={draft.mode === "manual" ? "active" : ""}
              onClick={() => patch({ mode: "manual" })}
            >
              Manual commits
            </button>
          </div>
        </div>

        <label className="field">
          <span className="label">Author</span>
          <select
            className="select"
            value={draft.author}
            onChange={(e) => patch({ author: e.target.value })}
          >
            <option value="">All authors</option>
            {authors.map((author) => (
              <option key={author.email} value={author.email}>
                {author.name} ({author.email})
              </option>
            ))}
          </select>
        </label>

        <label className="field">
          <span className="label">From (inclusive)</span>
          <input
            type="date"
            className="input"
            value={draft.from}
            onChange={(e) => patch({ from: e.target.value })}
          />
        </label>

        <label className="field">
          <span className="label">To (exclusive)</span>
          <input
            type="date"
            className="input"
            value={draft.to}
            onChange={(e) => patch({ to: e.target.value })}
          />
        </label>

        <label className="field">
          <span className="label">As of commit</span>
          <input
            className="input mono"
            placeholder="full or short hash"
            value={draft.asOf}
            onChange={(e) => patch({ asOf: e.target.value.trim() })}
          />
        </label>
      </div>

      <div className="filters-actions">
        <button type="button" className="btn btn-primary" disabled={!dirty} onClick={onApply}>
          Apply filters
        </button>
        <button type="button" className="btn btn-secondary" onClick={onReset}>
          Reset
        </button>
        {dirty ? <span className="dirty-note">Filter changes are not applied yet</span> : null}
      </div>

      {draft.mode === "manual" ? (
        <CommitPicker
          repoId={repoId}
          selected={draft.hashes}
          onToggle={toggleHash}
          onSetAsOf={onSetAsOf}
          asOf={draft.asOf}
        />
      ) : null}

      <div className="set-summary">
        <span className="set-summary-label">Measuring:</span>
        {chips.length ? (
          chips.map((text) => (
            <span className="chip" key={text}>
              {text}
            </span>
          ))
        ) : (
          <span className="chip chip-plain">whole history</span>
        )}
        {setCount !== null && setCount !== undefined ? (
          <span className="chip chip-plain">|H| = {fmtInt(setCount)} commits</span>
        ) : null}
      </div>
    </div>
  );
}
