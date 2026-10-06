import { fmtInt, fmtSigned } from "../format";

function lastSegment(path) {
  const parts = path.split("/");
  return parts[parts.length - 1];
}

/**
 * Breadcrumb navigation plus the table of immediate children of the
 * current directory. Clicking a directory drills into it; clicking a file
 * opens that file's metrics (spec items 43, 28).
 */
export default function ObjectBrowser({ object, onNavigate, children }) {
  const parts = object.path ? object.path.split("/") : [];

  return (
    <>
      <div className="breadcrumbs">
        <button
          type="button"
          className={object.path === "" ? "crumb-current" : "crumb"}
          onClick={() => onNavigate({ kind: "dir", path: "" })}
        >
          repository root
        </button>
        {parts.map((part, index) => {
          const prefix = parts.slice(0, index + 1).join("/");
          const isLast = index === parts.length - 1;
          return (
            <span key={prefix} style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
              <span className="crumb-sep">/</span>
              {isLast ? (
                <span className="crumb-current">{part}</span>
              ) : (
                <button type="button" className="crumb" onClick={() => onNavigate({ kind: "dir", path: prefix })}>
                  {part}
                </button>
              )}
            </span>
          );
        })}
        {object.kind === "file" ? (
          <span className="badge badge-muted" style={{ marginLeft: 8 }}>
            file
          </span>
        ) : null}
      </div>

      {children && children.length > 0 ? (
        <div className="tbl-scroll">
          <table className="tbl">
            <thead>
              <tr>
                <th>Child</th>
                <th>Kind</th>
                <th className="num">Added</th>
                <th className="num">Removed</th>
                <th className="num">Growth</th>
                <th className="num">Churn</th>
                <th className="num">Modifications</th>
              </tr>
            </thead>
            <tbody>
              {children.map((child) => (
                <tr
                  key={child.path}
                  className="clickable"
                  title={child.path}
                  onClick={() => onNavigate({ kind: child.kind, path: child.path })}
                >
                  <td>{lastSegment(child.path)}</td>
                  <td>
                    <span className="badge badge-kind">{child.kind}</span>
                  </td>
                  <td className="num">{fmtInt(child.added)}</td>
                  <td className="num">{fmtInt(child.removed)}</td>
                  <td className={`num ${child.growth > 0 ? "pos" : child.growth < 0 ? "neg" : ""}`}>
                    {fmtSigned(child.growth)}
                  </td>
                  <td className="num">{fmtInt(child.churn)}</td>
                  <td className="num">{fmtInt(child.modifications)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="list-note">
          {object.kind === "file"
            ? "File selected - use the breadcrumb to go back up."
            : "No children touched this directory within the selected commit set."}
        </p>
      )}
    </>
  );
}
