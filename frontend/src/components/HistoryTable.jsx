import { fmtDate, fmtInt, fmtSigned, shortHash } from "../format";
import { EmptyState, Loading } from "./ui";

/**
 * Per-commit rows behind the current object's numbers (the "history" of
 * the selected commit set), newest first, with pagination.
 */
export default function HistoryTable({ history, page, pageSize, onPage, onSetAsOf }) {
  if (!history) return <Loading label="Loading history..." />;
  if (!history.items.length) {
    return <EmptyState>No commits in the selected set touched this object.</EmptyState>;
  }

  const pages = Math.max(1, Math.ceil(history.total / pageSize));

  return (
    <>
      <div className="tbl-scroll">
        <table className="tbl">
          <thead>
            <tr>
              <th>When</th>
              <th>Commit</th>
              <th>Author</th>
              <th className="num">Added</th>
              <th className="num">Removed</th>
              <th className="num">Growth</th>
              <th className="num">Churn</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {history.items.map((item) => (
              <tr key={item.hash}>
                <td>{fmtDate(item.committer_ts)}</td>
                <td className="mono" title={item.hash}>
                  {shortHash(item.hash)}
                </td>
                <td>
                  {item.author_name} <span className="commit-meta">{item.author_email}</span>
                </td>
                <td className="num pos">+{fmtInt(item.added)}</td>
                <td className="num neg">-{fmtInt(item.removed)}</td>
                <td className={`num ${item.growth > 0 ? "pos" : item.growth < 0 ? "neg" : ""}`}>
                  {fmtSigned(item.growth)}
                </td>
                <td className="num">{fmtInt(item.churn)}</td>
                <td className="num">
                  <button
                    type="button"
                    className="btn btn-ghost btn-sm"
                    title="Measure the repository as of this commit"
                    onClick={() => onSetAsOf(item.hash)}
                  >
                    as of
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="pager">
        <button
          type="button"
          className="btn btn-secondary btn-sm"
          disabled={page === 0}
          onClick={() => onPage(page - 1)}
        >
          Previous
        </button>
        <span className="pager-info">
          Page {page + 1} of {pages} · {fmtInt(history.total)} commit
          {history.total === 1 ? "" : "s"}
        </span>
        <button
          type="button"
          className="btn btn-secondary btn-sm"
          disabled={page + 1 >= pages}
          onClick={() => onPage(page + 1)}
        >
          Next
        </button>
      </div>
    </>
  );
}
