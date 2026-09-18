import type {
  Compound,
  CompoundSchema,
  SearchMetrics,
  SimilarityHit,
  SubstructureHit,
  User,
} from "./types";

async function parseError(response: Response): Promise<string> {
  try {
    const body = await response.json();
    if (typeof body.detail === "string") return body.detail;
    return JSON.stringify(body.detail ?? body);
  } catch {
    return response.statusText;
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch(path, {
    credentials: "include",
    ...init,
    headers,
  });
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  if (response.status === 204) return undefined as T;
  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    return response.json() as Promise<T>;
  }
  return response as unknown as T;
}

export const api = {
  health: () => request<{ ok: boolean }>("/api/health"),
  login: (username: string, password: string) =>
    request<User>("/api/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    }),
  logout: () => request<{ ok: boolean }>("/api/logout", { method: "POST" }),
  me: () => request<User>("/api/me"),
  users: () => request<User[]>("/api/users"),
  createUser: (username: string, password: string, admin: boolean) =>
    request<User>("/api/users", {
      method: "POST",
      body: JSON.stringify({ username, password, admin }),
    }),
  schema: () => request<CompoundSchema>("/api/schema/compound"),
  databases: () => request<{ databases: string[] }>("/api/databases"),
  createDatabase: (name: string, collection: string) =>
    request("/api/databases", {
      method: "POST",
      body: JSON.stringify({ name, collection }),
    }),
  dropDatabase: (name: string) =>
    request(`/api/databases/${encodeURIComponent(name)}`, { method: "DELETE" }),
  collections: (db: string) =>
    request<{ collections: string[] }>(
      `/api/databases/${encodeURIComponent(db)}/collections`
    ),
  createCollection: (db: string, name: string) =>
    request(`/api/databases/${encodeURIComponent(db)}/collections`, {
      method: "POST",
      body: JSON.stringify({ name }),
    }),
  dropCollection: (db: string, name: string) =>
    request(
      `/api/databases/${encodeURIComponent(db)}/collections/${encodeURIComponent(name)}`,
      { method: "DELETE" }
    ),
  compounds: (db: string, coll: string, q = "", column = "All") => {
    const params = new URLSearchParams();
    if (q) params.set("q", q);
    if (column) params.set("column", column);
    const qs = params.toString();
    return request<{ compounds: Compound[] }>(
      `/api/databases/${encodeURIComponent(db)}/collections/${encodeURIComponent(coll)}/compounds${qs ? `?${qs}` : ""}`
    );
  },
  addCompound: (db: string, coll: string, data: Record<string, unknown>) =>
    request<Compound>(
      `/api/databases/${encodeURIComponent(db)}/collections/${encodeURIComponent(coll)}/compounds`,
      { method: "POST", body: JSON.stringify({ data }) }
    ),
  updateCompound: (
    db: string,
    coll: string,
    id: string,
    data: Record<string, unknown>,
    unset: string[] = []
  ) =>
    request<Compound>(
      `/api/databases/${encodeURIComponent(db)}/collections/${encodeURIComponent(coll)}/compounds/${encodeURIComponent(id)}`,
      { method: "PUT", body: JSON.stringify({ data, unset }) }
    ),
  deleteCompound: (db: string, coll: string, id: string) =>
    request(
      `/api/databases/${encodeURIComponent(db)}/collections/${encodeURIComponent(coll)}/compounds/${encodeURIComponent(id)}`,
      { method: "DELETE" }
    ),
  renderUrl: (smiles: string, w = 160, h = 120, highlight?: number[]) => {
    const params = new URLSearchParams({ smiles, w: String(w), h: String(h) });
    if (highlight && highlight.length) params.set("highlight", highlight.join(","));
    return `/api/render.png?${params.toString()}`;
  },
  metrics: () => request<SearchMetrics>("/api/search/metrics"),
  similarity: (
    db: string,
    coll: string,
    body: { query: string; cutoff: number; metric: string; sort_all?: boolean }
  ) =>
    request<{ hits: SimilarityHit[] }>(
      `/api/databases/${encodeURIComponent(db)}/collections/${encodeURIComponent(coll)}/search/similarity`,
      { method: "POST", body: JSON.stringify(body) }
    ),
  substructure: (db: string, coll: string, query: string) =>
    request<{ hits: SubstructureHit[] }>(
      `/api/databases/${encodeURIComponent(db)}/collections/${encodeURIComponent(coll)}/search/substructure`,
      { method: "POST", body: JSON.stringify({ query }) }
    ),
  exportCsvUrl: (db: string, coll: string, columns: string[], q = "", column = "All") => {
    const params = new URLSearchParams({ columns: columns.join(",") });
    if (q) params.set("q", q);
    if (column) params.set("column", column);
    return `/api/databases/${encodeURIComponent(db)}/collections/${encodeURIComponent(coll)}/csv/export?${params}`;
  },
  exportSimilarityCsvUrl: (
    db: string,
    coll: string,
    query: string,
    cutoff: number,
    metric: string,
    sortAll: boolean
  ) => {
    const params = new URLSearchParams({
      query,
      cutoff: String(cutoff),
      metric,
      sort_all: String(sortAll),
    });
    return `/api/databases/${encodeURIComponent(db)}/collections/${encodeURIComponent(coll)}/search/similarity.csv?${params}`;
  },
  importCsv: async (
    db: string,
    coll: string,
    file: File,
    identifierCol: string,
    dataCols: string[]
  ) => {
    const form = new FormData();
    form.append("file", file);
    form.append("identifier_col", identifierCol);
    form.append("data_cols", dataCols.join(","));
    return request<{ created: number; updated: number; total: number }>(
      `/api/databases/${encodeURIComponent(db)}/collections/${encodeURIComponent(coll)}/csv/import`,
      { method: "POST", body: form }
    );
  },
};
