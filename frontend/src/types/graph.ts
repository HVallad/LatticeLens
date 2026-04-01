import type { EdgeType, FactConfidence, FactLayer, FactStatus } from './fact';

export interface GraphNode {
  code: string;
  layer: FactLayer;
  type: string;
  status: FactStatus;
  confidence: FactConfidence;
  tags: string[];
  fact: string;
  owner: string;
  version: number;
  // D3 simulation properties
  x?: number;
  y?: number;
  vx?: number;
  vy?: number;
  fx?: number | null;
  fy?: number | null;
}

export interface GraphEdge {
  source: string | GraphNode;
  target: string | GraphNode;
  rel: EdgeType;
}

export interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export type GraphLayout = 'force' | 'layered';

/** Controls how matched nodes are visually emphasized. */
export type HighlightMode = 'highlight' | 'filter';

/** Criterion for highlighting nodes. */
export type HighlightCriterion = 'search' | 'tag' | 'layer' | 'status';

export interface HighlightSettings {
  /** 'highlight' dims non-matches; 'filter' hides them entirely. */
  mode: HighlightMode;
  /** Which property to match against. */
  criterion: HighlightCriterion;
  /** The value to match (search text, tag name, layer, or status). */
  value: string;
  /** Opacity for non-matching nodes in highlight mode (0.0 - 1.0). */
  dimOpacity: number;
  /** Custom highlight color (CSS color string) or empty for default. */
  highlightColor: string;
  /** Whether to apply a glow ring around matching nodes. */
  showGlow: boolean;
}
