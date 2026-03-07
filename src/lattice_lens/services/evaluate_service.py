"""Governance evaluation service for Claude Code hook integration.

Loads Active GUARDRAILS-layer facts and summarises available WHY/HOW
knowledge so that the injected context both *enforces* governance rules
and *encourages* the agent to consult relevant architectural decisions,
design patterns, and operational runbooks before starting work.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from lattice_lens.config import ROLES_DIR, find_lattice_root, load_config
from lattice_lens.models import Fact, FactConfidence
from lattice_lens.services.context_service import estimate_tokens
from lattice_lens.services.graph_service import load_role_templates
from lattice_lens.services.project_service import (
    fact_matches_project,
    is_scoping_enabled,
    read_project_registry,
)
from lattice_lens.store.yaml_store import YamlFileStore


# ---------------------------------------------------------------------------
# Hook input parsing
# ---------------------------------------------------------------------------

@dataclass
class HookInput:
    """Parsed Claude Code hook stdin payload."""

    session_id: str = ""
    cwd: str = ""
    hook_event_name: str = ""
    prompt: str = ""


def parse_hook_input(stdin_data: str) -> HookInput | None:
    """Parse Claude Code UserPromptSubmit hook stdin JSON.

    Returns ``None`` when *stdin_data* is empty, whitespace-only, or not
    valid JSON — indicating the command is being run standalone rather
    than as a hook.
    """
    if not stdin_data or not stdin_data.strip():
        return None
    try:
        data = json.loads(stdin_data)
    except (json.JSONDecodeError, TypeError):
        return None
    return HookInput(
        session_id=data.get("session_id", ""),
        cwd=data.get("cwd", ""),
        hook_event_name=data.get("hook_event_name", ""),
        prompt=data.get("prompt", ""),
    )


# ---------------------------------------------------------------------------
# Evaluation result
# ---------------------------------------------------------------------------

@dataclass
class EvaluationResult:
    """Result of a governance evaluation for Claude Code hook injection."""

    lattice_found: bool = False
    guardrails: list[Fact] = field(default_factory=list)
    knowledge_summary: dict[str, dict[str, int]] = field(default_factory=dict)
    available_roles: list[str] = field(default_factory=list)
    total_tokens: int = 0
    lattice_root: str = ""
    active_project: str = ""

    @property
    def has_governance(self) -> bool:
        """True when there is a lattice with at least one guardrail."""
        return self.lattice_found and len(self.guardrails) > 0

    # -- rendering ----------------------------------------------------------

    def render_briefing(self) -> str:
        """Render the full governance briefing as plain text.

        This text is emitted on *stdout* by the ``lattice evaluate``
        command.  When the command is invoked as a Claude Code
        ``UserPromptSubmit`` hook, Claude Code injects the text as
        additional context that the model sees before processing the
        user's prompt.

        Returns an empty string when there is nothing to inject (no
        lattice found, or no active guardrails).
        """
        if not self.lattice_found:
            return ""

        # Even if there are no guardrails, we still want to show the
        # knowledge discovery section if the lattice exists.
        has_knowledge = any(self.knowledge_summary.values())
        if not self.has_governance and not has_knowledge:
            return ""

        lines: list[str] = []
        lines.append("# LatticeLens Governance Briefing")
        if self.active_project:
            lines.append(f"**Active project: {self.active_project}**")
        lines.append("")

        # ---- Section 1: Mandatory governance rules ----
        if self.guardrails:
            lines.append("## Mandatory Rules")
            lines.append(
                "You MUST follow these governance rules for this project. "
                "If the user's request would violate any of these rules, "
                "you MUST raise the conflict before proceeding — cite the "
                "specific rule code (e.g. AUP-01) and explain why the "
                "proposed action conflicts with it. Ask the user how they "
                "would like to proceed rather than silently violating a rule."
            )
            lines.append("")

            for fact in self.guardrails:
                lines.append(
                    f"### [{fact.code}] {fact.type} ({fact.confidence.value})"
                )
                if fact.refs:
                    lines.append(f"Refs: {', '.join(fact.refs)}")
                lines.append("")
                lines.append(fact.fact)
                lines.append("")

        # ---- Section 2: Knowledge discovery ----
        if has_knowledge or self.available_roles:
            lines.append("## Project Knowledge Available")
            lines.append(
                "This project has a knowledge lattice you should consult "
                "before development:"
            )
            lines.append("")

            layer_labels = {
                "WHY": "architectural decisions & requirements",
                "HOW": "implementation patterns & operations",
            }
            for layer in ("WHY", "HOW"):
                type_counts = self.knowledge_summary.get(layer, {})
                if not type_counts:
                    continue
                lines.append(
                    f"**{layer} layer** ({layer_labels.get(layer, layer)}):"
                )
                for fact_type, count in sorted(type_counts.items()):
                    lines.append(f"- {count} {fact_type}{'s' if count != 1 else ''}")
                lines.append("")

            if self.available_roles:
                lines.append("### Before starting work, load relevant context:")
                role_hints = {
                    "planning": "planning/scoping",
                    "architecture": "design decisions",
                    "implementation": "coding tasks",
                    "qa": "testing/QA",
                    "deploy": "deployment",
                }
                for role in sorted(self.available_roles):
                    hint = role_hints.get(role, role)
                    lines.append(
                        f"- For {hint}: `lattice context {role} --json`"
                    )
                lines.append(
                    "- Look up a specific fact: `lattice fact get <CODE> --json`"
                )
                lines.append("")
                lines.append(
                    "Use the lattice context that best matches your current task."
                )
                lines.append("")

        # ---- Footer ----
        why_count = sum(self.knowledge_summary.get("WHY", {}).values())
        how_count = sum(self.knowledge_summary.get("HOW", {}).values())
        lines.append("---")
        lines.append(
            f"Source: .lattice/ ({len(self.guardrails)} guardrails, "
            f"{why_count} WHY facts, {how_count} HOW facts, "
            f"{len(self.available_roles)} roles)"
        )
        return "\n".join(lines)

    def to_dict(self) -> dict:
        """Serialise to dict for ``--json`` output."""
        return {
            "lattice_found": self.lattice_found,
            "guardrails_count": len(self.guardrails),
            "total_tokens": self.total_tokens,
            "lattice_root": self.lattice_root,
            "active_project": self.active_project,
            "guardrails": [
                {
                    "code": f.code,
                    "version": f.version,
                    "type": f.type,
                    "confidence": f.confidence.value,
                    "tags": f.tags,
                    "refs": f.refs,
                    "fact": f.fact,
                }
                for f in self.guardrails
            ],
            "knowledge_summary": self.knowledge_summary,
            "available_roles": self.available_roles,
        }


# ---------------------------------------------------------------------------
# Core evaluation function
# ---------------------------------------------------------------------------

def evaluate_governance(
    start_path: Path | None = None,
) -> EvaluationResult:
    """Load Active GUARDRAILS facts and summarise WHY/HOW knowledge.

    This is the core evaluation engine.  It:

    1. Finds the ``.lattice/`` root (silent if not found).
    2. Loads all **Active** facts from the **GUARDRAILS** layer.
    3. Sorts guardrails: Confirmed confidence first, then by code.
    4. Builds a knowledge summary counting Active WHY/HOW facts by type.
    5. Lists available role templates.

    Parameters
    ----------
    start_path:
        Directory to search upward from.  When called from a Claude Code
        hook this is the ``cwd`` field from the hook's stdin JSON.  When
        ``None`` the current working directory is used.
    """
    result = EvaluationResult()

    lattice_root = find_lattice_root(start_path)
    if lattice_root is None:
        return result  # silent no-op

    result.lattice_found = True
    result.lattice_root = str(lattice_root)

    store = YamlFileStore(lattice_root)

    # ---- Detect active project ----
    config = load_config(lattice_root)
    active_project = config.get("default_project", "")

    registry: dict | None = None
    if active_project and is_scoping_enabled(lattice_root):
        registry = read_project_registry(lattice_root)
        result.active_project = active_project

    # ---- Guardrails ----
    guardrails = store.list_facts(layer="GUARDRAILS", status=["Active"])

    # Filter by project if scoping is active
    if active_project and registry is not None:
        guardrails = [
            f for f in guardrails
            if fact_matches_project(f.projects, active_project, registry)
        ]

    def _sort_key(f: Fact) -> tuple:
        rank = 0 if f.confidence == FactConfidence.CONFIRMED else 1
        return (rank, f.code)

    guardrails.sort(key=_sort_key)
    result.guardrails = guardrails

    # Token estimate for the governance portion
    for fact in guardrails:
        text = (
            f"[{fact.code}] {fact.type}\n"
            f"Confidence: {fact.confidence.value}\n"
            f"{fact.fact}"
        )
        result.total_tokens += estimate_tokens(text)

    # ---- Knowledge summary (WHY + HOW) ----
    for layer in ("WHY", "HOW"):
        facts = store.list_facts(layer=layer, status=["Active"])
        # Filter by project if scoping is active
        if active_project and registry is not None:
            facts = [
                f for f in facts
                if fact_matches_project(f.projects, active_project, registry)
            ]
        if not facts:
            continue
        type_counts: dict[str, int] = {}
        for f in facts:
            type_counts[f.type] = type_counts.get(f.type, 0) + 1
        result.knowledge_summary[layer] = type_counts

    # ---- Available roles ----
    roles_dir = lattice_root / ROLES_DIR
    if roles_dir.is_dir():
        templates = load_role_templates(roles_dir)
        result.available_roles = sorted(templates.keys())

    return result
