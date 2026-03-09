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
