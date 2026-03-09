import { useState } from 'react';
import type { Fact } from '../../types/fact';
import { FactListItem } from './FactListItem';

interface FactListProps {
  facts: Fact[];
  selectedCode: string | null;
  matchingCodes: Set<string> | null;
  onSelect: (code: string) => void;
}

export function FactList({ facts, selectedCode, matchingCodes, onSelect }: FactListProps) {
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});

  // Group by type prefix
  const groups = new Map<string, Fact[]>();
  for (const fact of facts) {
    const prefix = fact.code.split('-')[0];
    if (!groups.has(prefix)) groups.set(prefix, []);
    groups.get(prefix)!.push(fact);
  }

  // Sort groups by prefix, facts within by numeric suffix
  const sortedGroups = [...groups.entries()].sort(([a], [b]) => a.localeCompare(b));
  for (const [, groupFacts] of sortedGroups) {
    groupFacts.sort((a, b) => {
      const numA = parseInt(a.code.split('-')[1]);
      const numB = parseInt(b.code.split('-')[1]);
      return numA - numB;
    });
  }

  const toggleGroup = (prefix: string) => {
    setCollapsed((prev) => ({ ...prev, [prefix]: !prev[prefix] }));
  };

  if (facts.length === 0) {
    return <div className="empty-state">No facts found</div>;
  }

  return (
    <div>
      {sortedGroups.map(([prefix, groupFacts]) => (
        <div key={prefix} className="fact-group">
          <div className="fact-group-header" onClick={() => toggleGroup(prefix)}>
            <span>
              {collapsed[prefix] ? '>' : 'v'} {prefix}
            </span>
            <span className="fact-group-count">{groupFacts.length}</span>
          </div>
          {!collapsed[prefix] &&
            groupFacts.map((fact) => (
              <FactListItem
                key={fact.code}
                fact={fact}
                selected={fact.code === selectedCode}
                dimmed={matchingCodes !== null && !matchingCodes.has(fact.code)}
                onClick={() => onSelect(fact.code)}
              />
            ))}
        </div>
      ))}
    </div>
  );
}
