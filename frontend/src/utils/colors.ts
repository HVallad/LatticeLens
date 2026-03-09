import type { EdgeType, FactLayer, FactStatus } from '../types/fact';

export const STATUS_COLORS: Record<FactStatus, string> = {
  Active: '#22c55e',
  Draft: '#eab308',
  'Under Review': '#3b82f6',
  Deprecated: '#6b7280',
  Superseded: '#9ca3af',
};

export const LAYER_COLORS: Record<FactLayer, string> = {
  WHY: '#8b5cf6',
  GUARDRAILS: '#f97316',
  HOW: '#06b6d4',
};

export const EDGE_STYLES: Record<EdgeType, { color: string; dash: string }> = {
  drives: { color: '#3b82f6', dash: '' },
  implements: { color: '#3b82f6', dash: '' },
  constrains: { color: '#f97316', dash: '' },
  contradicts: { color: '#ef4444', dash: '6,3' },
  mitigates: { color: '#22c55e', dash: '3,3' },
  depends_on: { color: '#8b5cf6', dash: '' },
  validates: { color: '#14b8a6', dash: '3,3' },
  supersedes: { color: '#6b7280', dash: '6,3' },
  relates: { color: '#9ca3af', dash: '' },
};
