export type User = {
  username: string;
  admin: boolean;
  kind: "student" | "employee";
  can_manage_permissions: boolean;
};

export type CollectionAccessPolicy = {
  database: string;
  collection: string;
  owner: string | null;
  visibility:
    | "owner_only"
    | "employees"
    | "students"
    | "employees_and_students"
    | "custom";
  custom_users: string[];
  student_access: "none" | "viewer" | "editor";
  employee_access: "none" | "viewer" | "editor";
};

export type FieldSpec = {
  type: string;
  default: unknown;
};

export type CompoundSchema = {
  fields: Record<string, FieldSpec>;
  defaults: Record<string, unknown>;
  visible_columns: string[];
  csv_identifiers: string[];
};

export type Compound = Record<string, unknown> & { _id: string };

export type AuditEvent = {
  at: string;
  actor: string | null;
  action: string;
  target: string;
  summary?: Record<string, unknown>;
  request_id?: string | null;
};

export type TrashCompound = Compound & {
  deleted_at?: string | null;
  deleted_by?: string | null;
  Name?: string;
};

export type SimilarityHit = {
  document: Compound;
  similarity: number;
};

export type SubstructureHit = {
  document: Compound;
  match_atoms: number[];
};

export type SearchMetrics = {
  default: string;
  metrics: string[];
  cutoffs: Record<string, number>;
  descriptions: Record<string, string>;
};

export type SarProject = { id: string; name: string };

export type SarSeries = { id: string; project_id: string; name: string };

export type SarAssayField = {
  id: string;
  name: string;
  type: string;
  default_unit: string | null;
};

export type SarMeasurement = {
  assay_id: string;
  value: number | null;
  qualifier: string;
  unit: string | null;
  uncertainty: number | null;
  display_value: string;
  revision: string;
};

export type SarCompoundSnapshot = {
  id: string;
  display_id: string;
  revision: string;
  structure: {
    format: string;
    value: string;
    fingerprint: string;
    coordinates_2d_source: string | null;
  };
  measurements: SarMeasurement[];
};

export type SeriesSnapshot = {
  source: { system_id: string; snapshot_at: string; revision: string };
  series: {
    id: string;
    project_id: string;
    name: string;
    description: string | null;
  };
  compounds: SarCompoundSnapshot[];
  assay_definitions: {
    id: string;
    name: string;
    description: string | null;
    default_unit: string | null;
    conditions: Record<string, unknown>;
  }[];
};

export type AlignmentRunResult = {
  status: string;
  certificate: string | null;
  user_message: string;
  unsupported_reason: string | null;
  objective: number[] | null;
  snapshot_revision: string | null;
  details: Record<string, unknown>;
  layouts: {
    molecule_id: string;
    display_id: string;
    smiles: string;
    molblock?: string | null;
    core_atom_indices?: number[];
    core_atom_count: number;
  }[];
};

export type AlignmentProjectRecord = {
  id: string;
  version: number;
  owner: string;
  project_id: string;
  series_id: string;
  compound_ids: string[];
  assay_ids: string[];
  reference_id: string;
  mode: "same_scaffold" | "ring_atom_replacements" | "scaffold_replacement" | string;
  core_smarts: string;
  snapshot_revision: string;
  draft_solution?: AlignmentRunResult;
  approval: {
    approved_at: string;
    approved_by: string;
    snapshot_revision: string;
    solution_version: number;
  } | null;
  audit: { action: string; at: string; by: string }[];
};

export type AlignmentProjectSummary = {
  id: string;
  version: number;
  owner: string;
  project_id: string;
  series_id: string;
  compound_count: number;
  mode: string;
  core_smarts: string;
  approved: boolean;
  updated_at: string;
  reference_id: string;
};

export type CoreAtomMode = "exact" | "group" | "hetero" | "any";

export type CorePreviewMatch = {
  id: string;
  matched: boolean;
  atom_indices: number[];
};

export type CorePreviewResult = {
  smarts: string;
  core_atoms: number[];
  connected: boolean;
  message: string;
  generalized_atoms: number[];
  atom_modes: Record<string, string>;
  matches: CorePreviewMatch[];
};

export type DepictAtom = {
  idx: number;
  x: number;
  y: number;
  symbol: string;
  atomic_num: number;
  charge: number;
  aromatic: boolean;
  selected: boolean;
  matched: boolean;
  neighbors: number[];
  query_label?: string;
};

export type DepictResult = {
  svg: string;
  width: number;
  height: number;
  atoms: DepictAtom[];
};
