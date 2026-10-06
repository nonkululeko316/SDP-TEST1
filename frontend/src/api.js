// Thin fetch wrapper around the RAT backend API.
//
// Every function returns the parsed JSON body or throws an ApiError with
// a human-readable `detail` (FastAPI puts the reason there). The network
// layer is the single place that knows the URL shapes.

export class ApiError extends Error {
  constructor(status, detail) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

async function request(path, options = {}) {
  let response;
  try {
    response = await fetch(`/api${path}`, options);
  } catch {
    throw new ApiError(
      0,
      "Cannot reach the backend API. Is the server running on port 8000?"
    );
  }
  if (response.status === 204) return null;

  const body = await response.json().catch(() => null);
  if (!response.ok) {
    let detail = `Request failed with status ${response.status}`;
    if (body && body.detail) {
      detail =
        typeof body.detail === "string"
          ? body.detail
          : JSON.stringify(body.detail);
    }
    throw new ApiError(response.status, detail);
  }
  return body;
}

const json = (payload, method = "POST") => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(payload),
});

// --- repositories -------------------------------------------------------

export const listRepos = () => request("/repos");

export const getRepo = (repoId) => request(`/repos/${repoId}`);

export function uploadZip(file) {
  const form = new FormData();
  form.append("file", file);
  return request("/repos/upload", { method: "POST", body: form });
}

export const cloneRepo = (url, name) =>
  request("/repos/clone", json({ url, name: name || null }));

export const analyseRepo = (repoId) =>
  request(`/repos/${repoId}/analyse`, { method: "POST" });

// --- metrics ------------------------------------------------------------

/** Turn the UI filter state into the commit-set request body. */
export function filtersToBody(filters, object) {
  return {
    kind: object.kind,
    path: object.path,
    author: filters.author || null,
    from: filters.from || null,
    to: filters.to || null,
    as_of: filters.asOf || null,
    hashes: filters.mode === "manual" ? filters.hashes : [],
  };
}

export const getMetrics = (repoId, filters, object) =>
  request(`/repos/${repoId}/metrics/commit-set`, json(filtersToBody(filters, object)));

export function getHistory(repoId, filters, object, limit = 100, offset = 0) {
  const params = new URLSearchParams({ kind: object.kind, path: object.path });
  params.set("limit", limit);
  params.set("offset", offset);
  if (filters.author) params.set("author", filters.author);
  if (filters.from) params.set("from", filters.from);
  if (filters.to) params.set("to", filters.to);
  if (filters.asOf) params.set("as_of", filters.asOf);
  if (filters.mode === "manual" && filters.hashes.length) {
    params.set("commits", filters.hashes.join(","));
  }
  return request(`/repos/${repoId}/metrics/history?${params}`);
}

export const listCommits = (repoId, limit = 500, offset = 0) =>
  request(`/repos/${repoId}/commits?limit=${limit}&offset=${offset}`);

export const listAuthors = (repoId) => request(`/repos/${repoId}/authors`);

// --- author merges ------------------------------------------------------

export const listMerges = (repoId) => request(`/repos/${repoId}/author-merges`);

export const createMerge = (repoId, sourceEmail, targetEmail) =>
  request(
    `/repos/${repoId}/author-merges`,
    json({ source_email: sourceEmail, target_email: targetEmail })
  );

export const deleteMerge = (repoId, mergeId) =>
  request(`/repos/${repoId}/author-merges/${mergeId}`, { method: "DELETE" });
