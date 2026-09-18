export type User = {
  username: string;
  admin: boolean;
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
