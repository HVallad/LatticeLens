"""Business logic for fact lifecycle management."""

from __future__ import annotations

import re
from datetime import datetime

from lattice_lens.config import LAYER_PREFIXES
from lattice_lens.models import Fact, FactStatus
from lattice_lens.store.yaml_store import YamlFileStore


# Reverse map: prefix -> layer
PREFIX_TO_LAYER: dict[str, str] = {}
for layer, prefixes in LAYER_PREFIXES.items():
    for prefix in prefixes:
        PREFIX_TO_LAYER[prefix] = layer


def next_code(store: YamlFileStore, prefix: str) -> str:
    """Auto-assign the next available code for a given prefix (e.g., ADR -> ADR-04)."""
    existing = store.all_codes()
    max_num = 0
    pattern = re.compile(rf"^{re.escape(prefix)}-(\d+)$")
    for code in existing:
        m = pattern.match(code)
        if m:
            max_num = max(max_num, int(m.group(1)))
    return f"{prefix}-{max_num + 1:02d}"


def infer_layer(prefix: str) -> str | None:
    """Infer the layer from a code prefix."""
    return PREFIX_TO_LAYER.get(prefix)


def check_refs(store: YamlFileStore, refs: list[str]) -> list[str]:
    """Return list of warning messages for refs pointing to non-existent codes."""
    warnings = []
    for ref in refs:
        if not store.exists(ref):
            warnings.append(f"Reference target '{ref}' does not exist (soft warning)")
    return warnings


def create_fact(store: YamlFileStore, fact: Fact) -> tuple[Fact, list[str]]:
    """Create a fact, returning (fact, warnings). Raises on hard errors."""
    warnings = check_refs(store, fact.refs)
    created = store.create(fact)
    return created, warnings


def update_fact(
    store: YamlFileStore, code: str, changes: dict, reason: str
) -> tuple[Fact, list[str]]:
    """Update a fact, returning (fact, warnings). Raises on hard errors."""
    # Don't allow code changes
    if "code" in changes:
        raise ValueError("Code is immutable and cannot be changed")

    # Check refs if being updated
    warnings = []
    if "refs" in changes:
        warnings = check_refs(store, changes["refs"])

    updated = store.update(code, changes, reason)
    return updated, warnings


def deprecate_fact(store: YamlFileStore, code: str, reason: str) -> Fact:
    """Deprecate a fact. No hard deletes allowed."""
    return store.deprecate(code, reason)


def is_stale(fact: Fact) -> bool:
    """Check if a fact is past its review_by date."""
    if fact.review_by is None:
        return False
    return fact.review_by < datetime.now().date()
