export type FactLayer = 'WHY' | 'GUARDRAILS' | 'HOW';
export type FactStatus = 'Draft' | 'Under Review' | 'Active' | 'Deprecated' | 'Superseded';
export type FactConfidence = 'Confirmed' | 'Provisional' | 'Assumed';
export type EdgeType =
  | 'drives'
  | 'constrains'
  | 'mitigates'
  | 'contradicts'
  | 'implements'
  | 'supersedes'
  | 'validates'
  | 'depends_on'
  | 'relates';

export interface FactRef {
  code: string;
  rel: EdgeType;
}

export interface Fact {
  code: string;
  layer: FactLayer;
  type: string;
  fact: string;
  tags: string[];
  status: FactStatus;
  confidence: FactConfidence;
  version: number;
  refs: FactRef[];
  superseded_by: string | null;
  owner: string;
  review_by: string | null;
  created_at: string;
  updated_at: string;
  projects: string[];
}

export interface TagEntry {
  tag: string;
  count: number;
  category: string;
}

export interface EnumsData {
  layers: FactLayer[];
  statuses: FactStatus[];
  confidences: FactConfidence[];
  edge_types: EdgeType[];
  layer_prefixes: Record<string, string[]>;
  inverse_labels: Record<string, string>;
}
