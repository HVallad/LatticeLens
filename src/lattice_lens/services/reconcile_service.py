"""Reconciliation engine — bidirectional fact-to-code verification."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

from lattice_lens.services.code_scanner import (
    ARCHITECTURAL_PATTERNS,
    scan_for_architectural_patterns,
    scan_for_fact_references,
)
from lattice_lens.store.protocol import LatticeStore


RECONCILIATION_SYSTEM_PROMPT = """You are a governance reconciliation engine for LatticeLens.

You analyze relationships between governance facts (documented architectural decisions, \
rules, and policies) and source code to assess whether governance is accurately reflected \
in the implementation.

For each finding below, you will see:
- The finding category assigned by rule-based matching (confirmed, orphaned, untracked, stale, violated)
- The governance fact text (if applicable)
- Code evidence (file path, line number, code snippet)

Your job:
1. VALIDATE confirmed findings: Does the code genuinely implement/reference this fact, \
or is the regex match a false positive?
2. RESCUE orphaned findings: Is this fact semantically implemented in code even without \
an explicit code reference?
3. DETECT violations: Does any code evidence contradict or violate a governance fact?
4. ASSESS staleness: Has the code evolved beyond what the fact describes?
5. EVALUATE untracked patterns: Are these genuinely undocumented architectural decisions?

Respond ONLY with a valid JSON array. Each object must have:
- original_category: string (the category from rule-based analysis)
- revised_category: string ("confirmed", "stale", "violated", "untracked", "orphaned")
- code: string or null (fact code if applicable)
- confidence: float (0.0-1.0, your confidence in the revised category)
- reasoning: string (1-2 sentence explanation of your assessment)
- file: string or null
- line: integer or null

Do not include any preamble, explanation, or markdown formatting. Only valid JSON."""


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
    llm_reasoning: str | None = None  # LLM's assessment explanation


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


def render_reconciliation_prompt(
    report: ReconciliationReport,
    active_facts: list,
) -> str:
    """Render reconciliation findings into a structured prompt for agent integration.

    Generates a complete prompt containing the system instructions, active fact
    definitions, and rule-based findings that a developer can feed to an AI agent
    (e.g., Claude Code) for semantic analysis.

    Args:
        report: Rule-based reconciliation report.
        active_facts: Active facts from the lattice store.

    Returns:
        Structured prompt text suitable for agent injection.
    """
    sections: list[str] = []

    # Section 1: System instructions
    sections.append(RECONCILIATION_SYSTEM_PROMPT)

    # Section 2: Active facts
    sections.append("\n---\n\n## Active Governance Facts\n")
    if active_facts:
        for fact in active_facts:
            tags_str = ", ".join(fact.tags) if fact.tags else "none"
            refs_str = ", ".join(fact.refs) if fact.refs else "none"
            sections.append(
                f"### [{fact.code}] {fact.type} ({fact.layer.value})\n"
                f"Tags: {tags_str}\n"
                f"Refs: {refs_str}\n"
                f"Confidence: {fact.confidence.value}\n\n"
                f"{fact.fact}\n"
            )
    else:
        sections.append("No active facts in the lattice.\n")

    # Section 3: Findings by category
    sections.append("\n---\n\n## Rule-Based Findings\n")

    categories = [
        ("Confirmed", report.confirmed),
        ("Stale", report.stale),
        ("Violated", report.violated),
        ("Untracked", report.untracked),
        ("Orphaned", report.orphaned),
    ]

    for label, findings in categories:
        if not findings:
            continue
        sections.append(f"\n### {label} ({len(findings)})\n")
        for f in findings:
            loc = f"{f.file}:{f.line}" if f.file else "no file"
            sections.append(
                f"- **{f.code or 'N/A'}** ({f.category}, confidence={f.confidence:.2f})\n"
                f"  Location: {loc}\n"
                f"  Description: {f.description}\n"
                f"  Evidence: {f.evidence[:300]}\n"
            )

    # Section 4: Usage hint
    sections.append(
        "\n---\n\n"
        "Feed this prompt to your AI agent (e.g., Claude Code) for semantic analysis.\n"
        "The agent should analyze each finding against the governance facts and return\n"
        "its assessment as a JSON array following the schema above.\n"
    )

    return "\n".join(sections)


def _build_llm_user_message(
    report: ReconciliationReport,
    active_facts: list,
) -> str:
    """Build the user message for the LLM API call.

    Contains fact definitions and findings without the system prompt
    (which is passed separately via the system parameter).
    """
    sections: list[str] = []

    # Active facts
    sections.append("## Active Governance Facts\n")
    for fact in active_facts:
        tags_str = ", ".join(fact.tags) if fact.tags else "none"
        refs_str = ", ".join(fact.refs) if fact.refs else "none"
        sections.append(
            f"### [{fact.code}] {fact.type} ({fact.layer.value})\n"
            f"Tags: {tags_str} | Refs: {refs_str} | "
            f"Confidence: {fact.confidence.value}\n\n"
            f"{fact.fact}\n"
        )

    # Findings
    sections.append("\n## Rule-Based Findings to Analyze\n")

    all_findings: list[Finding] = (
        report.confirmed
        + report.stale
        + report.violated
        + report.untracked
        + report.orphaned
    )

    if not all_findings:
        sections.append("No findings to analyze.\n")
    else:
        for f in all_findings:
            loc = f"{f.file}:{f.line}" if f.file else "no file"
            sections.append(
                f"- category={f.category}, code={f.code or 'N/A'}, "
                f"confidence={f.confidence:.2f}\n"
                f"  Location: {loc}\n"
                f"  Description: {f.description}\n"
                f"  Evidence: {f.evidence[:300]}\n"
            )

    return "\n".join(sections)


_VALID_CATEGORIES = {"confirmed", "stale", "violated", "untracked", "orphaned"}


def llm_reconcile(
    report: ReconciliationReport,
    active_facts: list,
    api_key: str,
    model: str = "claude-sonnet-4-20250514",
) -> ReconciliationReport:
    """Enrich a rule-based reconciliation report with LLM semantic analysis.

    Sends findings and fact definitions to the Anthropic API for deeper
    analysis. The LLM can reclassify findings, adjust confidence scores,
    and provide reasoning.

    On invalid JSON from the LLM, falls back to the original report with
    a warning on stderr.

    Args:
        report: Rule-based reconciliation report.
        active_facts: Active facts from the lattice store.
        api_key: Anthropic API key.
        model: Model to use for analysis.

    Returns:
        Enriched ReconciliationReport with LLM assessments.
    """
    from anthropic import Anthropic

    user_msg = _build_llm_user_message(report, active_facts)

    client = Anthropic(api_key=api_key)
    response = client.messages.create(
        model=model,
        max_tokens=4096,
        system=RECONCILIATION_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
    )

    response_text = response.content[0].text.strip()
    # Strip markdown code fences if present
    if response_text.startswith("```"):
        response_text = response_text.split("\n", 1)[1]
    if response_text.endswith("```"):
        response_text = response_text.rsplit("\n", 1)[0]

    try:
        llm_findings = json.loads(response_text)
    except json.JSONDecodeError as e:
        print(
            f"Warning: LLM returned invalid JSON, falling back to rule-based "
            f"report: {e}",
            file=sys.stderr,
        )
        return report

    if not isinstance(llm_findings, list):
        print(
            "Warning: LLM response is not a JSON array, falling back to "
            "rule-based report.",
            file=sys.stderr,
        )
        return report

    # Build enriched report from LLM results
    enriched = ReconciliationReport()

    for item in llm_findings:
        try:
            revised_cat = item.get("revised_category", item.get("original_category", "orphaned"))
            if revised_cat not in _VALID_CATEGORIES:
                continue

            finding = Finding(
                category=revised_cat,
                code=item.get("code"),
                description=item.get("reasoning", "LLM assessment"),
                file=item.get("file"),
                line=item.get("line"),
                confidence=float(item.get("confidence", 0.5)),
                evidence="",
                llm_reasoning=item.get("reasoning"),
            )

            # Preserve original evidence from the rule-based finding
            if finding.code:
                original = _find_original(report, finding.code)
                if original:
                    finding.evidence = original.evidence

            category_list = getattr(enriched, revised_cat, None)
            if category_list is not None:
                category_list.append(finding)

        except (TypeError, ValueError, KeyError) as e:
            print(
                f"Warning: skipping invalid LLM finding: {e}",
                file=sys.stderr,
            )

    return enriched


def _find_original(report: ReconciliationReport, code: str) -> Finding | None:
    """Find the original rule-based finding by fact code."""
    for category_list in [
        report.confirmed, report.stale, report.violated,
        report.untracked, report.orphaned,
    ]:
        for f in category_list:
            if f.code == code:
                return f
    return None


def reconcile(
    store: LatticeStore,
    codebase_root: Path,
    *,
    include_patterns: list[str] | None = None,
    exclude_patterns: list[str] | None = None,
    use_llm: bool = False,
    api_key: str | None = None,
    model: str = "claude-sonnet-4-20250514",
) -> ReconciliationReport:
    """Run bidirectional reconciliation.

    Facts-to-Code: For each active fact, check if the codebase references it.
    Code-to-Facts: Scan for architectural patterns with no corresponding fact.

    When use_llm is True, rule-based findings are enriched by sending them to
    the Anthropic API for semantic analysis.

    Args:
        store: LatticeStore instance.
        codebase_root: Directory to scan.
        include_patterns: Glob patterns to include (default: **/*.py).
        exclude_patterns: Glob patterns to exclude.
        use_llm: Enable LLM-assisted analysis via Anthropic API.
        api_key: Anthropic API key (required when use_llm=True).
        model: Model to use for LLM analysis.
    """
    if use_llm and not api_key:
        raise ValueError(
            "API key required for LLM-assisted reconciliation. "
            "Set LATTICE_ANTHROPIC_API_KEY or use --api-key."
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

    # ── LLM enrichment (Phase 2) ──
    if use_llm:
        report = llm_reconcile(report, active_facts, api_key, model)

    return report
