import { useState } from 'react';
import type { GraphLayout, HighlightSettings } from '../../types/graph';
import type { FactLayer, FactStatus, TagEntry } from '../../types/fact';
import { HighlightControls } from '../search/HighlightControls';

interface GraphControlsProps {
  layout: GraphLayout;
  onToggleLayout: () => void;
  highlightSettings: HighlightSettings;
  onHighlightChange: (settings: HighlightSettings) => void;
  tags: TagEntry[];
  layers: FactLayer[];
  statuses: FactStatus[];
}

export function GraphControls({
  layout,
  onToggleLayout,
  highlightSettings,
  onHighlightChange,
  tags,
  layers,
  statuses,
}: GraphControlsProps) {
  const [showPanel, setShowPanel] = useState(false);

  return (
    <div className="graph-controls">
      <button className="btn btn-sm" onClick={onToggleLayout}>
        {layout === 'force' ? 'Layered' : 'Force'}
      </button>
      <button
        className={`btn btn-sm ${showPanel ? 'btn-primary' : ''}`}
        onClick={() => setShowPanel((v) => !v)}
      >
        Highlight
      </button>
      {showPanel && (
        <div className="highlight-panel">
          <HighlightControls
            settings={highlightSettings}
            onChange={onHighlightChange}
            tags={tags}
            layers={layers}
            statuses={statuses}
          />
        </div>
      )}
    </div>
  );
}
