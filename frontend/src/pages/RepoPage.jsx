import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { analyseRepo, getHistory, getMetrics, getRepo, listAuthors, listMerges } from "../api";
import AuthorsTab from "../components/AuthorsTab";
import { AuthorChurnChart, AuthorPie, ChildrenChurnChart, GrowthChart } from "../components/Charts";
import FilterBar from "../components/FilterBar";
import HistoryTable from "../components/HistoryTable";
import ObjectBrowser from "../components/ObjectBrowser";
import { Banner, ChartCard, Loading, MetricCard, StatusBadge } from "../components/ui";
import { fmtInt, fmtPct, fmtRatio, fmtSigned } from "../format";

const BUSY = ["queued", "ingesting", "analysing"];
const EMPTY_FILTERS = { author: "", from: "", to: "", asOf: "", mode: "time", hashes: [] };
const HISTORY_PAGE = 25;
const CHART_HISTORY_LIMIT = 1000;

/** One repository's dashboard: filters, object browser, charts, authors, history. */
export default function RepoPage() {
  const { repoId: idParam } = useParams();
  const repoId = Number(idParam);

  const [repo, setRepo] = useState(null);
  const [repoError, setRepoError] = useState("");
  const [notice, setNotice] = useState("");
  const [tab, setTab] = useState("metrics");

  const [draft, setDraft] = useState(EMPTY_FILTERS);
  const [applied, setApplied] = useState(EMPTY_FILTERS);
  const [object, setObject] = useState({ kind: "dir", path: "" });

  const [metrics, setMetrics] = useState(null);
  const [metricsError, setMetricsError] = useState("");
  const [metricsLoading, setMetricsLoading] = useState(false);
  const [authors, setAuthors] = useState([]);
  const [merges, setMerges] = useState([]);
  const [history, setHistory] = useState(null);
  const [historyPage, setHistoryPage] = useState(0);
  const [historyError, setHistoryError] = useState("");
  const [chartHistory, setChartHistory] = useState(null);
  const [dataVersion, setDataVersion] = useState(0);

  // Keep the repository row fresh (status flips while analysis runs).
  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const detail = await getRepo(repoId);
        if (!cancelled) {
          setRepo(detail);
          setRepoError("");
        }
      } catch (err) {
        if (!cancelled) setRepoError(err.detail);
      }
    };
    load();
    const timer = setInterval(load, 3000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [repoId]);

  const ready = repo?.status === "ready";

  // Authors + manual merges (both feed the filter dropdown and the tab).
  useEffect(() => {
    if (!ready) return undefined;
    let cancelled = false;
    Promise.all([listAuthors(repoId), listMerges(repoId)])
      .then(([authorsBody, mergesBody]) => {
        if (cancelled) return;
        setAuthors(authorsBody.items);
        setMerges(mergesBody.items);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [repoId, ready, dataVersion]);

  // Object metrics for the applied filters.
  useEffect(() => {
    if (!ready) return undefined;
    let cancelled = false;
    setMetricsLoading(true);
    getMetrics(repoId, applied, object)
      .then((body) => {
        if (cancelled) return;
        setMetrics(body);
        setMetricsError("");
      })
      .catch((err) => {
        if (!cancelled) setMetricsError(err.detail);
      })
      .finally(() => {
        if (!cancelled) setMetricsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [repoId, ready, applied, object, dataVersion]);

  // Paginated history of the current object.
  useEffect(() => {
    if (!ready) return undefined;
    let cancelled = false;
    getHistory(repoId, applied, object, HISTORY_PAGE, historyPage * HISTORY_PAGE)
      .then((body) => {
        if (cancelled) return;
        setHistory(body);
        setHistoryError("");
      })
      .catch((err) => {
        if (!cancelled) {
          setHistory(null);
          setHistoryError(err.detail);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [repoId, ready, applied, object, historyPage, dataVersion]);

  // Larger history window for the cumulative growth chart.
  useEffect(() => {
    if (!ready) return undefined;
    let cancelled = false;
    getHistory(repoId, applied, object, CHART_HISTORY_LIMIT, 0)
      .then((body) => {
        if (!cancelled) setChartHistory(body);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [repoId, ready, applied, object, dataVersion]);

  const navigateObject = (target) => {
    setObject(target);
    setHistoryPage(0);
  };

  const applyFilters = () => {
    setApplied(draft);
    setHistoryPage(0);
  };

  const resetFilters = () => {
    setDraft(EMPTY_FILTERS);
    setApplied(EMPTY_FILTERS);
    setHistoryPage(0);
  };

  // "Measure as of this commit" actions apply immediately (explicit click).
  const setAsOf = (hash) => {
    setDraft((d) => ({ ...d, asOf: hash }));
    setApplied((a) => ({ ...a, asOf: hash }));
    setHistoryPage(0);
  };

  const reanalyse = async () => {
    setNotice("");
    setRepoError("");
    try {
      await analyseRepo(repoId);
      setNotice("Re-analysis queued - results refresh automatically when it finishes.");
    } catch (err) {
      setRepoError(err.detail);
    }
  };

  const dirty = JSON.stringify(draft) !== JSON.stringify(applied);

  if (!repo && repoError) {
    return (
      <>
        <Link className="back-link" to="/">
          ← Back to repositories
        </Link>
        <Banner kind="error">{repoError}</Banner>
      </>
    );
  }
  if (!repo) return <Loading label="Loading repository..." />;

  return (
    <>
      <Link className="back-link" to="/">
        ← Back to repositories
      </Link>

      <div className="page-head">
        <div>
          <h1 className="page-title">
            {repo.name} <StatusBadge status={repo.status} />
          </h1>
          <p className="page-sub">
            {repo.source_type === "url" ? "cloned from " : "uploaded as "}
            {repo.source_ref}
            {repo.message ? ` · ${repo.message}` : ""}
          </p>
        </div>
        <div className="page-actions">
          <button
            type="button"
            className="btn btn-secondary"
            disabled={!repo.local_path || BUSY.includes(repo.status)}
            onClick={reanalyse}
          >
            Re-analyse
          </button>
        </div>
      </div>

      {repoError ? <Banner kind="error">{repoError}</Banner> : null}
      {notice ? <Banner kind="success">{notice}</Banner> : null}
      {BUSY.includes(repo.status) ? (
        <Banner kind="info">
          Analysis is running in the background - this page updates automatically when it
          finishes.
        </Banner>
      ) : null}
      {repo.status === "error" ? <Banner kind="error">{repo.message}</Banner> : null}

      {ready ? (
        <>
          <div className="tabs">
            <button
              type="button"
              className={`tab ${tab === "metrics" ? "active" : ""}`}
              onClick={() => setTab("metrics")}
            >
              Metrics
            </button>
            <button
              type="button"
              className={`tab ${tab === "authors" ? "active" : ""}`}
              onClick={() => setTab("authors")}
            >
              Authors ({authors.length})
            </button>
          </div>

          {tab === "metrics" ? (
            <>
              <FilterBar
                repoId={repoId}
                draft={draft}
                setDraft={setDraft}
                applied={applied}
                onApply={applyFilters}
                onReset={resetFilters}
                onSetAsOf={setAsOf}
                authors={authors}
                dirty={dirty}
                setCount={metrics ? metrics.set.commit_count : null}
              />

              {metricsLoading ? <p className="list-note">Updating metrics...</p> : null}
              {metricsError ? <Banner kind="error">{metricsError}</Banner> : null}
              {metrics && metrics.set.hashes_missing && metrics.set.hashes_missing.length ? (
                <Banner kind="warn">
                  These picked commits were not found in the analysed history and were ignored:{" "}
                  <span className="mono">{metrics.set.hashes_missing.join(", ")}</span>
                </Banner>
              ) : null}

              {metrics ? (
                <>
                  <div className="grid grid-metrics">
                    <MetricCard label="Commits |H|" value={fmtInt(metrics.set.commit_count)} />
                    <MetricCard label="Added lines" value={fmtInt(metrics.added)} />
                    <MetricCard label="Removed lines" value={fmtInt(metrics.removed)} />
                    <MetricCard
                      label="Growth"
                      value={fmtSigned(metrics.growth)}
                      valueClass={metrics.growth > 0 ? "pos" : metrics.growth < 0 ? "neg" : ""}
                    />
                    <MetricCard label="Churn" value={fmtInt(metrics.churn)} />
                    <MetricCard label="Modifications" value={fmtInt(metrics.modifications)} />
                    <MetricCard
                      label="Modification freq."
                      value={fmtRatio(metrics.modification_frequency)}
                      hint="n / |H|"
                    />
                    <MetricCard label="Churn rate" value={fmtRatio(metrics.churn_rate)} hint="churn / |H|" />
                  </div>

                  <div className="card section-gap">
                    <h3 className="card-title">
                      Object: {metrics.path === "" ? "repository root" : metrics.path}
                    </h3>
                    <p className="card-sub">
                      Directories roll up their whole subtree; the repository is the root
                      directory.
                    </p>
                    <ObjectBrowser object={object} onNavigate={navigateObject} children={metrics.children} />
                  </div>

                  {object.kind === "dir" && metrics.children.length ? (
                    <div className="grid grid-2 section-gap">
                      <ChartCard
                        title="Children by churn"
                        sub={`Immediate children of ${object.path === "" ? "the repository root" : object.path}.`}
                      >
                        <ChildrenChurnChart children={metrics.children} onPick={navigateObject} />
                      </ChartCard>
                      <ChartCard
                        title="Growth over time"
                        sub="Cumulative added minus removed across the commits touching this object."
                      >
                        {chartHistory ? (
                          <GrowthChart items={chartHistory.items} total={chartHistory.total} />
                        ) : (
                          <Loading />
                        )}
                      </ChartCard>
                    </div>
                  ) : (
                    <div className="section-gap">
                      <ChartCard
                        title="Growth over time"
                        sub="Cumulative added minus removed across the commits touching this object."
                      >
                        {chartHistory ? (
                          <GrowthChart items={chartHistory.items} total={chartHistory.total} />
                        ) : (
                          <Loading />
                        )}
                      </ChartCard>
                    </div>
                  )}

                  <div className="grid grid-2 section-gap">
                    <ChartCard
                      title="Author ownership"
                      sub="Share of churn on this object (top 8, remainder grouped)."
                    >
                      <AuthorPie authors={metrics.authors} />
                    </ChartCard>
                    <ChartCard title="Churn per author" sub="Who did the most line work here.">
                      <AuthorChurnChart authors={metrics.authors} />
                    </ChartCard>
                  </div>

                  <div className="card section-gap">
                    <h3 className="card-title">Authors on this object</h3>
                    <p className="card-sub">
                      Commits in H = commits by that author inside the selected set; ownership =
                      author churn / total churn (spec items 36-39).
                    </p>
                    <div className="tbl-scroll">
                      <table className="tbl">
                        <thead>
                          <tr>
                            <th>Author</th>
                            <th className="num">Commits in H</th>
                            <th className="num">Modifications</th>
                            <th className="num">Added</th>
                            <th className="num">Removed</th>
                            <th className="num">Churn</th>
                            <th className="num">Ownership</th>
                          </tr>
                        </thead>
                        <tbody>
                          {metrics.authors.map((author) => (
                            <tr key={author.email}>
                              <td>
                                {author.name} <span className="commit-meta">{author.email}</span>
                              </td>
                              <td className="num">{fmtInt(author.commits)}</td>
                              <td className="num">{fmtInt(author.modifications)}</td>
                              <td className="num pos">+{fmtInt(author.added)}</td>
                              <td className="num neg">-{fmtInt(author.removed)}</td>
                              <td className="num">{fmtInt(author.churn)}</td>
                              <td className="num">{fmtPct(author.ownership)}</td>
                            </tr>
                          ))}
                          {!metrics.authors.length ? (
                            <tr>
                              <td colSpan={7}>
                                <span className="list-note">
                                  No authors touched this object in the selected set.
                                </span>
                              </td>
                            </tr>
                          ) : null}
                        </tbody>
                      </table>
                    </div>
                  </div>

                  <div className="card section-gap">
                    <h3 className="card-title">Commit history on this object</h3>
                    <p className="card-sub">
                      Every commit from the selected set that touched{" "}
                      {object.path === "" ? "the repository" : `"${object.path}"`}, newest first.
                    </p>
                    {historyError ? <Banner kind="error">{historyError}</Banner> : null}
                    <HistoryTable
                      history={history}
                      page={historyPage}
                      pageSize={HISTORY_PAGE}
                      onPage={setHistoryPage}
                      onSetAsOf={setAsOf}
                    />
                  </div>
                </>
              ) : (
                <Loading label="Computing metrics..." />
              )}
            </>
          ) : (
            <AuthorsTab
              repoId={repoId}
              authors={authors}
              merges={merges}
              onChanged={() => setDataVersion((version) => version + 1)}
            />
          )}
        </>
      ) : null}
    </>
  );
}
