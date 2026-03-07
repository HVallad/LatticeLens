"""Tag registry — centralized tag vocabulary with usage counts and categories."""

from __future__ import annotations

from pathlib import Path

from ruamel.yaml import YAML

from lattice_lens.store.protocol import LatticeStore

yaml_rw = YAML()
yaml_rw.default_flow_style = False

TAGS_FILE = "tags.yaml"

# Controlled vocabulary per DG-07
VOCABULARY: dict[str, list[str]] = {
    "domain": [
        "model-selection",
        "inference",
        "latency",
        "scaling",
        "architecture",
        "storage",
        "serialization",
        "api",
        "cli",
        "formatting",
        "discovery",
        "configuration",
        "context-assembly",
        "design",
        "extraction",
        "git-native",
        "impact-analysis",
        "import-export",
        "index",
        "project-scoping",
        "pydantic",
        "reconciliation",
        "sqlite",
    ],
    "concern": [
        "security",
        "privacy",
        "bias",
        "compliance",
        "data-integrity",
        "validation",
        "audit-trail",
        "governance",
        "normalization",
        "controlled-vocabulary",
        "developer-experience",
        "extensibility",
        "policy",
        "tag-vocabulary",
        "type-registry",
    ],
    "lifecycle": [
        "design-time",
        "runtime",
        "incident-response",
        "status-lifecycle",
        "versioning",
        "lifecycle",
        "migration",
    ],
    "stakeholder": [
        "end-user",
        "developer",
        "auditor",
        "ops-team",
    ],
    "risk": [
        "high-severity",
        "mitigated",
        "accepted-risk",
        "risk",
        "staleness",
    ],
}

# Build reverse lookup: tag -> category
_TAG_TO_CATEGORY: dict[str, str] = {}
for _category, _tags in VOCABULARY.items():
    for _tag in _tags:
        _TAG_TO_CATEGORY[_tag] = _category


def categorize_tag(tag: str) -> str:
    """Return the vocabulary category for a tag, or 'free' if unrecognized."""
    return _TAG_TO_CATEGORY.get(tag, "free")


def build_tag_registry(store: LatticeStore) -> list[dict]:
    """Scan all facts and build a tag registry with usage counts and categories.

    Returns a list of dicts: [{tag, count, category}, ...] sorted by count desc.
    """
    tag_counts: dict[str, int] = {}
    # Use list_facts with all statuses to scan everything
    all_statuses = ["Active", "Draft", "Under Review", "Deprecated", "Superseded"]
    facts = store.list_facts(status=all_statuses)
    for fact in facts:
        for tag in fact.tags:
            tag_counts[tag] = tag_counts.get(tag, 0) + 1

    registry = []
    for tag, count in sorted(tag_counts.items(), key=lambda x: (-x[1], x[0])):
        registry.append(
            {
                "tag": tag,
                "count": count,
                "category": categorize_tag(tag),
            }
        )
    return registry


def write_tag_registry(lattice_root: Path, registry: list[dict]) -> Path:
    """Write the tag registry to .lattice/tags.yaml."""
    path = lattice_root / TAGS_FILE
    data = {"tags": registry}
    with open(path, "w") as f:
        yaml_rw.dump(data, f)
    return path


def read_tag_registry(lattice_root: Path) -> list[dict] | None:
    """Read the existing tag registry from .lattice/tags.yaml."""
    path = lattice_root / TAGS_FILE
    if not path.exists():
        return None
    with open(path) as f:
        data = yaml_rw.load(f)
    if data is None:
        return None
    return data.get("tags", [])
