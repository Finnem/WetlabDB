import type {
  Compound,
  CompoundSchema,
  SarAssayField,
  SarProject,
  SarSeries,
  AlignmentRunResult,
  AlignmentProjectRecord,
  AlignmentProjectSummary,
  CorePreviewResult,
  DepictResult,
  SearchMetrics,
  SeriesSnapshot,
  SimilarityHit,
  SubstructureHit,
  User,
  CollectionAccessPolicy,
  AuditEvent,
  TrashCompound,
} from "./types";

const API_MUTATION_HEADER = "X-WetlabDB-Request";

function applyMutationHeader(headers: Headers, method: string | undefined, path: string): void {
  const verb = (method || "GET").toUpperCase();
  if (!["POST", "PUT", "PATCH", "DELETE"].includes(verb)) return;
  if (!path.startsWith("/api/")) return;
  if (path === "/api/login") return;
  headers.set(API_MUTATION_HEADER, "1");
}

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
  applyMutationHeader(headers, init.method, path);
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
  createUser: (username: string, password: string, admin: boolean, kind: "student" | "employee" = "student") =>
    request<User>("/api/users", {
      method: "POST",
      body: JSON.stringify({ username, password, admin, kind }),
    }),
  collectionPolicies: () =>
    request<{ policies: CollectionAccessPolicy[] }>("/api/access/collection-policies"),
  putCollectionPolicy: (
    database: string,
    collection: string,
    body: Omit<CollectionAccessPolicy, "database" | "collection">
  ) =>
    request<CollectionAccessPolicy>(
      `/api/databases/${encodeURIComponent(database)}/collections/${encodeURIComponent(collection)}/access-policy`,
      { method: "PUT", body: JSON.stringify(body) }
    ),
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
  compounds: (
    db: string,
    coll: string,
    q = "",
    column = "All",
    opts?: { limit?: number; cursor?: string }
  ) => {
    const params = new URLSearchParams();
    if (q) params.set("q", q);
    if (column) params.set("column", column);
    if (opts?.limit) params.set("limit", String(opts.limit));
    if (opts?.cursor) params.set("cursor", opts.cursor);
    const qs = params.toString();
    return request<{
      compounds: Compound[];
      total?: number;
      next_cursor?: string | null;
      limit?: number;
    }>(
      `/api/databases/${encodeURIComponent(db)}/collections/${encodeURIComponent(coll)}/compounds${qs ? `?${qs}` : ""}`
    );
  },
  compoundsAll: async (
    db: string,
    coll: string,
    q = "",
    column = "All",
    pageSize = 200
  ) => {
    const all: Compound[] = [];
    let cursor: string | undefined;
    for (;;) {
      const body = await api.compounds(db, coll, q, column, {
        limit: pageSize,
        cursor,
      });
      all.push(...body.compounds);
      if (!body.next_cursor) break;
      cursor = body.next_cursor;
    }
    return all;
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
  mol3dUrl: (smiles: string) => {
    const params = new URLSearchParams({ smiles });
    return `/api/chem/3d.mol?${params.toString()}`;
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
  exportMolZip: async (db: string, coll: string, ids: string[], format: "zip" | "sdf" = "zip") => {
    const path = `/api/databases/${encodeURIComponent(db)}/collections/${encodeURIComponent(coll)}/mol/export`;
    const headers = new Headers({ "Content-Type": "application/json" });
    applyMutationHeader(headers, "POST", path);
    const response = await fetch(path, {
      method: "POST",
      credentials: "include",
      headers,
      body: JSON.stringify({ ids, format }),
    });
    if (!response.ok) {
      throw new Error(await parseError(response));
    }
    const blob = await response.blob();
    const disposition = response.headers.get("content-disposition") || "";
    const match = /filename="([^"]+)"/.exec(disposition);
    const filename =
      match?.[1] || (format === "sdf" ? "compounds.sdf" : "compounds_aligned.zip");
    return { blob, filename };
  },
  exportMolBulk: async (body: {
    database?: string;
    collection?: string;
    molecules: { id?: string; name?: string; smiles?: string; molblock?: string }[];
    format?: "zip" | "sdf";
    filename?: string;
  }) => {
    const path = "/api/mol/bulk";
    const headers = new Headers({ "Content-Type": "application/json" });
    applyMutationHeader(headers, "POST", path);
    const response = await fetch(path, {
      method: "POST",
      credentials: "include",
      headers,
      body: JSON.stringify(body),
    });
    if (!response.ok) {
      throw new Error(await parseError(response));
    }
    const blob = await response.blob();
    const disposition = response.headers.get("content-disposition") || "";
    const match = /filename="([^"]+)"/.exec(disposition);
    const filename = match?.[1] || "compounds.zip";
    return { blob, filename };
  },
  exportMolPage: async (body: {
    database?: string;
    collection?: string;
    molecules: { id?: string; name?: string; smiles?: string; molblock?: string }[];
    columns?: number;
    filename?: string;
    format?: "mol" | "cdxml";
  }) => {
    const path = "/api/mol/page";
    const headers = new Headers({ "Content-Type": "application/json" });
    applyMutationHeader(headers, "POST", path);
    const response = await fetch(path, {
      method: "POST",
      credentials: "include",
      headers,
      body: JSON.stringify(body),
    });
    if (!response.ok) {
      throw new Error(await parseError(response));
    }
    const blob = await response.blob();
    const disposition = response.headers.get("content-disposition") || "";
    const match = /filename="([^"]+)"/.exec(disposition);
    const filename = match?.[1] || "figure.mol";
    return { blob, filename };
  },
  sarProjects: (q = "", cursor?: string, limit = 50) => {
    const params = new URLSearchParams({ limit: String(limit) });
    if (q) params.set("q", q);
    if (cursor) params.set("cursor", cursor);
    const qs = params.toString();
    return request<{ projects: SarProject[]; next_cursor: string | null }>(
      `/api/projects${qs ? `?${qs}` : ""}`
    );
  },
  sarSeries: (projectId: string, cursor?: string, limit = 50) => {
    const params = new URLSearchParams({ limit: String(limit) });
    if (cursor) params.set("cursor", cursor);
    const qs = params.toString();
    return request<{ series: SarSeries[]; next_cursor: string | null }>(
      `/api/projects/${encodeURIComponent(projectId)}/series${qs ? `?${qs}` : ""}`
    );
  },
  sarSnapshot: (
    projectId: string,
    seriesId: string,
    assayIds: string[],
    compoundIds: string[] = []
  ) => {
    const params = new URLSearchParams();
    if (assayIds.length) params.set("assays", assayIds.join(","));
    if (compoundIds.length) params.set("ids", compoundIds.join(","));
    const qs = params.toString();
    return request<SeriesSnapshot>(
      `/api/projects/${encodeURIComponent(projectId)}/series/${encodeURIComponent(seriesId)}${qs ? `?${qs}` : ""}`
    );
  },
  sarAssayFields: () =>
    request<{ assay_fields: SarAssayField[] }>("/api/sar/assay-fields"),
  sarCorePreview: (body: {
    reference_smiles: string;
    core_atoms: number[];
    molecules: { id: string; smiles: string }[];
    ignore_bond_order?: boolean;
    atom_modes?: Record<string, string>;
    remap_smarts?: string;
  }) =>
    request<CorePreviewResult>("/api/sar/core-preview", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  sarCoreAnalogGeneralize: (body: {
    reference_smiles: string;
    core_atoms: number[];
    atom_modes?: Record<string, string>;
    analog_smiles: string;
    analog_atom_index: number;
    ignore_bond_order?: boolean;
  }) =>
    request<{
      ok: boolean;
      message: string;
      core_atoms: number[];
      atom_modes: Record<string, string>;
      mapped_ref_atom: number | null;
    }>("/api/sar/core-analog-generalize", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  sarGuessCore: (body: {
    reference_id?: string;
    molecules: { id: string; smiles: string }[];
    ignore_bond_order?: boolean;
  }) =>
    request<{
      smarts: string;
      source_id: string;
      core_atoms: number[];
      atom_modes: Record<string, string>;
      message: string;
    }>("/api/sar/guess-core", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  sarDepict: (body: {
    smiles: string;
    width?: number;
    height?: number;
    highlight?: number[];
    selected?: number[];
    fragment_atoms?: number[];
    molblock?: string;
    core_atom_modes?: Record<string, string>;
    query_labels?: boolean;
  }) =>
    request<DepictResult>("/api/sar/depict", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  sarRotatePoses: (body: {
    degrees: number;
    molecules: { id: string; smiles?: string; molblock?: string }[];
  }) =>
    request<{ poses: { id: string; molblock: string }[] }>("/api/sar/rotate-poses", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  sarRunAlignment: (body: {
    project_id: string;
    series_id: string;
    database?: string;
    collection?: string;
    compound_ids: string[];
    assay_ids: string[];
    reference_id: string;
    mode?: "same_scaffold" | "ring_atom_replacements" | "scaffold_replacement";
    core_smarts?: string;
    ignore_bond_order?: boolean;
    scaffold_element_mode?: "from_smarts" | "element_agnostic";
    poses?: { id: string; molblock: string }[];
  }) =>
    request<AlignmentRunResult>("/api/alignment/run", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  sarRunAlignmentProgress: async (
    body: {
      project_id: string;
      series_id: string;
      database?: string;
      collection?: string;
      compound_ids: string[];
      assay_ids: string[];
      reference_id: string;
      mode?: "same_scaffold" | "ring_atom_replacements" | "scaffold_replacement";
      core_smarts?: string;
      ignore_bond_order?: boolean;
      scaffold_element_mode?: "from_smarts" | "element_agnostic";
      poses?: { id: string; molblock: string }[];
    },
    onProgress?: (event: { phase: string; done: number; total: number }) => void
  ): Promise<AlignmentRunResult> => {
    const path = "/api/alignment/run-progress";
    const headers = new Headers({ "Content-Type": "application/json" });
    applyMutationHeader(headers, "POST", path);
    const response = await fetch(path, {
      method: "POST",
      credentials: "include",
      headers,
      body: JSON.stringify(body),
    });
    if (!response.ok) {
      throw new Error(await parseError(response));
    }
    if (!response.body) {
      throw new Error("No progress stream from server");
    }
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let result: AlignmentRunResult | undefined;
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() ?? "";
      for (const line of lines) {
        if (!line.trim()) continue;
        const event = JSON.parse(line) as {
          phase: string;
          done?: number;
          total?: number;
          result?: AlignmentRunResult;
          detail?: string;
        };
        if (event.phase === "done" && event.result) {
          result = event.result;
        } else if (event.phase === "error") {
          throw new Error(event.detail || "Alignment failed");
        } else {
          onProgress?.({
            phase: event.phase,
            done: event.done ?? 0,
            total: event.total ?? 0,
          });
        }
      }
    }
    if (!result) {
      throw new Error("Alignment stream ended without a result");
    }
    return result;
  },
  sarCreateAlignmentProject: (body: {
    project_id: string;
    series_id: string;
    database?: string;
    collection?: string;
    compound_ids: string[];
    assay_ids: string[];
    reference_id: string;
    mode: string;
    core_smarts: string;
    snapshot_revision: string;
    draft_solution: AlignmentRunResult;
  }) =>
    request<AlignmentProjectRecord>("/api/alignment-projects", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  sarListAlignmentProjects: (projectId: string, seriesId: string, limit = 12) => {
    const params = new URLSearchParams({
      project_id: projectId,
      series_id: seriesId,
      limit: String(limit),
    });
    return request<{ projects: AlignmentProjectSummary[] }>(`/api/alignment-projects?${params}`);
  },
  sarGetAlignmentProject: (projectId: string) =>
    request<AlignmentProjectRecord>(`/api/alignment-projects/${encodeURIComponent(projectId)}`),
  sarApproveAlignmentProject: (
    projectId: string,
    body: {
      expected_version: number;
      snapshot_revision: string;
      database?: string;
      collection?: string;
    }
  ) =>
    request<AlignmentProjectRecord>(`/api/alignment-projects/${encodeURIComponent(projectId)}/approve`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  auditEvents: (limit = 100) =>
    request<{ events: AuditEvent[] }>(`/api/audit/events?limit=${limit}`),
  deletedCompounds: (db: string, coll: string) =>
    request<{ compounds: TrashCompound[] }>(
      `/api/databases/${encodeURIComponent(db)}/collections/${encodeURIComponent(coll)}/compounds/deleted`
    ),
  restoreCompound: (db: string, coll: string, id: string) =>
    request<Compound>(
      `/api/databases/${encodeURIComponent(db)}/collections/${encodeURIComponent(coll)}/compounds/${encodeURIComponent(id)}/restore`,
      { method: "POST" }
    ),
  importCsv: async (
    db: string,
    coll: string,
    file: File,
    identifierCol: string,
    dataCols: string[],
    onCollision: "append" | "overwrite" = "append"
  ) => {
    const form = new FormData();
    form.append("file", file);
    form.append("identifier_col", identifierCol);
    form.append("data_cols", dataCols.join(","));
    form.append("on_collision", onCollision);
    const body = await request<{
      created: number;
      updated: number;
      appended?: number;
      total: number;
    }>(
      `/api/databases/${encodeURIComponent(db)}/collections/${encodeURIComponent(coll)}/csv/import`,
      { method: "POST", body: form }
    );
    return {
      created: body.created,
      updated: body.updated,
      appended: body.appended ?? 0,
      total: body.total,
    };
  },
};
