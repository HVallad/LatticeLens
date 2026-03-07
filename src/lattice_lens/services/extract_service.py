"""LLM-powered fact extraction from documents."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from lattice_lens.models import Fact, FactStatus

EXTRACTION_SYSTEM_PROMPT = """You are a knowledge extraction engine for LatticeLens.

Your job is to decompose a document into atomic facts. Each fact must be:
- Self-contained: readable without the original document
- One decision, one finding, or one rule per fact
- Tagged with at least 2 relevant tags from this vocabulary (or create new lowercase hyphenated tags):
  Domain: model-selection, inference, training, data-pipeline, user-facing, internal-tool, api, authentication, authorization, storage, caching, scaling, cost, latency, throughput, availability
  Concern: security, privacy, bias, fairness, transparency, accountability, safety, compliance, regulatory, legal, ethical, accessibility
  Lifecycle: design-time, build-time, deploy-time, runtime, monitoring, incident-response, rollback, migration, deprecation, end-of-life
  Stakeholder: end-user, developer, ops-team, compliance-team, executive, auditor, regulator, data-subject
  Risk: high-severity, medium-severity, low-severity, mitigated, unmitigated, accepted-risk

Each fact must be classified into a layer:
- WHY: Architecture decisions (ADR), product requirements (PRD), ethical findings (ETH), design proposals (DES)
- GUARDRAILS: Model cards (MC), acceptable use policies (AUP), risk assessments (RISK), data governance (DG), compliance (COMP)
- HOW: System prompt rules (SP), API specifications (API), runbook procedures (RUN), MLOps rules (ML), monitoring rules (MON)

Respond ONLY with a valid JSON array. Each object has these fields:
- code: string in format "{PREFIX}-{SEQ}" (e.g., "ADR-01", "RISK-03")
- layer: "WHY", "GUARDRAILS", or "HOW"
- type: The document type name (e.g., "Architecture Decision Record")
- fact: The atomic fact as a complete, self-contained sentence or short paragraph
- tags: Array of at least 2 lowercase hyphenated tags
- confidence: "Confirmed" if explicitly stated in the document, "Provisional" if inferred, "Assumed" if your interpretation
- refs: Array of codes this fact relates to (use codes you've assigned to other facts in this extraction)
- owner: Best guess at the responsible team based on content (e.g., "architecture-team", "security-team", "product-team")

Do not include any preamble, explanation, or markdown formatting. Only valid JSON."""


def extract_facts_from_document(
    document_path: Path,
    api_key: str,
    model: str = "claude-sonnet-4-20250514",
    existing_codes: list[str] | None = None,
) -> list[Fact]:
    """Send document content to Claude, receive extracted facts.

    Args:
        document_path: Path to the document (.md, .txt, .docx via pandoc)
        api_key: Anthropic API key
        model: Model to use for extraction
        existing_codes: Codes already in the lattice (to avoid collisions)

    Returns:
        List of Fact objects with status=Draft
    """
    from anthropic import Anthropic

    content = _read_document(document_path)
    if not content.strip():
        raise ValueError(f"Document is empty: {document_path}")

    user_msg = f"Extract atomic facts from this document:\n\n{content}"
    if existing_codes:
        user_msg += (
            f"\n\nExisting codes in the lattice (avoid collisions and reference "
            f"these where appropriate): {', '.join(existing_codes)}"
        )

    client = Anthropic(api_key=api_key)
    response = client.messages.create(
        model=model,
        max_tokens=4096,
        system=EXTRACTION_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
    )

    response_text = response.content[0].text.strip()
    # Strip markdown code fences if present
    if response_text.startswith("```"):
        response_text = response_text.split("\n", 1)[1]
    if response_text.endswith("```"):
        response_text = response_text.rsplit("\n", 1)[0]

    raw_facts = json.loads(response_text)

    facts = []
    for raw in raw_facts:
        try:
            fact = Fact(
                code=raw["code"],
                layer=raw["layer"],
                type=raw["type"],
                fact=raw["fact"],
                tags=raw.get("tags", []),
                status=FactStatus.DRAFT,
                confidence=raw.get("confidence", "Provisional"),
                refs=raw.get("refs", []),
                owner=raw.get("owner", "extracted"),
                review_by=None,
            )
            facts.append(fact)
        except Exception as e:
            print(
                f"Warning: skipping invalid extracted fact {raw.get('code', '?')}: {e}",
                file=sys.stderr,
            )

    return facts


def _read_document(path: Path) -> str:
    """Read document content. Supports .md, .txt. For .docx, shell out to pandoc."""
    suffix = path.suffix.lower()
    if suffix in (".md", ".txt", ".yaml", ".yml", ".json"):
        return path.read_text(encoding="utf-8")
    elif suffix == ".docx":
        import subprocess

        try:
            result = subprocess.run(
                ["pandoc", str(path), "-t", "plain"],
                capture_output=True,
                text=True,
            )
        except FileNotFoundError:
            raise RuntimeError(
                "pandoc is required for .docx files. Install: https://pandoc.org/installing.html"
            )
        if result.returncode != 0:
            raise RuntimeError(f"pandoc failed: {result.stderr}")
        return result.stdout
    else:
        raise ValueError(f"Unsupported document type: {suffix}. Supported: .md, .txt, .docx")
