import { useState } from 'react';
import type { Fact, EnumsData } from '../../types/fact';

interface EditPanelProps {
  mode: 'create' | 'edit';
  fact?: Fact | null;
  enums: EnumsData;
  onSave: (data: any) => void;
  onClose: () => void;
}

export function EditPanel({ mode, fact, enums, onSave, onClose }: EditPanelProps) {
  const [prefix, setPrefix] = useState(fact ? fact.code.split('-')[0] : 'ADR');
  const [layer, setLayer] = useState<string>(fact?.layer || 'WHY');
  const [type, setType] = useState(fact?.type || 'Architecture Decision Record');
  const [factText, setFactText] = useState(fact?.fact || '');
  const [tagsStr, setTagsStr] = useState(fact?.tags.join(', ') || '');
  const [owner, setOwner] = useState(fact?.owner || '');
  const [reason, setReason] = useState('');

  // Auto-set layer when prefix changes
  const handlePrefixChange = (newPrefix: string) => {
    setPrefix(newPrefix);
    for (const [layerName, prefixes] of Object.entries(enums.layer_prefixes)) {
      if (prefixes.includes(newPrefix)) {
        setLayer(layerName);
        break;
      }
    }
  };

  const handleSubmit = () => {
    const tags = tagsStr
      .split(',')
      .map((t) => t.trim().toLowerCase())
      .filter(Boolean);

    if (mode === 'create') {
      onSave({
        prefix,
        layer,
        type,
        fact: factText,
        tags,
        owner,
      });
    } else {
      onSave({
        code: fact!.code,
        changes: { fact: factText, tags, owner, type },
        reason,
      });
    }
  };

  const allPrefixes = Object.values(enums.layer_prefixes).flat();

  return (
    <div className="edit-panel">
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <h3 style={{ fontSize: 16, fontWeight: 600 }}>
          {mode === 'create' ? 'New Fact' : `Edit ${fact?.code}`}
        </h3>
        <button className="btn-icon" onClick={onClose}>
          X
        </button>
      </div>

      {mode === 'create' && (
        <div className="form-group">
          <label className="form-label">Prefix</label>
          <select
            className="form-select"
            value={prefix}
            onChange={(e) => handlePrefixChange(e.target.value)}
          >
            {allPrefixes.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
        </div>
      )}

      <div className="form-group">
        <label className="form-label">Layer</label>
        <input className="form-input" value={layer} readOnly />
      </div>

      <div className="form-group">
        <label className="form-label">Type</label>
        <input
          className="form-input"
          value={type}
          onChange={(e) => setType(e.target.value)}
        />
      </div>

      <div className="form-group">
        <label className="form-label">Fact Text</label>
        <textarea
          className="form-textarea"
          value={factText}
          onChange={(e) => setFactText(e.target.value)}
          placeholder="Minimum 10 characters..."
        />
      </div>

      <div className="form-group">
        <label className="form-label">Tags (comma-separated, min 2)</label>
        <input
          className="form-input"
          value={tagsStr}
          onChange={(e) => setTagsStr(e.target.value)}
          placeholder="e.g. architecture, security"
        />
      </div>

      <div className="form-group">
        <label className="form-label">Owner</label>
        <input
          className="form-input"
          value={owner}
          onChange={(e) => setOwner(e.target.value)}
          placeholder="Team or person responsible"
        />
      </div>

      {mode === 'edit' && (
        <div className="form-group">
          <label className="form-label">Reason for change</label>
          <input
            className="form-input"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="Required"
          />
        </div>
      )}

      <div style={{ display: 'flex', gap: 8, marginTop: 16 }}>
        <button className="btn btn-primary" onClick={handleSubmit}>
          {mode === 'create' ? 'Create' : 'Save'}
        </button>
        <button className="btn" onClick={onClose}>
          Cancel
        </button>
      </div>
    </div>
  );
}
