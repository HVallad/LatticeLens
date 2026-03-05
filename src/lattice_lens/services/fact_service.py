"""Business logic for fact lifecycle management."""

from __future__ import annotations

import re
from datetime import datetime

from lattice_lens.config import LAYER_PREFIXES
from lattice_lens.models import Fact, FactConfidence, FactStatus
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


# Valid lifecycle transitions: current_status -> next_status
PROMOTION_TRANSITIONS: dict[FactStatus, FactStatus] = {
    FactStatus.DRAFT: FactStatus.UNDER_REVIEW,
    FactStatus.UNDER_REVIEW: FactStatus.ACTIVE,
}


def promote_fact(store: YamlFileStore, code: str, reason: str) -> Fact:
    """Promote a fact one step through the lifecycle.

    Draft -> Under Review -> Active.
    Raises ValueError if the fact cannot be promoted.
    """
    fact = store.get(code)
    if fact is None:
        raise FileNotFoundError(f"Fact {code} not found")

    next_status = PROMOTION_TRANSITIONS.get(fact.status)
    if next_status is None:
        raise ValueError(
            f"Cannot promote {code}: status '{fact.status.value}' is not promotable. "
            f"Only Draft and Under Review facts can be promoted."
        )

    changes: dict = {"status": next_status.value}

    # When promoting to Active, set confidence to Confirmed
    if next_status == FactStatus.ACTIVE:
        changes["confidence"] = FactConfidence.CONFIRMED.value

    # When promoting to Under Review, set confidence to Provisional
    if next_status == FactStatus.UNDER_REVIEW:
        changes["confidence"] = FactConfidence.PROVISIONAL.value

    return store.update(code, changes, f"Promoted to {next_status.value}: {reason}")
