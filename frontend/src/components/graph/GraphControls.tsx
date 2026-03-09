import type { GraphLayout } from '../../types/graph';

interface GraphControlsProps {
  layout: GraphLayout;
  onToggleLayout: () => void;
}

export function GraphControls({ layout, onToggleLayout }: GraphControlsProps) {
  return (
    <div className="graph-controls">
      <button className="btn btn-sm" onClick={onToggleLayout}>
        {layout === 'force' ? 'Layered' : 'Force'}
      </button>
    </div>
  );
}
