# LatticeLens — Phase 2 Implementation Brief
# Knowledge Graph + Git Integration

> **Purpose**: Add graph traversal (impact analysis, orphan detection) and git-aware change tracking to the Tier 1 foundation.
>
> **Timeline**: Week 2 (~5 days).
>
> **Prerequisites**: Phase 1 complete. All Phase 1 tests passing.

---

## 1. What This Phase Delivers

After Phase 2, a developer can:
- Ask "if I change ADR-03, what else is affected?" and get a traversal of the reference graph
- Find orphaned facts that have no connections to anything
- See git-formatted diffs of fact changes scoped to `.lattice/facts/`
- View git history for individual facts

---

## 2. New Files

```
src/lattice_lens/
├── services/
│   └── graph_service.py         # NEW: impact analysis, orphan detection
├── cli/
│   ├── graph_commands.py        # NEW: lattice graph impact/orphans
│   └── git_commands.py          # NEW: lattice diff/log
tests/
├── test_graph_service.py        # NEW
├── test_graph_cli.py            # NEW
└── test_git_commands.py         # NEW
```

No changes to existing files except importing new CLI command groups in `cli/main.py`.

---

## 3. Graph Service

```python
# src/lattice_lens/services/graph_service.py
from __future__ import annotations
from dataclasses import dataclass
from lattice_lens.store.protocol import LatticeStore
from lattice_lens.store.index import FactIndex


@dataclass
class ImpactResult:
    source_code: str
    directly_affected: list[str]      # Facts where refs include source_code
    transitively_affected: list[str]  # 2+ hops away (deduplicated, excludes direct)
    all_affected: list[str]           # Union of direct + transitive
    affected_roles: list[str]         # Agent roles whose queries include this fact
    depth_reached: int


def impact_analysis(
    index: FactIndex,
    code: str,
    max_depth: int = 3,
    role_templates: dict | None = None,
) -> ImpactResult:
    """
    Traverse the reverse reference graph from `code`.

    Algorithm:
    1. Find all facts whose `refs` field contains `code` (direct)
    2. For each of those, recurse up to max_depth
    3. Deduplicate, separate direct from transitive
    4. Cross-reference with role query templates to find affected roles
    """
    visited: set[str] = set()
    direct: set[str] = set()
    transitive: set[str] = set()

    def traverse(current: str, depth: int):
        if depth > max_depth or current in visited:
            return
        visited.add(current)
        referencing = index.refs_to(current)  # codes that reference `current`
        for ref_code in referencing:
            if ref_code == code:
                continue
            if depth == 1:
                direct.add(ref_code)
            else:
                transitive.add(ref_code)
            traverse(ref_code, depth + 1)

    traverse(code, 1)
    transitive -= direct  # Don't double-count

    # Determine affected roles
    affected_roles = []
    if role_templates:
        all_affected_codes = direct | transitive | {code}
        for role_name, template in role_templates.items():
            role_layers = template.get("layers", [])
            role_types = template.get("types", [])
            for affected_code in all_affected_codes:
                fact = index.get(affected_code)
                if fact and fact.layer.value in role_layers:
                    if not role_types or fact.type in role_types:
                        affected_roles.append(role_name)
                        break

    return ImpactResult(
        source_code=code,
        directly_affected=sorted(direct),
        transitively_affected=sorted(transitive),
        all_affected=sorted(direct | transitive),
        affected_roles=sorted(set(affected_roles)),
        depth_reached=max_depth,
    )


def find_orphans(index: FactIndex) -> list[str]:
    """
    Find facts that have no inbound refs AND no outbound refs.
    These are disconnected from the knowledge graph.
    """
    orphans = []
    for fact in index.all_facts():
        has_outbound = len(index.refs_from(fact.code)) > 0
        has_inbound = len(index.refs_to(fact.code)) > 0
        if not has_outbound and not has_inbound:
            orphans.append(fact.code)
    return sorted(orphans)


def find_contradiction_candidates(index: FactIndex, min_shared_tags: int = 2) -> list[tuple[str, str, list[str]]]:
    """
    Find pairs of Active facts that share `min_shared_tags` or more tags
    but are in different layers or have different owners.
    Returns list of (code_a, code_b, shared_tags) tuples.
    These are CANDIDATES for human review, not confirmed contradictions.
    """
    active_facts = [f for f in index.all_facts() if f.status.value == "Active"]
    candidates = []
    for i, a in enumerate(active_facts):
        for b in active_facts[i + 1:]:
            shared = sorted(set(a.tags) & set(b.tags))
            if len(shared) >= min_shared_tags:
                if a.layer != b.layer or a.owner != b.owner:
                    candidates.append((a.code, b.code, shared))
    return candidates
```

---

## 4. CLI Commands

### 4.1 lattice graph impact

```
lattice graph impact CODE [--depth N] [--json]
```

Displays:
- **Directly affected**: Facts whose `refs` include CODE
- **Transitively affected**: Facts 2+ hops away
- **Affected roles**: Which agent roles would be impacted

Default `--depth` is 3. Rich-formatted tree output by default, JSON with `--json`.

### 4.2 lattice graph orphans

```
lattice graph orphans [--json]
```

Lists all facts with no references in or out. Rich table with Code, Layer, Type, Status.

### 4.3 lattice diff

```
lattice diff [--staged]
```

Wrapper around `git diff` scoped to `.lattice/facts/`. Parses the diff to show:
- Which fact codes changed
- Which fields within each fact changed
- Summary line: "3 facts modified, 1 added, 0 deprecated"

`--staged` shows only staged changes (maps to `git diff --staged`).

**Implementation**: Shell out to `git diff .lattice/facts/`, parse the unified diff output, extract YAML field names from changed lines.

### 4.4 lattice log

```
lattice log [CODE] [--limit N]
```

Without CODE: `git log --oneline .lattice/facts/` (recent changes to any fact).
With CODE: `git log --follow .lattice/facts/{CODE}.yaml` (history of specific fact).

`--limit` defaults to 20.

---

## 5. Role Templates for Impact Display

Load role templates from `.lattice/roles/*.yaml` (created during `lattice init`). Format:

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
```

The graph service reads these to determine which roles are affected by a fact change.

---

## 6. Test Specifications

### test_graph_service.py
| Test | Asserts |
|------|---------|
| `test_impact_direct` | Changing ADR-03 surfaces facts that ref ADR-03 (PRD-01, RISK-07, MC-01 via reverse lookup) |
| `test_impact_transitive` | 2-hop traversal finds indirectly affected facts |
| `test_impact_respects_max_depth` | depth=1 returns only direct, no transitive |
| `test_impact_no_self_reference` | Source code not in its own affected list |
| `test_impact_cycle_safe` | Circular refs don't cause infinite loop |
| `test_orphan_detection` | Facts with no refs appear in orphan list |
| `test_orphan_excludes_connected` | Facts with at least one ref (in or out) not in orphan list |
| `test_contradiction_candidates` | Two active facts sharing 2+ tags in different layers flagged |
| `test_affected_roles` | Changing a WHY/ADR fact shows Planning and Architecture roles affected |

### test_graph_cli.py
| Test | Asserts |
|------|---------|
| `test_impact_output` | `lattice graph impact ADR-03` prints direct and transitive sections |
| `test_impact_json` | `--json` returns valid JSON with expected keys |
| `test_orphans_output` | `lattice graph orphans` lists disconnected facts |

### test_git_commands.py
| Test | Asserts |
|------|---------|
| `test_diff_detects_changes` | After modifying a fact, `lattice diff` shows the code |
| `test_log_shows_history` | After commits, `lattice log ADR-03` shows entries |

---

## 7. Acceptance Criteria — Phase 2 Done When

- [ ] `lattice graph impact ADR-03` shows directly and transitively affected facts
- [ ] `lattice graph impact ADR-03 --depth 1` shows only direct
- [ ] `lattice graph impact ADR-03 --json` returns valid JSON
- [ ] `lattice graph orphans` lists disconnected facts
- [ ] After seeding, placeholder Draft facts appear as orphans
- [ ] `lattice diff` shows fact-level summary of git changes
- [ ] `lattice log ADR-03` shows git history for that fact file
- [ ] Circular references in the graph do not crash traversal
- [ ] All tests in §6 pass

---

## 8. What Phase 2 Does NOT Include

- **Context assembly** (Phase 3) — token budgets, role-based context building
- **Contradiction resolution** — candidates are surfaced, not auto-resolved
- **Merge conflict tooling** — standard git merge handles YAML conflicts
