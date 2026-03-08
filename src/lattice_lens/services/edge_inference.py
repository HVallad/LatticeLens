"""Edge type inference from code prefix pairs.

Used during migration (0.6.0 → 0.7.0) to convert untyped string refs
to typed FactRef objects with inferred edge types.
"""

from __future__ import annotations

from lattice_lens.config import LAYER_PREFIXES
from lattice_lens.models import EdgeType

# Prefix-pair heuristics: (source_prefix, target_prefix) -> EdgeType
_PREFIX_PAIR_MAP: dict[tuple[str, str], EdgeType] = {
    # PRD drives ADR
    ("PRD", "ADR"): EdgeType.DRIVES,
    ("ADR", "DES"): EdgeType.DRIVES,
    ("ADR", "SP"): EdgeType.DRIVES,
    ("ADR", "API"): EdgeType.DRIVES,
    ("PRD", "DES"): EdgeType.DRIVES,
    # ADR mitigates RISK
    ("ADR", "RISK"): EdgeType.MITIGATES,
    ("DES", "RISK"): EdgeType.MITIGATES,
    ("SP", "RISK"): EdgeType.MITIGATES,
    # MON validates RISK
    ("MON", "RISK"): EdgeType.VALIDATES,
    ("MON", "AUP"): EdgeType.VALIDATES,
    ("MON", "DG"): EdgeType.VALIDATES,
    # RISK constrains ADR/DES
    ("RISK", "ADR"): EdgeType.CONSTRAINS,
    ("RISK", "DES"): EdgeType.CONSTRAINS,
    ("AUP", "SP"): EdgeType.CONSTRAINS,
    ("AUP", "API"): EdgeType.CONSTRAINS,
    ("DG", "SP"): EdgeType.CONSTRAINS,
    ("COMP", "SP"): EdgeType.CONSTRAINS,
    # SP/API/RUN implements DES/ADR
    ("SP", "DES"): EdgeType.IMPLEMENTS,
    ("API", "DES"): EdgeType.IMPLEMENTS,
    ("RUN", "DES"): EdgeType.IMPLEMENTS,
    ("SP", "ADR"): EdgeType.IMPLEMENTS,
    ("API", "ADR"): EdgeType.IMPLEMENTS,
    # DES depends_on DES
    ("DES", "DES"): EdgeType.DEPENDS_ON,
    ("SP", "SP"): EdgeType.DEPENDS_ON,
    ("API", "API"): EdgeType.DEPENDS_ON,
    ("RUN", "RUN"): EdgeType.DEPENDS_ON,
    ("RUN", "MON"): EdgeType.DEPENDS_ON,
}

# Build reverse map: prefix -> layer
_PREFIX_TO_LAYER: dict[str, str] = {}
for _layer, _prefixes in LAYER_PREFIXES.items():
    for _prefix in _prefixes:
        _PREFIX_TO_LAYER[_prefix] = _layer

# Layer-pair fallbacks: (source_layer, target_layer) -> EdgeType
_LAYER_PAIR_MAP: dict[tuple[str, str], EdgeType] = {
    ("WHY", "HOW"): EdgeType.DRIVES,
    ("HOW", "WHY"): EdgeType.IMPLEMENTS,
    ("GUARDRAILS", "WHY"): EdgeType.CONSTRAINS,
    ("GUARDRAILS", "HOW"): EdgeType.CONSTRAINS,
    ("HOW", "HOW"): EdgeType.DEPENDS_ON,
    ("WHY", "WHY"): EdgeType.RELATES,
    ("HOW", "GUARDRAILS"): EdgeType.VALIDATES,
    ("WHY", "GUARDRAILS"): EdgeType.MITIGATES,
    ("GUARDRAILS", "GUARDRAILS"): EdgeType.RELATES,
}


def infer_edge_type(source_code: str, target_code: str) -> EdgeType:
    """Infer edge type from source and target code prefixes.

    Priority:
    1. Exact prefix-pair match (e.g., PRD→ADR = drives)
    2. Layer-pair fallback (e.g., WHY→HOW = drives)
    3. Default: relates
    """
    source_prefix = source_code.split("-")[0]
    target_prefix = target_code.split("-")[0]

    # Try exact prefix pair
    edge = _PREFIX_PAIR_MAP.get((source_prefix, target_prefix))
    if edge is not None:
        return edge

    # Try layer pair fallback
    source_layer = _PREFIX_TO_LAYER.get(source_prefix)
    target_layer = _PREFIX_TO_LAYER.get(target_prefix)
    if source_layer and target_layer:
        edge = _LAYER_PAIR_MAP.get((source_layer, target_layer))
        if edge is not None:
            return edge

    return EdgeType.RELATES
