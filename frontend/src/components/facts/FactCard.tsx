import type { Fact } from '../../types/fact';
import { StatusBadge } from '../common/StatusBadge';
import { LayerIcon } from '../common/LayerIcon';

interface FactCardProps {
  fact: Fact;
  onSelectCode: (code: string) => void;
  onPromote?: (code: string) => void;
  onDeprecate?: (code: string) => void;
  onEdit?: (code: string) => void;
}

export function FactCard({ fact, onSelectCode, onPromote, onDeprecate, onEdit }: FactCardProps) {
  const isPromotable = fact.status === 'Draft' || fact.status === 'Under Review';
  const isDeprecatable = fact.status !== 'Deprecated' && fact.status !== 'Superseded';

  return (
    <div className="fact-card">
      <div className="fact-card-header">
        <span className="fact-card-code">{fact.code}</span>
        <StatusBadge status={fact.status} />
      </div>

      <div className="fact-card-meta">
        <span className="badge" style={{ background: 'var(--bg-tertiary)' }}>
          <LayerIcon layer={fact.layer} size={10} />
          {fact.layer}
        </span>
        <span className="badge" style={{ background: 'var(--bg-tertiary)' }}>
          {fact.type}
        </span>
        <span className="badge" style={{ background: 'var(--bg-tertiary)' }}>
          v{fact.version}
        </span>
        <span className="badge" style={{ background: 'var(--bg-tertiary)' }}>
          {fact.confidence}
        </span>
      </div>

      <div className="fact-card-text">{fact.fact}</div>

      <div className="fact-card-section">
        <h4>Tags</h4>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
          {fact.tags.map((tag) => (
            <span key={tag} className="tag">
              {tag}
            </span>
          ))}
        </div>
      </div>

      {fact.refs.length > 0 && (
        <div className="fact-card-section">
          <h4>References</h4>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
            {fact.refs.map((ref, i) => (
              <span key={i} className="ref-link" onClick={() => onSelectCode(ref.code)}>
                {ref.code}
                <span className="ref-rel">{ref.rel}</span>
              </span>
            ))}
          </div>
        </div>
      )}

      <div className="fact-card-section">
        <h4>Owner</h4>
        <span style={{ fontSize: 13 }}>{fact.owner}</span>
      </div>

      {fact.projects.length > 0 && (
        <div className="fact-card-section">
          <h4>Projects</h4>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
            {fact.projects.map((p) => (
              <span key={p} className="tag">{p}</span>
            ))}
          </div>
        </div>
      )}

      <div className="fact-card-section" style={{ fontSize: 11, color: 'var(--text-muted)' }}>
        Created: {new Date(fact.created_at).toLocaleDateString()} | Updated:{' '}
        {new Date(fact.updated_at).toLocaleDateString()}
        {fact.review_by && <> | Review by: {fact.review_by}</>}
      </div>

      <div className="fact-card-actions">
        {onEdit && (
          <button className="btn btn-sm" onClick={() => onEdit(fact.code)}>
            Edit
          </button>
        )}
        {isPromotable && onPromote && (
          <button className="btn btn-sm btn-primary" onClick={() => onPromote(fact.code)}>
            Promote
          </button>
        )}
        {isDeprecatable && onDeprecate && (
          <button className="btn btn-sm" onClick={() => onDeprecate(fact.code)}>
            Deprecate
          </button>
        )}
      </div>
    </div>
  );
}
