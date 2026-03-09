import type { FactLayer } from '../../types/fact';
import { LAYER_COLORS } from '../../utils/colors';

export function LayerIcon({ layer, size = 12 }: { layer: FactLayer; size?: number }) {
  const color = LAYER_COLORS[layer];
  const half = size / 2;

  if (layer === 'WHY') {
    return (
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        <circle cx={half} cy={half} r={half - 1} fill={color} />
      </svg>
    );
  }

  if (layer === 'GUARDRAILS') {
    // Diamond
    return (
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        <polygon
          points={`${half},1 ${size - 1},${half} ${half},${size - 1} 1,${half}`}
          fill={color}
        />
      </svg>
    );
  }

  // HOW = square
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
      <rect x={1} y={1} width={size - 2} height={size - 2} fill={color} rx={1} />
    </svg>
  );
}
