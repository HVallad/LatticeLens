"""Reconciliation engine — bidirectional fact-to-code verification."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from lattice_lens.services.code_scanner import (
    ARCHITECTURAL_PATTERNS,
    scan_for_architectural_patterns,
    scan_for_fact_references,
)
from lattice_lens.store.protocol import LatticeStore


@dataclass
class Finding:
    """A single reconciliation finding."""

    category: str  # "confirmed", "stale", "violated", "untracked", "orphaned"
    code: str | None  # Fact code (None for untracked findings)
    description: str  # Human-readable explanation
    file: str | None  # Source file path (None for orphaned)
    line: int | None  # Line number in source
    confidence: float  # 0.0-1.0 confidence in the finding
    evidence: str  # Code snippet or text supporting the finding


@dataclass
class ReconciliationReport:
    """Full reconciliation report."""

    confirmed: list[Finding] = field(default_factory=list)
    stale: list[Finding] = field(default_factory=list)
    violated: list[Finding] = field(default_factory=list)
    untracked: list[Finding] = field(default_factory=list)
    orphaned: list[Finding] = field(default_factory=list)

    @property
    def total_facts_checked(self) -> int:
        return (
            len(self.confirmed)
            + len(self.stale)
            + len(self.violated)
            + len(self.orphaned)
        )

    @property
    def coverage_pct(self) -> float:
        total = self.total_facts_checked
        if total == 0:
            return 0.0
        return len(self.confirmed) / total * 100

    def summary(self) -> dict:
        return {
            "confirmed": len(self.confirmed),
            "stale": len(self.stale),
            "violated": len(self.violated),
            "untracked": len(self.untracked),
            "orphaned": len(self.orphaned),
            "coverage_pct": round(self.coverage_pct, 1),
        }


# Mapping from architectural pattern categories to fact types/tags that cover them
_PATTERN_COVERAGE: dict[str, dict[str, list[str]]] = {
    "framework": {"types": ["Architecture Decision Record"], "tags": ["architecture", "cli"]},
    "validation": {"types": ["Architecture Decision Record", "Model Card Entry"], "tags": ["validation", "pydantic"]},
    "storage": {"types": ["Architecture Decision Record", "Design Proposal Decision"], "tags": ["storage", "sqlite"]},
    "security": {"types": ["Risk Register Entry", "Acceptable Use Policy Rule"], "tags": ["security"]},
    "error_handling": {"types": ["Design Proposal Decision", "Runbook Procedure"], "tags": ["error-handling"]},
}


def _is_pattern_covered(
    category: str,
    active_facts: list,
) -> bool:
    """Check if an architectural pattern category is covered by existing facts."""
    coverage = _PATTERN_COVERAGE.get(category, {})
    covered_types = set(coverage.get("types", []))
    covered_tags = set(coverage.get("tags", []))

    for fact in active_facts:
        if fact.type in covered_types:
            return True
        if set(fact.tags) & covered_tags:
            return True
    return False


def reconcile(
    store: LatticeStore,
    codebase_root: Path,
    *,
    include_patterns: list[str] | None = None,
    exclude_patterns: list[str] | None = None,
    use_llm: bool = False,
) -> ReconciliationReport:
    """Run bidirectional reconciliation.

    Facts-to-Code: For each active fact, check if the codebase references it.
    Code-to-Facts: Scan for architectural patterns with no corresponding fact.

    Args:
        store: LatticeStore instance.
        codebase_root: Directory to scan.
        include_patterns: Glob patterns to include (default: **/*.py).
        exclude_patterns: Glob patterns to exclude.
        use_llm: Enable LLM-assisted analysis (not yet implemented).
    """
    if use_llm:
        raise NotImplementedError(
            "LLM-assisted reconciliation is planned but not yet implemented. "
            "Remove --llm flag to use rule-based matching."
        )

    report = ReconciliationReport()

    # Load active facts
    active_facts = store.list_facts(status=["Active"])
    known_codes = store.all_codes()

    # ── Facts-to-Code direction ──
    code_refs = scan_for_fact_references(
        codebase_root, known_codes, include_patterns, exclude_patterns
    )

    # Group references by fact code
    refs_by_code: dict[str, list] = {}
    for ref in code_refs:
        refs_by_code.setdefault(ref.code, []).append(ref)

    # Classify each active fact
    for fact in active_facts:
        if fact.code in refs_by_code:
            refs = refs_by_code[fact.code]
            ref = refs[0]  # Use first reference as primary evidence
            report.confirmed.append(
                Finding(
                    category="confirmed",
                    code=fact.code,
                    description=f"Found {len(refs)} code reference(s)",
                    file=str(ref.file),
                    line=ref.line,
                    confidence=min(1.0, 0.5 + 0.1 * len(refs)),
                    evidence=ref.context,
                )
            )
        else:
            report.orphaned.append(
                Finding(
                    category="orphaned",
                    code=fact.code,
                    description=f"No code evidence found for {fact.type}",
                    file=None,
                    line=None,
                    confidence=0.6,
                    evidence=fact.fact[:200],
                )
            )

    # ── Code-to-Facts direction ──
    arch_patterns = scan_for_architectural_patterns(
        codebase_root, include_patterns, exclude_patterns
    )

    # Deduplicate patterns by category (report once per category, not per file)
    seen_categories: set[str] = set()
    for pattern in arch_patterns:
        if pattern.category in seen_categories:
            continue
        if not _is_pattern_covered(pattern.category, active_facts):
            report.untracked.append(
                Finding(
                    category="untracked",
                    code=None,
                    description=f"{pattern.category.title()}: {pattern.suggests}",
                    file=str(pattern.file),
                    line=pattern.line,
                    confidence=0.7,
                    evidence=pattern.match,
                )
            )
            seen_categories.add(pattern.category)

    return report
