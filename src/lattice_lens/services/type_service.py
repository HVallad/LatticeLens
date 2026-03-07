"""Type registry — canonical type mapping per code prefix, mitigates RISK-03."""

from __future__ import annotations

from pathlib import Path

from ruamel.yaml import YAML

from lattice_lens.store.protocol import LatticeStore

yaml_rw = YAML()
yaml_rw.default_flow_style = False

TYPES_FILE = "types.yaml"

# Canonical type map — one entry per prefix with name and description.
CANONICAL_TYPES: dict[str, dict[str, dict[str, str]]] = {
    "WHY": {
        "ADR": {
            "name": "Architecture Decision Record",
            "description": "Captures architectural choices with context, alternatives considered, and rationale for the selected approach",
        },
        "PRD": {
            "name": "Product Requirement",
            "description": "Defines what the system must do — functional requirements, acceptance criteria, and success metrics",
        },
        "ETH": {
            "name": "Ethical Finding",
            "description": "Documents ethical considerations, bias assessments, and fairness evaluations for AI system behavior",
        },
        "DES": {
            "name": "Design Proposal Decision",
            "description": "Records design-level decisions (API shape, data models, UX flows) that don't rise to full ADR scope",
        },
    },
    "GUARDRAILS": {
        "MC": {
            "name": "Model Card Entry",
            "description": "Documents AI model characteristics — capabilities, limitations, intended use, and known failure modes",
        },
        "AUP": {
            "name": "Acceptable Use Policy Rule",
            "description": "Defines hard constraints on system behavior — what the system must always or never do",
        },
        "RISK": {
            "name": "Risk Register Entry",
            "description": "Tracks identified risks with severity, likelihood, mitigation strategies, and residual risk levels",
        },
        "DG": {
            "name": "Data Governance Rule",
            "description": "Specifies data handling requirements — retention, access controls, PII treatment, and audit obligations",
        },
        "COMP": {
            "name": "Compliance Rule",
            "description": "Captures regulatory and standards compliance requirements (SOC 2, GDPR, ISO, industry-specific)",
        },
    },
    "HOW": {
        "SP": {
            "name": "System Prompt Rule",
            "description": "Defines rules and instructions that shape AI agent behavior at runtime via system prompts",
        },
        "API": {
            "name": "API Specification",
            "description": "Documents API contracts — endpoints, schemas, authentication, rate limits, and versioning policies",
        },
        "RUN": {
            "name": "Runbook Procedure",
            "description": "Step-by-step operational procedures for deployment, rollback, incident response, and maintenance",
        },
        "ML": {
            "name": "MLOps Rule",
            "description": "Specifies ML pipeline requirements — training schedules, evaluation thresholds, model versioning, and drift detection",
        },
        "MON": {
            "name": "Monitoring Rule",
            "description": "Defines what to monitor, alert thresholds, escalation paths, and observability requirements",
        },
    },
}

# Flat lookups: prefix -> name, prefix -> description
_PREFIX_TO_TYPE: dict[str, str] = {}
_PREFIX_TO_DESC: dict[str, str] = {}
for _layer, _prefixes in CANONICAL_TYPES.items():
    for _prefix, _info in _prefixes.items():
        _PREFIX_TO_TYPE[_prefix] = _info["name"]
        _PREFIX_TO_DESC[_prefix] = _info["description"]


def canonical_type_for_prefix(prefix: str) -> str | None:
    """Look up the canonical type string for a code prefix."""
    return _PREFIX_TO_TYPE.get(prefix)


def description_for_prefix(prefix: str) -> str | None:
    """Look up the description for a code prefix."""
    return _PREFIX_TO_DESC.get(prefix)


def _to_flat_registry(types_map: dict) -> dict:
    """Convert enriched CANONICAL_TYPES to flat {layer: {prefix: name}} for YAML output."""
    flat: dict[str, dict[str, str]] = {}
    for layer, prefixes in types_map.items():
        flat[layer] = {}
        for prefix, info in prefixes.items():
            if isinstance(info, dict):
                flat[layer][prefix] = info["name"]
            else:
                # Already flat (legacy or custom input)
                flat[layer][prefix] = info
    return flat


def write_type_registry(lattice_root: Path, types_map: dict | None = None) -> Path:
    """Write the type registry to .lattice/types.yaml.

    Writes the enriched format with name and description per prefix.
    If types_map is None, uses the default CANONICAL_TYPES.
    """
    path = lattice_root / TYPES_FILE
    data = types_map or CANONICAL_TYPES
    with open(path, "w") as f:
        yaml_rw.dump(data, f)
    return path


def read_type_registry(lattice_root: Path) -> dict | None:
    """Read the existing type registry from .lattice/types.yaml.

    Handles both legacy flat format ({layer: {prefix: name}}) and
    enriched format ({layer: {prefix: {name, description}}}).
    """
    path = lattice_root / TYPES_FILE
    if not path.exists():
        return None
    with open(path) as f:
        data = yaml_rw.load(f)
    return dict(data) if data else None


def is_enriched_registry(registry: dict) -> bool:
    """Check if a registry uses the enriched format (with descriptions)."""
    for _layer, prefixes in registry.items():
        for _prefix, info in prefixes.items():
            return isinstance(info, dict)
    return False


def get_type_name(registry: dict, layer: str, prefix: str) -> str | None:
    """Get type name from a registry, handling both flat and enriched formats."""
    info = registry.get(layer, {}).get(prefix)
    if info is None:
        return None
    if isinstance(info, dict):
        return info.get("name")
    return str(info)


def get_type_description(registry: dict, layer: str, prefix: str) -> str | None:
    """Get type description from a registry (enriched format only)."""
    info = registry.get(layer, {}).get(prefix)
    if isinstance(info, dict):
        return info.get("description")
    return None


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
            mismatches.append(
                {
                    "code": fact.code,
                    "current_type": fact.type,
                    "canonical_type": canonical,
                    "layer": fact.layer.value,
                }
            )
    return mismatches
