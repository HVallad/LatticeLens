import type {
  HighlightSettings,
  HighlightMode,
  HighlightCriterion,
} from '../../types/graph';
import type { FactLayer, FactStatus, TagEntry } from '../../types/fact';

interface HighlightControlsProps {
  settings: HighlightSettings;
  onChange: (settings: HighlightSettings) => void;
  tags: TagEntry[];
  layers: FactLayer[];
  statuses: FactStatus[];
}

const PRESET_COLORS = [
  { label: 'Default', value: '' },
  { label: 'Red', value: '#ef4444' },
  { label: 'Orange', value: '#f97316' },
  { label: 'Yellow', value: '#eab308' },
  { label: 'Green', value: '#22c55e' },
  { label: 'Blue', value: '#3b82f6' },
  { label: 'Purple', value: '#8b5cf6' },
  { label: 'Cyan', value: '#06b6d4' },
];

export function HighlightControls({
  settings,
  onChange,
  tags,
  layers,
  statuses,
}: HighlightControlsProps) {
  const update = (partial: Partial<HighlightSettings>) =>
    onChange({ ...settings, ...partial });

  return (
    <div className="highlight-controls">
      <div className="highlight-section">
        <label className="highlight-label">Highlight by</label>
        <div className="highlight-row">
          {(['search', 'tag', 'layer', 'status'] as HighlightCriterion[]).map(
            (c) => (
              <button
                key={c}
                className={`filter-chip ${settings.criterion === c ? 'active' : ''}`}
                onClick={() => update({ criterion: c, value: '' })}
              >
                {c}
              </button>
            )
          )}
        </div>
      </div>

      {/* Value selector based on criterion */}
      {settings.criterion === 'tag' && (
        <div className="highlight-section">
          <label className="highlight-label">Tag</label>
          <select
            className="highlight-select"
            value={settings.value}
            onChange={(e) => update({ value: e.target.value })}
          >
            <option value="">All tags...</option>
            {tags.map((t) => (
              <option key={t.tag} value={t.tag}>
                {t.tag} ({t.count})
              </option>
            ))}
          </select>
        </div>
      )}

      {settings.criterion === 'layer' && (
        <div className="highlight-section">
          <label className="highlight-label">Layer</label>
          <div className="highlight-row">
            {layers.map((l) => (
              <button
                key={l}
                className={`filter-chip ${settings.value === l ? 'active' : ''}`}
                onClick={() => update({ value: settings.value === l ? '' : l })}
              >
                {l}
              </button>
            ))}
          </div>
        </div>
      )}

      {settings.criterion === 'status' && (
        <div className="highlight-section">
          <label className="highlight-label">Status</label>
          <div className="highlight-row">
            {statuses.map((s) => (
              <button
                key={s}
                className={`filter-chip ${settings.value === s ? 'active' : ''}`}
                onClick={() => update({ value: settings.value === s ? '' : s })}
              >
                {s}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Mode: highlight vs filter */}
      <div className="highlight-section">
        <label className="highlight-label">Mode</label>
        <div className="highlight-row">
          {(['highlight', 'filter'] as HighlightMode[]).map((m) => (
            <button
              key={m}
              className={`filter-chip ${settings.mode === m ? 'active' : ''}`}
              onClick={() => update({ mode: m })}
            >
              {m === 'highlight' ? 'Dim others' : 'Hide others'}
            </button>
          ))}
        </div>
      </div>

      {/* Dim opacity slider — only shown in highlight mode */}
      {settings.mode === 'highlight' && (
        <div className="highlight-section">
          <label className="highlight-label">
            Dim intensity: {Math.round((1 - settings.dimOpacity) * 100)}%
          </label>
          <input
            type="range"
            className="highlight-slider"
            min="0"
            max="100"
            value={Math.round(settings.dimOpacity * 100)}
            onChange={(e) =>
              update({ dimOpacity: Number(e.target.value) / 100 })
            }
          />
        </div>
      )}

      {/* Highlight color */}
      <div className="highlight-section">
        <label className="highlight-label">Highlight color</label>
        <div className="highlight-row">
          {PRESET_COLORS.map((c) => (
            <button
              key={c.label}
              className={`color-swatch ${settings.highlightColor === c.value ? 'active' : ''}`}
              style={{
                background: c.value || 'var(--text-muted)',
                ...(c.value === '' ? { border: '2px dashed var(--border)' } : {}),
              }}
              title={c.label}
              onClick={() => update({ highlightColor: c.value })}
            />
          ))}
        </div>
      </div>

      {/* Glow toggle */}
      <div className="highlight-section">
        <label
          className="highlight-label"
          style={{ display: 'flex', alignItems: 'center', gap: 8 }}
        >
          <input
            type="checkbox"
            checked={settings.showGlow}
            onChange={(e) => update({ showGlow: e.target.checked })}
          />
          Show glow on matches
        </label>
      </div>
    </div>
  );
}
