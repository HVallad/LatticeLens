import type { Fact } from '../../types/fact';
import { STATUS_COLORS } from '../../utils/colors';

interface FactListItemProps {
  fact: Fact;
  selected: boolean;
  dimmed: boolean;
  onClick: () => void;
}

export function FactListItem({ fact, selected, dimmed, onClick }: FactListItemProps) {
  return (
    <div
      className={`fact-item ${selected ? 'selected' : ''} ${dimmed ? 'dimmed' : ''}`}
      onClick={onClick}
    >
      <span
        className="fact-item-status"
        style={{ background: STATUS_COLORS[fact.status] }}
      />
      <span className="fact-item-code">{fact.code}</span>
    </div>
  );
}
