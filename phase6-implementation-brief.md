# LatticeLens — Phase 6 Implementation Brief
# Bidirectional Reconciliation + SQLite Backend

> **Purpose**: Add the two capabilities that transform LatticeLens from a governance store into a verification engine — bidirectional codebase reconciliation and a SQLite backend for scale.
>
> **Prerequisites**: Phase 5 complete. Full CLI, MCP server, tag/type registries working.

---

## 1. What This Phase Delivers

After Phase 6, a developer can:
- Run `lattice reconcile` and get a report showing which governance facts are confirmed by the code, which are stale, which code behaviors have no corresponding fact, and which facts are orphaned from implementation
- Switch to a SQLite backend (`backend: sqlite` in config.yaml) for lattices approaching thousands of facts, with zero CLI changes
- See advisory warnings when their YAML lattice grows past performance thresholds

This is the phase that builds LatticeLens's moat: no competing tool combines curated fact governance with live codebase verification.

---

## 2. Phase 6A — Bidirectional Reconciliation

### 2.1 Overview

Reconciliation verifies knowledge against codebases in both directions:

```
Facts-to-Code                    Code-to-Facts
─────────────                    ─────────────
"Does ADR-03 match               "Are there architectural
 what the code actually           decisions in the code
 does?"                           with no corresponding fact?"

Finding types:                   Finding types:
  ✓ Confirmed                      ! Untracked
  ⚠ Stale                          ? Orphaned
  ✗ Violated
```

### 2.2 Architecture

```
┌───────────────────────────────────────────┐
│  lattice reconcile [--path src/]          │
│                                           │
│  1. Load lattice facts (via LatticeStore) │
│  2. Scan codebase (AST + text analysis)   │
│  3. LLM-assisted matching (optional)      │
│  4. Produce ReconciliationReport          │
└──────────┬────────────────────────────────┘
           │
           ▼
┌───────────────────────────────────────────┐
│  ReconciliationReport                     │
│                                           │
│  confirmed:  [{code, evidence, file}]     │
│  stale:      [{code, reason, file}]       │
│  violated:   [{code, violation, file}]    │
│  untracked:  [{description, file, line}]  │
│  orphaned:   [{code, reason}]             │
│  summary:    {total, coverage_pct}        │
└───────────────────────────────────────────┘
```

### 2.3 New Files

```
src/lattice_lens/
├── services/
│   ├── reconcile_service.py       # NEW: reconciliation engine
│   └── code_scanner.py            # NEW: codebase scanning + pattern matching
├── cli/
│   └── reconcile_command.py       # NEW: lattice reconcile
tests/
├── test_reconcile_service.py      # NEW
├── test_code_scanner.py           # NEW
└── test_reconcile_cli.py          # NEW
```

### 2.4 Reconciliation Engine

```python
# src/lattice_lens/services/reconcile_service.py
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from lattice_lens.store.protocol import LatticeStore


@dataclass
class Finding:
    """A single reconciliation finding."""
    category: str           # "confirmed", "stale", "violated", "untracked", "orphaned"
    code: str | None        # Fact code (None for untracked findings)
    description: str        # Human-readable explanation
    file: str | None        # Source file path (None for orphaned)
    line: int | None        # Line number in source
    confidence: float       # 0.0-1.0 confidence in the finding
    evidence: str           # Code snippet or text supporting the finding


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
        return len(self.confirmed) + len(self.stale) + len(self.violated) + len(self.orphaned)

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


def reconcile(
    store: LatticeStore,
    codebase_root: Path,
    *,
    include_patterns: list[str] | None = None,
    exclude_patterns: list[str] | None = None,
    use_llm: bool = False,
) -> ReconciliationReport:
    """Run bidirectional reconciliation.

    Phase 1 (rule-based):
      - Facts-to-Code: scan code for evidence of each active fact
      - Code-to-Facts: scan code for patterns that suggest undocumented decisions

    Phase 2 (LLM-assisted, when use_llm=True):
      - Send ambiguous findings to LLM for deeper analysis
    """
    ...
```

### 2.5 Code Scanner

```python
# src/lattice_lens/services/code_scanner.py
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path


@dataclass
class CodeReference:
    """A reference to a lattice fact found in source code."""
    file: Path
    line: int
    code: str              # Fact code found (e.g., "ADR-03")
    context: str           # Surrounding code snippet
    match_type: str        # "explicit" (comment/string), "inferred" (pattern match)


def scan_for_fact_references(
    codebase_root: Path,
    known_codes: list[str],
    include: list[str] | None = None,
    exclude: list[str] | None = None,
) -> list[CodeReference]:
    """Scan source files for explicit fact code references (e.g., '# ADR-03', 'per RISK-07').

    Uses regex pattern matching on comments, docstrings, and string literals.
    Respects .gitignore patterns via exclude list.
    """
    ...


def scan_for_architectural_patterns(
    codebase_root: Path,
    include: list[str] | None = None,
    exclude: list[str] | None = None,
) -> list[dict]:
    """Scan for code patterns that suggest undocumented architectural decisions.

    Detects:
    - Framework/library imports (suggests technology decisions)
    - Configuration patterns (suggests infrastructure decisions)
    - Error handling strategies (suggests policy decisions)
    - Security patterns (authentication, encryption, input validation)
    - API patterns (REST, GraphQL, gRPC)
    """
    ...
```

### 2.6 Facts-to-Code Matching Strategy

For each active fact, the reconciler determines whether the codebase supports it:

| Fact Type | Matching Strategy |
|-----------|-------------------|
| **ADR** (Architecture Decisions) | Look for imports, configs, patterns matching the decision. E.g., ADR-01 (Typer over Click) → check for `import typer` |
| **SP** (System Prompt Rules) | Look for implementation of the described behavior in code |
| **API** (API Specifications) | Match against function signatures, protocol definitions |
| **RUN** (Runbook Procedures) | Check for referenced commands, scripts, config files |
| **DG** (Data Governance) | Check validators, constraints, normalization logic |
| **AUP** (Acceptable Use Policy) | Check for enforcement code (guards, validators, error handlers) |
| **RISK** (Risk Register) | Check for mitigation code referenced in the fact |
| **MC** (Model Card) | Check for validation/resilience code described |

### 2.7 Code-to-Facts Analysis

Scan for patterns that suggest undocumented decisions:

```python
# Pattern categories to detect
ARCHITECTURAL_PATTERNS = {
    "framework": {
        "patterns": [r"import\s+(typer|click|flask|fastapi|django)"],
        "suggests": "Technology choice — should have an ADR",
    },
    "validation": {
        "patterns": [r"class\s+\w+\(BaseModel\)", r"@validator", r"@field_validator"],
        "suggests": "Validation strategy — should be documented",
    },
    "storage": {
        "patterns": [r"sqlite3|sqlalchemy|import\s+redis", r"\.yaml|\.json"],
        "suggests": "Storage decision — should have an ADR",
    },
    "security": {
        "patterns": [r"hashlib|hmac|encrypt|decrypt|sanitize"],
        "suggests": "Security measure — should have a RISK or AUP fact",
    },
    "error_handling": {
        "patterns": [r"class\s+\w+Error\(", r"raise\s+\w+Error"],
        "suggests": "Error strategy — may need documentation",
    },
}
```

### 2.8 CLI Command

```
lattice reconcile [--path PATH] [--include GLOB] [--exclude GLOB]
                  [--llm] [--json] [--verbose]
```

**--path** (default: project root): Directory to scan.
**--include**: Glob patterns to include (default: `**/*.py`).
**--exclude**: Glob patterns to exclude (default: `**/node_modules/**`, `**/.venv/**`, `**/__pycache__/**`).
**--llm**: Enable LLM-assisted analysis for ambiguous findings (requires API key).
**--json**: Output report as JSON.
**--verbose**: Show per-fact matching details.

**Default output** (Rich table):

```
┌─────────────────────────────────────────────────────────────────┐
│                    Reconciliation Report                        │
├──────────┬────────────────────────────────────────┬─────────────┤
│ Category │ Description                            │ Count       │
├──────────┼────────────────────────────────────────┼─────────────┤
│ ✓        │ Confirmed facts                        │ 42          │
│ ⚠        │ Stale facts (code diverged)            │ 3           │
│ ✗        │ Violated facts                         │ 1           │
│ !        │ Untracked code patterns                │ 5           │
│ ?        │ Orphaned facts (no code evidence)      │ 8           │
├──────────┼────────────────────────────────────────┼─────────────┤
│          │ Coverage                               │ 84.0%       │
└──────────┴────────────────────────────────────────┴─────────────┘

⚠ Stale Facts:
  ADR-03 — code uses ruamel.yaml 0.18 but fact references 0.17 API
           src/lattice_lens/store/yaml_store.py:15

✗ Violated:
  AUP-01 — Found file deletion in deprecate path
           src/lattice_lens/store/yaml_store.py:112

! Untracked Patterns:
  Framework: import rich (no ADR documenting Rich library choice)
             src/lattice_lens/cli/main.py:3
```

### 2.9 MCP Integration

Add a `reconcile` tool to the MCP server (read-only, always available):

```python
# In mcp/tools.py
def tool_reconcile(store, codebase_root, **opts) -> dict:
    report = reconcile(store, codebase_root, **opts)
    return report.summary()
```

---

## 3. Phase 6B — SQLite Backend

### 3.1 Overview

A SQLite-backed `LatticeStore` implementation for lattices that outgrow YAML flat files. Shares the same protocol interface — all CLI commands, MCP tools, and services work without modification.

### 3.2 Why SQLite

| Metric | YAML (Tier 1) | SQLite (Tier 2) |
|--------|---------------|-----------------|
| **Fact count** | Sweet spot: 10–500 | Sweet spot: 500–100K |
| **Index rebuild** | Full scan on every operation | Indexed queries, no rebuild |
| **Concurrent reads** | File locking | WAL mode, concurrent readers |
| **Query speed** | O(n) scan | O(log n) indexed |
| **Git-native** | ✓ individual file diffs | ✗ binary blob (use export for diffs) |
| **Zero dependencies** | ✓ | ✓ (stdlib sqlite3) |

### 3.3 New Files

```
src/lattice_lens/
├── store/
│   └── sqlite_store.py          # NEW: SQLite LatticeStore implementation
├── cli/
│   └── backend_command.py       # NEW: lattice backend [switch|status]
tests/
├── test_sqlite_store.py         # NEW
└── test_backend_cli.py          # NEW
```

### 3.4 Schema

```sql
-- Facts table (mirrors the Fact model exactly)
CREATE TABLE facts (
    code        TEXT PRIMARY KEY,
    layer       TEXT NOT NULL CHECK (layer IN ('WHY', 'GUARDRAILS', 'HOW')),
    type        TEXT NOT NULL,
    fact        TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'Draft',
    confidence  TEXT NOT NULL DEFAULT 'Provisional',
    version     INTEGER NOT NULL DEFAULT 1,
    owner       TEXT NOT NULL,
    review_by   TEXT,           -- ISO date string or NULL
    superseded_by TEXT,
    created_at  TEXT NOT NULL,  -- ISO datetime
    updated_at  TEXT NOT NULL,  -- ISO datetime
    FOREIGN KEY (superseded_by) REFERENCES facts(code)
);

-- Tags (many-to-many)
CREATE TABLE fact_tags (
    code TEXT NOT NULL REFERENCES facts(code) ON DELETE CASCADE,
    tag  TEXT NOT NULL,
    PRIMARY KEY (code, tag)
);

-- References (many-to-many)
CREATE TABLE fact_refs (
    source_code TEXT NOT NULL REFERENCES facts(code) ON DELETE CASCADE,
    target_code TEXT NOT NULL,
    PRIMARY KEY (source_code, target_code)
);

-- Changelog (append-only, mirrors changelog.jsonl)
CREATE TABLE changelog (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    action    TEXT NOT NULL,
    code      TEXT NOT NULL,
    reason    TEXT
);

-- Indexes for common queries
CREATE INDEX idx_facts_layer ON facts(layer);
CREATE INDEX idx_facts_status ON facts(status);
CREATE INDEX idx_fact_tags_tag ON fact_tags(tag);
CREATE INDEX idx_fact_refs_target ON fact_refs(target_code);
```

### 3.5 SqliteStore Implementation

```python
# src/lattice_lens/store/sqlite_store.py
from __future__ import annotations
import sqlite3
from datetime import datetime
from pathlib import Path
from lattice_lens.models import Fact, FactStatus, FactConfidence, FactLayer
from lattice_lens.config import HISTORY_DIR


class SqliteStore:
    """SQLite-backed LatticeStore implementation.

    Uses WAL mode for concurrent read access.
    Implements the same LatticeStore protocol as YamlFileStore.
    """

    DB_FILE = "lattice.db"

    def __init__(self, lattice_root: Path):
        self.root = lattice_root
        self.db_path = lattice_root / self.DB_FILE
        self._conn: sqlite3.Connection | None = None
        self._ensure_schema()

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def _ensure_schema(self):
        """Create tables if they don't exist."""
        ...

    # ── LatticeStore protocol methods ──

    def get(self, code: str) -> Fact | None:
        """Single indexed lookup by primary key."""
        ...

    def list_facts(self, **filters) -> list[Fact]:
        """Build SQL WHERE clause from filters. Uses indexed columns."""
        ...

    def create(self, fact: Fact) -> Fact:
        """INSERT fact + tags + refs in a transaction. Append to changelog."""
        ...

    def update(self, code: str, changes: dict, reason: str) -> Fact:
        """UPDATE within transaction. Auto-increment version, set updated_at."""
        ...

    def deprecate(self, code: str, reason: str) -> Fact:
        """Set status=Deprecated within transaction."""
        ...

    def exists(self, code: str) -> bool:
        """SELECT 1 WHERE code = ?"""
        ...

    def all_codes(self) -> list[str]:
        """SELECT code FROM facts ORDER BY code"""
        ...

    def stats(self) -> dict:
        """Aggregate counts using SQL GROUP BY."""
        ...
```

### 3.6 FactIndex Compatibility

The `FactIndex` class is used by graph services and context assembly. For the SQLite backend, provide an adapter that builds a `FactIndex` from the database rather than scanning YAML files:

```python
# In sqlite_store.py
@property
def index(self) -> FactIndex:
    """Build FactIndex from SQLite data (replaces YAML file scan)."""
    idx = FactIndex()
    for fact in self.list_facts(status=None):  # All statuses
        idx._add(fact)
    return idx
```

For large lattices, this can be optimized later with SQL-native graph queries.

### 3.7 Backend Switching

```
lattice backend status          # Show current backend and stats
lattice backend switch sqlite   # Migrate YAML -> SQLite
lattice backend switch yaml     # Migrate SQLite -> YAML
```

**Migration is always explicit** (per RISK-06 — never auto-migrate). The switch command:
1. Reads all facts from the source backend
2. Writes all facts to the target backend
3. Updates `config.yaml` with `backend: sqlite` or `backend: yaml`
4. Preserves the original data (YAML files or DB file) as backup

### 3.8 Advisory Thresholds (RISK-06)

Add performance advisories to `lattice status`:

```python
# In status output
fact_count = stats["total"]
if fact_count >= 2000:
    console.print("[yellow]⚠ 2,000+ facts. Consider: lattice backend switch sqlite[/yellow]")
elif fact_count >= 1500:
    console.print("[dim]ℹ Approaching scale threshold (1,500 facts). SQLite available.[/dim]")
```

### 3.9 Config Changes

```yaml
# .lattice/config.yaml
version: "0.3.0"
backend: yaml          # or "sqlite"
```

The CLI reads `backend` from config and instantiates the appropriate store:

```python
def get_store(lattice_root: Path) -> LatticeStore:
    config = load_config(lattice_root)
    backend = config.get("backend", "yaml")
    if backend == "sqlite":
        from lattice_lens.store.sqlite_store import SqliteStore
        return SqliteStore(lattice_root)
    return YamlFileStore(lattice_root)
```

---

## 4. Test Specifications

### test_reconcile_service.py
| Test | Asserts |
|------|---------|
| `test_explicit_code_reference_found` | Comment `# ADR-03` in source detected as confirmed |
| `test_missing_fact_detected` | Active fact with no code evidence → orphaned |
| `test_violated_fact_detected` | Code contradicts fact → violated finding |
| `test_untracked_pattern_detected` | Import without ADR → untracked finding |
| `test_exclude_patterns_respected` | Files matching exclude globs are skipped |
| `test_report_summary_counts` | Summary dict has correct counts |
| `test_coverage_calculation` | coverage_pct = confirmed / total_checked * 100 |

### test_code_scanner.py
| Test | Asserts |
|------|---------|
| `test_scan_finds_code_in_comments` | `# See ADR-03` → CodeReference |
| `test_scan_finds_code_in_strings` | `"per RISK-07"` → CodeReference |
| `test_scan_ignores_non_code_patterns` | `"ADR" alone` not matched |
| `test_architectural_pattern_detection` | `import typer` → framework pattern |
| `test_security_pattern_detection` | `hashlib.sha256` → security pattern |
| `test_include_exclude_filtering` | Glob patterns filter correctly |

### test_sqlite_store.py
| Test | Asserts |
|------|---------|
| `test_create_and_get` | Round-trip fact through SQLite |
| `test_list_facts_default_status` | Default returns Active facts |
| `test_list_facts_layer_filter` | layer="WHY" returns only WHY facts |
| `test_list_facts_tag_filter` | tags_any matches correctly |
| `test_update_increments_version` | Version bumps by 1 (AUP-03) |
| `test_update_preserves_created_at` | created_at unchanged (AUP-05) |
| `test_deprecate_sets_status` | Status set to Deprecated |
| `test_changelog_appended` | Each mutation adds changelog entry (DG-01) |
| `test_duplicate_code_rejected` | Second create with same code → error (AUP-06) |
| `test_code_immutable` | Changing code in update → rejected (AUP-02) |
| `test_wal_mode_enabled` | PRAGMA journal_mode returns WAL |
| `test_stats_counts` | Group-by counts match actual data |
| `test_index_property` | .index returns valid FactIndex |

### test_backend_cli.py
| Test | Asserts |
|------|---------|
| `test_backend_status` | Shows current backend type |
| `test_switch_yaml_to_sqlite` | All facts migrated, config updated |
| `test_switch_sqlite_to_yaml` | All facts exported to YAML files |
| `test_switch_preserves_data` | Fact count and content identical after switch |

---

## 5. Acceptance Criteria — Phase 6 Done When

### 6A — Reconciliation
- [ ] `lattice reconcile` scans codebase and produces a report
- [ ] Explicit fact code references in comments/strings are detected (confirmed)
- [ ] Active facts with no code evidence are flagged (orphaned)
- [ ] Code patterns without corresponding facts are surfaced (untracked)
- [ ] `--json` outputs machine-readable report
- [ ] `--verbose` shows per-fact matching details
- [ ] MCP tool `reconcile` returns summary
- [ ] All reconciliation tests pass

### 6B — SQLite Backend
- [ ] `SqliteStore` implements full `LatticeStore` protocol
- [ ] All existing tests pass with SQLite backend (parametric fixture)
- [ ] `lattice backend switch sqlite` migrates YAML → SQLite
- [ ] `lattice backend switch yaml` migrates SQLite → YAML
- [ ] Round-trip migration preserves all fact data
- [ ] Advisory thresholds display in `lattice status`
- [ ] WAL mode enabled for concurrent reads
- [ ] All SQLite-specific tests pass

---

## 6. What Phase 6 Does NOT Include

- **LLM-powered reconciliation** — The `--llm` flag is defined but implementation deferred. Rule-based matching comes first.
- **SQL-native graph queries** — FactIndex is built from DB data using the existing in-memory approach. SQL graph traversal (recursive CTEs) is a future optimization.
- **Automatic backend switching** — Per RISK-06, the system advises but never forces tier promotion.
- **Authentication** — MCP server remains unauthenticated. Auth planned for Enterprise tier.
- **Multi-database support** — SQLite only. PostgreSQL/MySQL comes with Tier 4 (DES-06).

---

*Phase 6 transforms LatticeLens from a passive knowledge store into an active verification engine. Reconciliation proves that governance rules match reality. SQLite ensures the tool scales with the team.*
