import type { FactLayer, FactStatus } from '../../types/fact';

interface FilterPanelProps {
  layers: FactLayer[];
  activeLayer: FactLayer | null;
  onLayerChange: (layer: FactLayer | null) => void;
  statusFilters: FactStatus[];
  activeStatuses: Set<FactStatus>;
  onStatusToggle: (status: FactStatus) => void;
}

export function FilterPanel({
  layers,
  activeLayer,
  onLayerChange,
  statusFilters,
  activeStatuses,
  onStatusToggle,
}: FilterPanelProps) {
  return (
    <div className="filter-bar">
      {layers.map((layer) => (
        <button
          key={layer}
          className={`filter-chip ${activeLayer === layer ? 'active' : ''}`}
          onClick={() => onLayerChange(activeLayer === layer ? null : layer)}
        >
          {layer}
        </button>
      ))}
      <span style={{ width: 1, background: 'var(--border)', margin: '0 2px' }} />
      {statusFilters.map((status) => (
        <button
          key={status}
          className={`filter-chip ${activeStatuses.has(status) ? 'active' : ''}`}
          onClick={() => onStatusToggle(status)}
        >
          {status}
        </button>
      ))}
    </div>
  );
}
