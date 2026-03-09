import type { FactStatus } from '../../types/fact';
import { STATUS_COLORS } from '../../utils/colors';

export function StatusBadge({ status }: { status: FactStatus }) {
  return (
    <span
      className="badge"
      style={{ background: STATUS_COLORS[status] + '20', color: STATUS_COLORS[status] }}
    >
      <span
        style={{
          width: 6,
          height: 6,
          borderRadius: '50%',
          background: STATUS_COLORS[status],
        }}
      />
      {status}
    </span>
  );
}
