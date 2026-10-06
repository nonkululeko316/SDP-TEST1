import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import RepoListPage from "./pages/RepoListPage";
import RepoPage from "./pages/RepoPage";

// HashRouter is used on purpose: the built app can then be served by the
// FastAPI backend (or any static file server) without needing SPA routing
// rules, because every client route lives behind the URL fragment.

export default function App() {
  return (
    <>
      <header className="app-header">
        <div className="app-header-inner">
          <NavLink to="/" className="brand">
            <span className="brand-mark">RAT</span>
            <span className="brand-sub">Repo Analysis Tool</span>
          </NavLink>
          <nav className="nav">
            <NavLink to="/" end>
              Repositories
            </NavLink>
          </nav>
        </div>
      </header>
      <main className="container">
        <Routes>
          <Route path="/" element={<RepoListPage />} />
          <Route path="/repos/:repoId" element={<RepoPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </>
  );
}
