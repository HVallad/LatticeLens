"""Type registry — canonical type mapping per code prefix, mitigates RISK-03."""

from __future__ import annotations

from pathlib import Path

from ruamel.yaml import YAML

from lattice_lens.store.protocol import LatticeStore

yaml_rw = YAML()
yaml_rw.default_flow_style = False

TYPES_FILE = "types.yaml"

# Canonical type map — one type string per prefix (from phase5 brief)
CANONICAL_TYPES: dict[str, dict[str, str]] = {
    "WHY": {
        "ADR": "Architecture Decision Record",
        "PRD": "Product Requirement",
        "ETH": "Ethical Finding",
        "DES": "Design Proposal Decision",
    },
    "GUARDRAILS": {
        "MC": "Model Card Entry",
        "AUP": "Acceptable Use Policy Rule",
        "RISK": "Risk Register Entry",
        "DG": "Data Governance Rule",
        "COMP": "Compliance Rule",
    },
    "HOW": {
        "SP": "System Prompt Rule",
        "API": "API Specification",
        "RUN": "Runbook Procedure",
        "ML": "MLOps Rule",
        "MON": "Monitoring Rule",
    },
}

# Flat lookup: prefix -> canonical type
_PREFIX_TO_TYPE: dict[str, str] = {}
for _layer, _prefixes in CANONICAL_TYPES.items():
    for _prefix, _type_name in _prefixes.items():
        _PREFIX_TO_TYPE[_prefix] = _type_name


def canonical_type_for_prefix(prefix: str) -> str | None:
    """Look up the canonical type string for a code prefix."""
    return _PREFIX_TO_TYPE.get(prefix)


def write_type_registry(lattice_root: Path, types_map: dict | None = None) -> Path:
    """Write the type registry to .lattice/types.yaml.

    If types_map is None, uses the default CANONICAL_TYPES.
    """
    path = lattice_root / TYPES_FILE
    data = types_map or CANONICAL_TYPES
    with open(path, "w") as f:
        yaml_rw.dump(data, f)
    return path


def read_type_registry(lattice_root: Path) -> dict | None:
    """Read the existing type registry from .lattice/types.yaml."""
    path = lattice_root / TYPES_FILE
    if not path.exists():
        return None
    with open(path) as f:
        data = yaml_rw.load(f)
    return dict(data) if data else None


def audit_types(store: LatticeStore) -> list[dict]:
    """Find facts whose type doesn't match their prefix's canonical type.

    Returns list of {code, current_type, canonical_type, layer}.
    """
    mismatches = []
    all_statuses = ["Active", "Draft", "Under Review", "Deprecated", "Superseded"]
    facts = store.list_facts(status=all_statuses)
    for fact in facts:
        prefix = fact.code.split("-")[0]
        canonical = canonical_type_for_prefix(prefix)
        if canonical and fact.type != canonical:
            mismatches.append({
                "code": fact.code,
                "current_type": fact.type,
                "canonical_type": canonical,
                "layer": fact.layer.value,
            })
    return mismatches
