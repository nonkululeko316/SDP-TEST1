import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { analyseRepo, cloneRepo, listRepos, uploadZip } from "../api";
import { Banner, EmptyState, Loading, StatusBadge } from "../components/ui";
import { fmtDateTime } from "../format";

const BUSY = ["queued", "ingesting", "analysing"];

/** Repository registry: add repos (zip / URL), watch statuses, open dashboards. */
export default function RepoListPage() {
  const [repos, setRepos] = useState(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [uploadBusy, setUploadBusy] = useState(false);
  const [cloneBusy, setCloneBusy] = useState(false);
  const [cloneUrl, setCloneUrl] = useState("");
  const [cloneName, setCloneName] = useState("");
  const fileRef = useRef(null);
  const navigate = useNavigate();

  const refresh = useCallback(async () => {
    try {
      setRepos(await listRepos());
    } catch (err) {
      setError(err.detail);
    }
  }, []);

  useEffect(() => {
    refresh();
    const timer = setInterval(refresh, 3000);
    return () => clearInterval(timer);
  }, [refresh]);

  const doUpload = async (event) => {
    event.preventDefault();
    const file = fileRef.current?.files?.[0];
    if (!file) {
      setError("Choose a .zip file first.");
      return;
    }
    setUploadBusy(true);
    setError("");
    setNotice("");
    try {
      const repo = await uploadZip(file);
      setNotice(`Uploaded "${repo.name}" - ingest and analysis run in the background.`);
      if (fileRef.current) fileRef.current.value = "";
      refresh();
    } catch (err) {
      setError(err.detail);
    } finally {
      setUploadBusy(false);
    }
  };

  const doClone = async (event) => {
    event.preventDefault();
    if (!cloneUrl.trim()) {
      setError("Enter a repository URL first.");
      return;
    }
    setCloneBusy(true);
    setError("");
    setNotice("");
    try {
      const repo = await cloneRepo(cloneUrl.trim(), cloneName.trim());
      setNotice(`Cloning "${repo.name}" with full history - analysis follows when the clone ends.`);
      setCloneUrl("");
      setCloneName("");
      refresh();
    } catch (err) {
      setError(err.detail);
    } finally {
      setCloneBusy(false);
    }
  };

  const doAnalyse = async (repoId) => {
    setError("");
    setNotice("");
    try {
      await analyseRepo(repoId);
      setNotice(`Re-analysis of repository ${repoId} queued.`);
      refresh();
    } catch (err) {
      setError(err.detail);
    }
  };

  const busy = (repos || []).some((repo) => BUSY.includes(repo.status));

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="page-title">Repositories</h1>
          <p className="page-sub">
            {repos
              ? `${repos.length} registered · ${repos.filter((repo) => repo.status === "ready").length} ready to explore`
              : "Loading..."}
          </p>
        </div>
      </div>

      {error ? <Banner kind="error">{error}</Banner> : null}
      {notice ? <Banner kind="success">{notice}</Banner> : null}

      <div className="grid grid-2">
        <div className="card">
          <h3 className="card-title">Add from a .zip</h3>
          <p className="card-sub">The archive must contain the repository's .git directory or file.</p>
          <form className="form-row" onSubmit={doUpload}>
            <input ref={fileRef} type="file" accept=".zip" className="input" style={{ flex: 1 }} />
            <button type="submit" className="btn btn-primary" disabled={uploadBusy}>
              {uploadBusy ? "Uploading..." : "Upload & analyse"}
            </button>
          </form>
        </div>
        <div className="card">
          <h3 className="card-title">Add from a URL</h3>
          <p className="card-sub">Clones the full history (never shallow), then analyses it.</p>
          <form className="form-row" onSubmit={doClone}>
            <input
              className="input"
              style={{ flex: 2, minWidth: 190 }}
              placeholder="https://github.com/user/repo.git"
              value={cloneUrl}
              onChange={(e) => setCloneUrl(e.target.value)}
            />
            <input
              className="input"
              style={{ flex: 1, minWidth: 110 }}
              placeholder="name (optional)"
              value={cloneName}
              onChange={(e) => setCloneName(e.target.value)}
            />
            <button type="submit" className="btn btn-primary" disabled={cloneBusy}>
              {cloneBusy ? "Cloning..." : "Clone & analyse"}
            </button>
          </form>
        </div>
      </div>

      <div className="section-gap">
        {repos === null ? (
          <Loading />
        ) : repos.length === 0 ? (
          <EmptyState>No repositories yet - add one above to get started.</EmptyState>
        ) : (
          <div className="grid grid-repos">
            {repos.map((repo) => (
              <div className="card" key={repo.id}>
                <div className="repo-card-head">
                  <h3 className="repo-name">{repo.name}</h3>
                  <span className="badge badge-type">{repo.source_type}</span>
                  <StatusBadge status={repo.status} />
                </div>
                <p className="repo-meta" title={repo.source_ref}>
                  {repo.source_type === "url" ? "cloned from " : "uploaded as "}
                  {repo.source_ref}
                </p>
                <p className="repo-meta" title={repo.message}>
                  {repo.message || " "}
                </p>
                <p className="repo-meta">
                  added {fmtDateTime(Date.parse(repo.created_at) / 1000)}
                </p>
                <div className="repo-actions">
                  <button
                    type="button"
                    className="btn btn-primary"
                    disabled={repo.status !== "ready"}
                    onClick={() => navigate(`/repos/${repo.id}`)}
                  >
                    Open dashboard
                  </button>
                  <button
                    type="button"
                    className="btn btn-secondary"
                    disabled={!repo.local_path || BUSY.includes(repo.status)}
                    onClick={() => doAnalyse(repo.id)}
                  >
                    Re-analyse
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
        {busy ? (
          <p className="list-note">Background jobs are running - this list refreshes automatically.</p>
        ) : null}
      </div>
    </>
  );
}
