# LatticeLens — Phase 4 Implementation Brief
# LLM Extraction + Import/Export

> **Purpose**: Enable bootstrapping a lattice from existing documents using LLM-powered fact extraction, plus interchange formats for moving facts between lattices.
>
> **Timeline**: Week 4 (~5 days).
>
> **Prerequisites**: Phase 3 complete. Context assembly working.

---

## 1. What This Phase Delivers

After Phase 4, a developer can:
- Point `lattice extract` at an existing design doc, PRD, or architecture document and get atomic facts automatically generated
- Preview extracted facts before committing them
- Export the entire fact base as JSON or YAML for backup, sharing, or migration
- Import facts from another lattice or external source with configurable merge strategies

---

## 2. New Files

```
src/lattice_lens/
├── services/
│   └── extract_service.py       # NEW: LLM-powered fact extraction
├── cli/
│   ├── extract_command.py       # NEW: lattice extract
│   └── exchange_commands.py     # NEW: lattice export / lattice import
tests/
├── test_extract_service.py      # NEW
├── test_exchange.py             # NEW
└── fixtures/
    └── sample_doc.md            # NEW: test document for extraction
```

Add `anthropic>=0.25.0` to `[project.optional-dependencies.extract]`.

---

## 3. LLM Extraction Service

### 3.1 Extraction Prompt

```python
# src/lattice_lens/services/extract_service.py
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
```

### 3.2 Extraction Logic

```python
from __future__ import annotations
from pathlib import Path
from lattice_lens.models import Fact, FactStatus
import json


def extract_facts_from_document(
    document_path: Path,
    api_key: str,
    model: str = "claude-sonnet-4-20250514",
    existing_codes: list[str] | None = None,
) -> list[Fact]:
    """
    Send document content to Claude, receive extracted facts.

    Args:
        document_path: Path to the document (.md, .txt, .docx via pandoc)
        api_key: Anthropic API key
        model: Model to use for extraction
        existing_codes: Codes already in the lattice (to avoid collisions)

    Returns:
        List of Fact objects with status=Draft
    """
    from anthropic import Anthropic

    # Read document
    content = _read_document(document_path)
    if not content.strip():
        raise ValueError(f"Document is empty: {document_path}")

    # Build user message
    user_msg = f"Extract atomic facts from this document:\n\n{content}"
    if existing_codes:
        user_msg += (
            f"\n\nExisting codes in the lattice (avoid collisions and reference these where appropriate): "
            f"{', '.join(existing_codes)}"
        )

    # Call API
    client = Anthropic(api_key=api_key)
    response = client.messages.create(
        model=model,
        max_tokens=4096,
        system=EXTRACTION_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
    )

    # Parse response
    response_text = response.content[0].text.strip()
    # Strip markdown code fences if present
    if response_text.startswith("```"):
        response_text = response_text.split("\n", 1)[1]
    if response_text.endswith("```"):
        response_text = response_text.rsplit("\n", 1)[0]

    raw_facts = json.loads(response_text)

    # Convert to Fact objects
    facts = []
    for raw in raw_facts:
        try:
            fact = Fact(
                code=raw["code"],
                layer=raw["layer"],
                type=raw["type"],
                fact=raw["fact"],
                tags=raw.get("tags", []),
                status=FactStatus.DRAFT,  # Always Draft until human review
                confidence=raw.get("confidence", "Provisional"),
                refs=raw.get("refs", []),
                owner=raw.get("owner", "extracted"),
                review_by=None,
            )
            facts.append(fact)
        except Exception as e:
            # Log validation error but continue with other facts
            import sys
            print(f"Warning: skipping invalid extracted fact {raw.get('code', '?')}: {e}", file=sys.stderr)

    return facts


def _read_document(path: Path) -> str:
    """Read document content. Supports .md, .txt. For .docx, shell out to pandoc."""
    suffix = path.suffix.lower()
    if suffix in (".md", ".txt", ".yaml", ".yml", ".json"):
        return path.read_text(encoding="utf-8")
    elif suffix == ".docx":
        import subprocess
        result = subprocess.run(
            ["pandoc", str(path), "-t", "plain"],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            raise RuntimeError(f"pandoc failed: {result.stderr}")
        return result.stdout
    else:
        raise ValueError(f"Unsupported document type: {suffix}. Supported: .md, .txt, .docx")
```

---

## 4. Import/Export Service

```python
# src/lattice_lens/services/exchange_service.py
from __future__ import annotations
import json
from pathlib import Path
from ruamel.yaml import YAML
from lattice_lens.models import Fact
from lattice_lens.store.protocol import LatticeStore

yaml = YAML()
yaml.default_flow_style = False


def export_facts(store: LatticeStore, format: str = "json") -> str:
    """Export all facts from the store."""
    facts = store.list_facts(status=None)  # All statuses
    data = [f.model_dump(mode="json") for f in facts]

    if format == "json":
        return json.dumps(data, indent=2, default=str)
    elif format == "yaml":
        from io import StringIO
        buf = StringIO()
        yaml.dump(data, buf)
        return buf.getvalue()
    else:
        raise ValueError(f"Unsupported format: {format}. Use 'json' or 'yaml'.")


def import_facts(
    store: LatticeStore,
    data: str,
    format: str = "json",
    strategy: str = "skip",
) -> dict:
    """
    Import facts into the store.

    Strategies:
      skip: Skip facts whose code already exists
      overwrite: Overwrite existing facts (increments version)
      fail: Abort if any code already exists
    """
    if format == "json":
        raw = json.loads(data)
    elif format == "yaml":
        raw = yaml.load(data)
    else:
        raise ValueError(f"Unsupported format: {format}")

    results = {"created": 0, "skipped": 0, "overwritten": 0, "errors": []}

    for item in raw:
        try:
            fact = Fact(**item)
            if store.exists(fact.code):
                if strategy == "skip":
                    results["skipped"] += 1
                elif strategy == "overwrite":
                    store.update(fact.code, fact.model_dump(), "Imported (overwrite)")
                    results["overwritten"] += 1
                elif strategy == "fail":
                    raise FileExistsError(f"Fact {fact.code} already exists")
            else:
                store.create(fact)
                results["created"] += 1
        except Exception as e:
            results["errors"].append({"code": item.get("code", "?"), "error": str(e)})

    return results
```

---

## 5. CLI Commands

### 5.1 lattice extract

```
lattice extract FILE [--dry-run] [--model MODEL] [--api-key KEY]
```

**FILE**: Path to document (.md, .txt, .docx).

**--dry-run**: Preview extracted facts in a Rich table without writing to `.lattice/facts/`. This is the default-safe workflow — always preview first.

**--model**: Override extraction model. Default: `claude-sonnet-4-20250514`.

**--api-key**: Override API key. Default: `$LATTICE_ANTHROPIC_API_KEY` env var.

**Workflow**:
1. Read document
2. Call Claude with extraction prompt
3. Display extracted facts in Rich table
4. If not `--dry-run`, ask confirmation: "Write N facts to .lattice/facts/? [y/N]"
5. On confirm, write each fact as Draft status
6. Run `lattice validate` to check refs

### 5.2 lattice export

```
lattice export [--format json|yaml] [--output FILE]
```

Export all facts. Default format: json. Default output: stdout. With `--output`, writes to file.

### 5.3 lattice import

```
lattice import FILE [--format json|yaml] [--strategy skip|overwrite|fail]
```

Import facts from file. Default format: auto-detected from extension. Default strategy: `skip`.

---

## 6. Test Specifications

### test_extract_service.py
| Test | Asserts |
|------|---------|
| `test_read_markdown` | Reads .md file content |
| `test_read_txt` | Reads .txt file content |
| `test_empty_document_errors` | Empty file raises ValueError |
| `test_extraction_prompt_present` | System prompt contains required field names |
| `test_parse_valid_response` | Valid JSON array parsed into Fact objects |
| `test_parse_invalid_fact_skipped` | Invalid fact in response logged and skipped |
| `test_extracted_facts_are_draft` | All extracted facts have status=Draft |
| `test_existing_codes_in_prompt` | Existing codes passed to user message |

Note: Full extraction tests require API access. Mark with `@pytest.mark.integration` and skip in CI unless API key available.

### test_exchange.py
| Test | Asserts |
|------|---------|
| `test_export_json` | Exports valid JSON with all facts |
| `test_export_yaml` | Exports valid YAML with all facts |
| `test_import_json_skip` | Existing facts skipped, new created |
| `test_import_json_overwrite` | Existing facts overwritten with version bump |
| `test_import_json_fail` | Fails on first collision |
| `test_import_round_trip` | Export then import produces identical fact set |
| `test_import_invalid_fact` | Invalid facts in import produce errors list |

---

## 7. Acceptance Criteria — Phase 4 Done When

- [ ] `lattice extract doc.md --dry-run` displays extracted facts without writing
- [ ] `lattice extract doc.md` (without --dry-run) prompts for confirmation, writes Draft facts
- [ ] Extracted facts have valid codes, layers, tags, and status=Draft
- [ ] `lattice export --format json` outputs valid JSON of all facts
- [ ] `lattice export --format yaml` outputs valid YAML of all facts
- [ ] `lattice import facts.json` creates new facts, skips existing (default strategy)
- [ ] `lattice import facts.json --strategy overwrite` updates existing facts
- [ ] Export → Import round trip produces identical fact set
- [ ] All tests in §6 pass (excluding @pytest.mark.integration)

---

## 8. What Phase 4 Does NOT Include

- **Multi-document extraction** — one document at a time. Batch via shell script.
- **Incremental extraction** — re-extracting from an updated doc doesn't diff against existing facts. That's a Phase 7+ reconciliation feature.
- **Custom extraction prompts** — the system prompt is hardcoded. Customization is a future enhancement.
- **PDF extraction** — requires OCR tooling. Out of scope. Convert to text first.
