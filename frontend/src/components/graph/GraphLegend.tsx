import { useState } from 'react';
import { STATUS_COLORS, LAYER_COLORS, EDGE_STYLES } from '../../utils/colors';
import type { FactStatus, FactLayer, EdgeType } from '../../types/fact';

const LAYER_SHAPES: Record<FactLayer, string> = {
  WHY: 'circle',
  GUARDRAILS: 'diamond',
  HOW: 'square',
};

export function GraphLegend() {
  const [visible, setVisible] = useState(true);

  if (!visible) {
    return (
      <button
        className="btn btn-sm graph-legend-toggle"
        onClick={() => setVisible(true)}
        title="Show legend"
      >
        Legend
      </button>
    );
  }

  return (
    <div className="graph-legend">
      <div className="legend-header">
        <span className="legend-title">Legend</span>
        <button
          className="legend-close"
          onClick={() => setVisible(false)}
          title="Hide legend"
        >
          &times;
        </button>
      </div>

      {/* Node shapes by layer */}
      <div className="legend-section">
        <div className="legend-section-title">Layers (shape)</div>
        {(Object.entries(LAYER_SHAPES) as [FactLayer, string][]).map(([layer, shape]) => (
          <div className="legend-row" key={layer}>
            <svg className="legend-shape" viewBox="0 0 14 14">
              {shape === 'circle' && (
                <circle cx="7" cy="7" r="6" fill={LAYER_COLORS[layer]} />
              )}
              {shape === 'diamond' && (
                <polygon points="7,1 13,7 7,13 1,7" fill={LAYER_COLORS[layer]} />
              )}
              {shape === 'square' && (
                <rect x="1" y="1" width="12" height="12" rx="2" fill={LAYER_COLORS[layer]} />
              )}
            </svg>
            <span>{layer}</span>
          </div>
        ))}
      </div>

      {/* Node colors by status */}
      <div className="legend-section">
        <div className="legend-section-title">Status (color)</div>
        {(Object.entries(STATUS_COLORS) as [FactStatus, string][]).map(([status, color]) => (
          <div className="legend-row" key={status}>
            <svg className="legend-shape" viewBox="0 0 14 14">
              <circle cx="7" cy="7" r="6" fill={color} />
            </svg>
            <span>{status}</span>
          </div>
        ))}
      </div>

      {/* Edge types */}
      <div className="legend-section">
        <div className="legend-section-title">Edges (relationship)</div>
        {(Object.entries(EDGE_STYLES) as [EdgeType, { color: string; dash: string }][]).map(
          ([rel, style]) => (
            <div className="legend-row" key={rel}>
              <svg className="legend-line" viewBox="0 0 28 4">
                <line
                  x1="0"
                  y1="2"
                  x2="28"
                  y2="2"
                  stroke={style.color}
                  strokeWidth="2"
                  strokeDasharray={style.dash || undefined}
                />
              </svg>
              <span>{rel.replace('_', ' ')}</span>
            </div>
          )
        )}
      </div>
    </div>
  );
}
