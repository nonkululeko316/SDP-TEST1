import { useState } from "react";
import { createMerge, deleteMerge } from "../api";
import { fmtDate, fmtInt } from "../format";
import { Banner } from "./ui";

/**
 * Author management: the resolved author table plus CRUD over manual
 * merges. Every change re-materialises identities on the backend, so the
 * dashboard numbers update as soon as `onChanged` refreshes them.
 */
export default function AuthorsTab({ repoId, authors, merges, onChanged }) {
  const [source, setSource] = useState("");
  const [target, setTarget] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const submit = async (event) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    setSuccess("");
    try {
      const merge = await createMerge(repoId, source, target);
      setSuccess(`Merged ${merge.source_email} into ${merge.target_email}. Metrics updated.`);
      setSource("");
      setTarget("");
      onChanged();
    } catch (err) {
      setError(err.detail);
    } finally {
      setBusy(false);
    }
  };

  const remove = async (mergeId, sourceEmail) => {
    setBusy(true);
    setError("");
    setSuccess("");
    try {
      await deleteMerge(repoId, mergeId);
      setSuccess(`Merge of ${sourceEmail} removed - that identity is separate again.`);
      onChanged();
    } catch (err) {
      setError(err.detail);
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <div className="grid grid-2">
        <div className="card">
          <h3 className="card-title">Manual author merges</h3>
          <p className="card-sub">
            Merge one identity into another when the repository has no .mailmap (or to override
            it). Merges are stored in the database, survive re-analysis, and can be undone at any
            time.
          </p>

          {error ? <Banner kind="error">{error}</Banner> : null}
          {success ? <Banner kind="success">{success}</Banner> : null}

          {authors.length >= 2 ? (
            <form className="form-row" onSubmit={submit}>
              <label className="field" style={{ flex: 1 }}>
                <span className="label">Identity to merge away</span>
                <select
                  className="select"
                  value={source}
                  onChange={(e) => setSource(e.target.value)}
                  required
                >
                  <option value="">Select an author...</option>
                  {authors.map((author) => (
                    <option key={author.email} value={author.email} disabled={author.email === target}>
                      {author.name} ({author.email})
                    </option>
                  ))}
                </select>
              </label>
              <label className="field" style={{ flex: 1 }}>
                <span className="label">Merge into</span>
                <select
                  className="select"
                  value={target}
                  onChange={(e) => setTarget(e.target.value)}
                  required
                >
                  <option value="">Select an author...</option>
                  {authors.map((author) => (
                    <option key={author.email} value={author.email} disabled={author.email === source}>
                      {author.name} ({author.email})
                    </option>
                  ))}
                </select>
              </label>
              <button type="submit" className="btn btn-primary" disabled={busy || !source || !target}>
                {busy ? "Working..." : "Merge"}
              </button>
            </form>
          ) : (
            <p className="list-note">A manual merge needs at least two visible author identities.</p>
          )}

          {merges.length ? (
            <div className="tbl-scroll section-gap">
              <table className="tbl">
                <thead>
                  <tr>
                    <th>#</th>
                    <th>Identity merged away</th>
                    <th>Merged into</th>
                    <th>Created</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {merges.map((merge) => (
                    <tr key={merge.id}>
                      <td>{merge.id}</td>
                      <td className="mono">{merge.source_email}</td>
                      <td className="mono">{merge.target_email}</td>
                      <td>{fmtDate(Date.parse(merge.created_at) / 1000)}</td>
                      <td className="num">
                        <button
                          type="button"
                          className="btn btn-danger btn-sm"
                          disabled={busy}
                          onClick={() => remove(merge.id, merge.source_email)}
                        >
                          Undo
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="list-note">No manual merges yet.</p>
          )}
        </div>

        <div className="card">
          <h3 className="card-title">How identity resolution works</h3>
          <p className="card-sub">Two mechanisms combine, always in this order:</p>
          <ol style={{ margin: "0 0 10px", paddingLeft: 20, color: "var(--text-dim)" }}>
            <li>
              <strong>.mailmap file</strong> - read from the repository at analysis time and
              applied in one batched <span className="mono">git check-mailmap</span> call (spec
              item 46).
            </li>
            <li>
              <strong>Manual merges</strong> - applied on top, so they work with or without a
              mailmap (spec item 47).
            </li>
          </ol>
          <div className="kv">
            <span>Raw identities kept per commit</span>
            <span>yes, alongside the resolved one</span>
          </div>
          <div className="kv">
            <span>Filtering by a merged-away email</span>
            <span>still finds its commits</span>
          </div>
          <div className="kv">
            <span>Merges survive re-analysis</span>
            <span>yes (they are your configuration)</span>
          </div>
        </div>
      </div>

      <div className="card section-gap">
        <h3 className="card-title">Authors ({authors.length})</h3>
        <p className="card-sub">
          Totals over the whole history, using identities after .mailmap and manual merges.
        </p>
        <div className="tbl-scroll">
          <table className="tbl">
            <thead>
              <tr>
                <th>Name</th>
                <th>Email</th>
                <th className="num">Commits</th>
                <th className="num">Added</th>
                <th className="num">Removed</th>
                <th>First commit</th>
                <th>Last commit</th>
                <th>Merged identities</th>
              </tr>
            </thead>
            <tbody>
              {authors.map((author) => (
                <tr key={author.email}>
                  <td>{author.name}</td>
                  <td className="mono">{author.email}</td>
                  <td className="num">{fmtInt(author.commits)}</td>
                  <td className="num pos">+{fmtInt(author.added)}</td>
                  <td className="num neg">-{fmtInt(author.removed)}</td>
                  <td>{fmtDate(author.first_ts)}</td>
                  <td>{fmtDate(author.last_ts)}</td>
                  <td>
                    {author.identities && author.identities.length ? (
                      <div className="chip-row">
                        {author.identities.map((identity) => (
                          <span key={identity} className="chip">
                            {identity}
                          </span>
                        ))}
                      </div>
                    ) : (
                      <span className="list-note">-</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}
