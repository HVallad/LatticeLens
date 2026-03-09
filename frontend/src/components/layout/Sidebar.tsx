import type { Fact } from '../../types/fact';
import { FactList } from '../facts/FactList';
import { FactCard } from '../facts/FactCard';

interface SidebarProps {
  facts: Fact[];
  selectedCode: string | null;
  selectedFact: Fact | null;
  matchingCodes: Set<string> | null;
  onSelect: (code: string) => void;
  onPromote: (code: string) => void;
  onDeprecate: (code: string) => void;
  onEdit: (code: string) => void;
  onNewFact: () => void;
}

export function Sidebar({
  facts,
  selectedCode,
  selectedFact,
  matchingCodes,
  onSelect,
  onPromote,
  onDeprecate,
  onEdit,
  onNewFact,
}: SidebarProps) {
  return (
    <div className="sidebar">
      <div className="sidebar-header">
        <h3>Facts ({facts.length})</h3>
        <button className="btn btn-sm btn-primary" onClick={onNewFact}>
          + New
        </button>
      </div>

      {selectedFact ? (
        <>
          <div style={{ padding: '8px 12px', borderBottom: '1px solid var(--border)' }}>
            <button
              className="btn btn-sm"
              onClick={() => onSelect('')}
              style={{ width: '100%', justifyContent: 'center' }}
            >
              Back to list
            </button>
          </div>
          <FactCard
            fact={selectedFact}
            onSelectCode={onSelect}
            onPromote={onPromote}
            onDeprecate={onDeprecate}
            onEdit={onEdit}
          />
        </>
      ) : (
        <div className="sidebar-content">
          <FactList
            facts={facts}
            selectedCode={selectedCode}
            matchingCodes={matchingCodes}
            onSelect={onSelect}
          />
        </div>
      )}
    </div>
  );
}
