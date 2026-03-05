# LatticeLens — Phase 3 Implementation Brief
# Context Assembly Engine

> **Purpose**: Build the role-scoped, token-budgeted context assembly that feeds governed facts directly into agent prompts. This is the core value proposition — after Phase 3, any agent framework can pull precisely the facts it needs from the lattice.
>
> **Timeline**: Week 3 (~5 days).
>
> **Prerequisites**: Phase 2 complete. Graph traversal and role templates working.

---

## 1. What This Phase Delivers

After Phase 3, a developer can:
- Run `lattice context planning` and get a token-budgeted set of facts scoped to the Planning Agent role
- Pipe `lattice context planning --json` directly into an agent prompt
- See exactly how many tokens each role's context consumes
- Control the budget and see which facts were included vs. excluded

---

## 2. New Files

```
src/lattice_lens/
├── services/
│   └── context_service.py       # NEW: context assembly + token budgeting
├── cli/
│   └── context_commands.py      # NEW: lattice context {role}
tests/
├── test_context_service.py      # NEW
└── test_context_cli.py          # NEW
```

Add `tiktoken>=0.6.0` to `pyproject.toml` dependencies.

---

## 3. Context Assembly Service

```python
# src/lattice_lens/services/context_service.py
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from ruamel.yaml import YAML
from lattice_lens.models import Fact, FactConfidence
from lattice_lens.store.protocol import LatticeStore
from lattice_lens.store.index import FactIndex

yaml_loader = YAML()


@dataclass
class ContextBudget:
    total_tokens: int = 40_000
    used_tokens: int = 0
    fact_count: int = 0

    @property
    def remaining(self) -> int:
        return max(0, self.total_tokens - self.used_tokens)


@dataclass
class AssembledContext:
    role: str
    facts_included: list[Fact]
    facts_excluded: list[str]   # Codes that didn't fit in budget
    refs_outside: list[str]     # Referenced codes not in context (awareness pointers)
    budget: ContextBudget
    token_breakdown: list[dict] # [{code, tokens, cumulative}]


def estimate_tokens(fact: Fact) -> int:
    """
    Estimate token count for a fact when injected into context.
    Uses tiktoken cl100k_base encoding (GPT-4/Claude compatible).
    """
    import tiktoken
    enc = tiktoken.get_encoding("cl100k_base")

    # Format as it would appear in a prompt
    text = (
        f"[{fact.code}] ({fact.layer.value}/{fact.type}) "
        f"{fact.fact} "
        f"Tags: {', '.join(fact.tags)} | "
        f"Status: {fact.status.value} | Confidence: {fact.confidence.value}"
    )
    if fact.refs:
        text += f" | Refs: {', '.join(fact.refs)}"

    return len(enc.encode(text))


def load_role_template(roles_dir: Path, role_name: str) -> dict:
    """Load a role query template from .lattice/roles/{role_name}.yaml"""
    path = roles_dir / f"{role_name}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Role template not found: {path}")
    with open(path) as f:
        return yaml_loader.load(f)


def query_facts_for_role(index: FactIndex, template: dict) -> list[Fact]:
    """
    Execute the role's query template against the fact index.
    Returns facts matching the role's layer/type criteria, status=Active.
    """
    results: dict[str, Fact] = {}  # code -> Fact, deduplicated

    # Primary query
    query_conf = template.get("query", {})
    primary_layers = query_conf.get("layers", [])
    primary_types = query_conf.get("types", [])

    for fact in index.all_facts():
        if fact.status.value != "Active":
            continue
        if fact.layer.value in primary_layers:
            if not primary_types or fact.type in primary_types:
                results[fact.code] = fact

    # Extra queries (cross-layer additions)
    extras = query_conf.get("extra", [])
    if isinstance(extras, dict):
        extras = [extras]
    for extra in extras:
        extra_layer = extra.get("layer", "")
        extra_types = extra.get("types", [])
        for fact in index.all_facts():
            if fact.status.value != "Active":
                continue
            if fact.layer.value == extra_layer:
                if not extra_types or fact.type in extra_types:
                    results[fact.code] = fact

    # Extra layers (alternative format)
    for extra_layer_conf in query_conf.get("extra_layers", []):
        el = extra_layer_conf.get("layer", "")
        et = extra_layer_conf.get("types", [])
        for fact in index.all_facts():
            if fact.status.value != "Active":
                continue
            if fact.layer.value == el:
                if not et or fact.type in et:
                    results[fact.code] = fact

    # Tag-based filtering (if specified)
    tags_any = query_conf.get("tags_any", [])
    if tags_any:
        tag_filtered = {}
        for code, fact in results.items():
            if set(fact.tags) & set(tags_any):
                tag_filtered[code] = fact
        results = tag_filtered

    return list(results.values())


def prioritize_facts(facts: list[Fact]) -> list[Fact]:
    """
    Sort facts by priority for context loading:
    1. Confirmed first, then Provisional, then Assumed
    2. Within each confidence tier, sort by updated_at DESC (most recent first)
    """
    confidence_order = {
        FactConfidence.CONFIRMED: 0,
        FactConfidence.PROVISIONAL: 1,
        FactConfidence.ASSUMED: 2,
    }
    return sorted(
        facts,
        key=lambda f: (confidence_order.get(f.confidence, 9), -(f.updated_at.timestamp())),
    )


def assemble_context(
    index: FactIndex,
    roles_dir: Path,
    role_name: str,
    token_budget: int = 40_000,
) -> AssembledContext:
    """
    Full context assembly pipeline:
    1. Load role template
    2. Query facts matching role criteria
    3. Prioritize by confidence + recency
    4. Pack into budget, tracking included/excluded
    5. Collect awareness pointers for refs outside context
    """
    template = load_role_template(roles_dir, role_name)
    candidates = query_facts_for_role(index, template)
    prioritized = prioritize_facts(candidates)

    budget = ContextBudget(total_tokens=token_budget)
    included: list[Fact] = []
    excluded: list[str] = []
    breakdown: list[dict] = []

    for fact in prioritized:
        tokens = estimate_tokens(fact)
        if budget.used_tokens + tokens <= budget.total_tokens:
            budget.used_tokens += tokens
            budget.fact_count += 1
            included.append(fact)
            breakdown.append({
                "code": fact.code,
                "tokens": tokens,
                "cumulative": budget.used_tokens,
            })
        else:
            excluded.append(fact.code)

    # Awareness pointers: refs from included facts that are NOT in the included set
    included_codes = {f.code for f in included}
    refs_outside = set()
    for fact in included:
        for ref in fact.refs:
            if ref not in included_codes:
                refs_outside.add(ref)

    return AssembledContext(
        role=role_name,
        facts_included=included,
        facts_excluded=excluded,
        refs_outside=sorted(refs_outside),
        budget=budget,
        token_breakdown=breakdown,
    )
```

---

## 4. CLI Commands

### 4.1 lattice context

```
lattice context ROLE [--budget TOKENS] [--json] [--verbose]
```

**ROLE**: Name of a role template file in `.lattice/roles/` (without .yaml extension). Examples: `planning`, `architecture`, `implementation`, `qa`, `deploy`.

**--budget**: Token budget for the context window. Default: 40000.

**--json**: Output the assembled context as JSON. Suitable for piping directly into an agent prompt builder.

**--verbose**: Show the token breakdown per fact, excluded facts, and awareness pointers.

**Default output** (Rich-formatted):
```
Context for: Planning Agent (Product Strategist)
Budget: 4,230 / 40,000 tokens (10.6%)
Facts: 7 included, 0 excluded

 Code    Layer       Type                             Tokens  Cumulative
 ADR-01  WHY         Architecture Decision Record     189     189
 ADR-03  WHY         Architecture Decision Record     212     401
 PRD-01  WHY         Product Requirement              156     557
 ...
 AUP-05  GUARDRAILS  Acceptable Use Policy Rule       198     4,230

Refs outside context (awareness): RISK-03, RISK-05, ETH-01, MON-01
```

**JSON output** structure:
```json
{
  "role": "planning",
  "budget": {"total": 40000, "used": 4230, "remaining": 35770},
  "facts": [
    {"code": "ADR-01", "layer": "WHY", "type": "...", "fact": "...", "tags": [...], "tokens": 189}
  ],
  "excluded": [],
  "refs_outside": ["RISK-03", "RISK-05"],
  "token_breakdown": [{"code": "ADR-01", "tokens": 189, "cumulative": 189}]
}
```

### 4.2 lattice context --list

```
lattice context --list
```

Lists all available role templates from `.lattice/roles/` with name and description.

---

## 5. Default Role Templates

Created during `lattice init` in Phase 1. The templates follow the query patterns from the Agent Factory design doc:

```yaml
# .lattice/roles/planning.yaml
name: Planning Agent
description: "Product Strategist — scopes work, defines acceptance criteria"
query:
  layers: ["WHY"]
  types: ["Architecture Decision Record", "Product Requirement"]
  extra:
    - layer: "GUARDRAILS"
      types: ["Acceptable Use Policy Rule"]

# .lattice/roles/architecture.yaml
name: Architecture Agent
description: "Systems Architect — designs components, annotates risks"
query:
  layers: ["WHY"]
  types: ["Architecture Decision Record", "Design Proposal Decision"]
  extra_layers:
    - layer: "GUARDRAILS"
      types: ["Model Card Entry", "Risk Assessment Finding", "Data Governance Rule"]
    - layer: "HOW"
      types: ["API Specification"]

# .lattice/roles/implementation.yaml
name: Implementation Agent
description: "Senior Developer — writes code, configures prompts"
query:
  layers: ["GUARDRAILS"]
  types: ["Acceptable Use Policy Rule", "Data Governance Rule"]
  extra:
    - layer: "HOW"
      types: ["System Prompt Rule", "API Specification", "MLOps Pipeline Rule"]

# .lattice/roles/qa.yaml
name: QA Agent
description: "Quality & Compliance Reviewer — validates against criteria"
query:
  layers: ["WHY"]
  types: ["Product Requirement", "Ethical Review Finding"]
  extra_layers:
    - layer: "GUARDRAILS"
      types: ["Model Card Entry", "Acceptable Use Policy Rule", "Risk Assessment Finding", "Compliance Requirement"]
    - layer: "HOW"
      types: ["Monitoring Rule"]

# .lattice/roles/deploy.yaml
name: Deploy Agent
description: "DevOps / Release Engineer — deploys and monitors"
query:
  layers: ["GUARDRAILS"]
  types: ["Risk Assessment Finding"]
  tags_any: ["deploy-time", "high-severity"]
  extra:
    - layer: "HOW"
      types: ["Runbook Procedure", "MLOps Pipeline Rule", "Monitoring Rule"]
```

---

## 6. Test Specifications

### test_context_service.py
| Test | Asserts |
|------|---------|
| `test_estimate_tokens_nonzero` | Every fact produces > 0 tokens |
| `test_estimate_tokens_reasonable` | Average fact is 80-250 tokens |
| `test_query_planning_role` | Planning role gets WHY ADRs, PRDs, and GUARDRAILS AUP facts |
| `test_query_architecture_role` | Architecture role gets ADRs, Design Proposals, Model Cards, Risk, Data Gov, API Specs |
| `test_query_excludes_deprecated` | Deprecated facts never included |
| `test_prioritize_confirmed_first` | Confirmed facts sort before Provisional |
| `test_prioritize_recent_within_tier` | Most recently updated facts first within same confidence |
| `test_budget_respected` | With a small budget (500 tokens), only a few facts included |
| `test_excluded_facts_listed` | Facts beyond budget appear in excluded list |
| `test_refs_outside_context` | Refs from included facts pointing to non-included facts listed |
| `test_full_assembly_planning` | End-to-end assembly for planning role produces valid result |
| `test_full_assembly_all_roles` | All 5 default roles assemble without error |
| `test_unknown_role_errors` | Non-existent role raises FileNotFoundError |

### test_context_cli.py
| Test | Asserts |
|------|---------|
| `test_context_default_output` | `lattice context planning` prints table with budget summary |
| `test_context_json_output` | `--json` returns valid JSON with facts, budget, refs_outside |
| `test_context_budget_flag` | `--budget 500` limits included facts |
| `test_context_list_roles` | `--list` shows all 5 default roles |
| `test_context_verbose` | `--verbose` shows token breakdown and excluded list |

---

## 7. Acceptance Criteria — Phase 3 Done When

- [ ] `lattice context planning` displays facts scoped to Planning Agent role
- [ ] `lattice context planning --json` outputs valid JSON suitable for agent prompt injection
- [ ] `lattice context planning --budget 500` respects the token limit
- [ ] `lattice context --list` shows all available roles with descriptions
- [ ] Token estimates are within 20% of actual tokenizer count (spot-check manually)
- [ ] Confirmed facts always appear before Provisional in assembled context
- [ ] Excluded facts and refs-outside-context are listed in verbose output
- [ ] All 5 default roles (planning, architecture, implementation, qa, deploy) assemble without error
- [ ] All tests in §6 pass

---

## 8. What Phase 3 Does NOT Include

- **Prompt template formatting** — Phase 3 outputs structured data. The consuming agent framework formats it into its own prompt template.
- **Dynamic query expansion** — "pull all facts tagged X" is a future enhancement. Phase 3 uses static role templates.
- **Streaming** — context is assembled synchronously. For the fact counts we're dealing with, this is instant.
- **Caching** — context assembly is fast enough without caching. Add if needed.
