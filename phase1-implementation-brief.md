# LatticeLens — Phase 1 Implementation Brief
# Core CLI + YAML Backend (Tier 1)

> **Purpose**: Executable spec for building the Tier 1 YAML-backed lattice. At the end of Phase 1, a developer can `lattice init`, create facts, query them, edit them, validate integrity, and carry the entire knowledge base with `git clone`.
>
> **Timeline**: ~6 days, split into three sub-phases (1A, 1B, 1C).
>
> **Prerequisites**: Python 3.11+, pip. Nothing else.

---

## 1. Project Setup

### 1.1 Repository Structure

```
lattice-lens/
├── README.md
├── LICENSE                              # MIT License
├── CONTRIBUTING.md
├── pyproject.toml
├── src/
│   └── lattice_lens/
│       ├── __init__.py
│       ├── config.py                    # Settings + lattice discovery
│       ├── models.py                    # Pydantic fact models + enums
│       ├── store/
│       │   ├── __init__.py
│       │   ├── protocol.py             # LatticeStore protocol definition
│       │   ├── yaml_store.py           # YamlFileStore implementation
│       │   └── index.py                # In-memory index builder
│       ├── services/
│       │   ├── __init__.py
│       │   ├── fact_service.py         # Business logic (validation, lifecycle)
│       │   └── validate_service.py     # Schema + integrity checks
│       └── cli/
│           ├── __init__.py
│           ├── main.py                 # Typer app entrypoint
│           ├── fact_commands.py        # lattice fact add/get/ls/edit/deprecate
│           ├── init_command.py         # lattice init
│           ├── validate_command.py     # lattice validate + reindex
│           ├── seed_command.py         # lattice seed
│           └── status_command.py       # lattice status
├── tests/
│   ├── conftest.py                     # Fixtures: temp .lattice dirs, seed data
│   ├── test_models.py                  # Pydantic validation tests
│   ├── test_yaml_store.py             # YamlFileStore CRUD tests
│   ├── test_index.py                  # Index building + query tests
│   ├── test_fact_service.py           # Business rule tests
│   ├── test_validate.py              # Integrity check tests
│   └── test_cli.py                    # CLI integration tests
├── seed/
│   └── example_facts.yaml             # 12 example facts from design doc
└── docs/
    └── latticelens-git-native-redesign.docx
```

### 1.2 Python Dependencies

```toml
# pyproject.toml
[project]
name = "lattice-lens"
version = "0.1.0"
description = "Knowledge governance layer for AI agent systems"
license = {text = "MIT"}
requires-python = ">=3.11"
dependencies = [
    "typer>=0.12.0",
    "rich>=13.0.0",
    "pydantic>=2.6.0",
    "pydantic-settings>=2.1.0",
    "ruamel.yaml>=0.18.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "ruff>=0.3.0",
]

[project.scripts]
lattice = "lattice_lens.cli.main:app"

[build-system]
requires = ["setuptools>=68.0"]
build-backend = "setuptools.backends._legacy:_Backend"
```

### 1.3 Application Config

```python
# src/lattice_lens/config.py
from pathlib import Path
from pydantic_settings import BaseSettings


LATTICE_DIR = ".lattice"
FACTS_DIR = "facts"
ROLES_DIR = "roles"
HISTORY_DIR = "history"
CONFIG_FILE = "config.yaml"
INDEX_FILE = "index.yaml"

LAYER_PREFIXES = {
    "WHY": ["ADR", "PRD", "ETH", "DES"],
    "GUARDRAILS": ["MC", "AUP", "RISK", "DG", "COMP"],
    "HOW": ["SP", "API", "RUN", "ML", "MON"],
}


class Settings(BaseSettings):
    """Runtime settings. Resolved from env vars or config.yaml."""
    lattice_root: Path | None = None  # auto-discovered from cwd upward

    # For LLM-powered extraction (Phase 4)
    anthropic_api_key: str = ""
    extraction_model: str = "claude-sonnet-4-20250514"

    class Config:
        env_prefix = "LATTICE_"


def find_lattice_root(start: Path | None = None) -> Path | None:
    """Walk up from start (default: cwd) looking for .lattice/ directory."""
    current = start or Path.cwd()
    for parent in [current, *current.parents]:
        if (parent / LATTICE_DIR).is_dir():
            return parent / LATTICE_DIR
        if parent == parent.parent:
            break
    return None
```

---

## 2. Data Models

### 2.1 Pydantic Fact Model

```python
# src/lattice_lens/models.py
from __future__ import annotations
import enum
from datetime import date, datetime
from pydantic import BaseModel, Field, field_validator, model_validator
from lattice_lens.config import LAYER_PREFIXES


class FactLayer(str, enum.Enum):
    WHY = "WHY"
    GUARDRAILS = "GUARDRAILS"
    HOW = "HOW"


class FactStatus(str, enum.Enum):
    DRAFT = "Draft"
    UNDER_REVIEW = "Under Review"
    ACTIVE = "Active"
    DEPRECATED = "Deprecated"
    SUPERSEDED = "Superseded"


class FactConfidence(str, enum.Enum):
    CONFIRMED = "Confirmed"
    PROVISIONAL = "Provisional"
    ASSUMED = "Assumed"


class Fact(BaseModel):
    """Core fact model. One YAML file per fact."""
    code: str = Field(..., pattern=r"^[A-Z]+-\d+$")
    layer: FactLayer
    type: str = Field(..., min_length=1, max_length=100)
    fact: str = Field(..., min_length=10, description="The atomic fact text")
    tags: list[str] = Field(..., min_length=2)
    status: FactStatus = FactStatus.DRAFT
    confidence: FactConfidence = FactConfidence.CONFIRMED
    version: int = Field(default=1, ge=1)
    refs: list[str] = Field(default_factory=list)
    superseded_by: str | None = None
    owner: str = Field(..., min_length=1, max_length=100)
    review_by: date | None = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    @field_validator("tags")
    @classmethod
    def normalize_tags(cls, v: list[str]) -> list[str]:
        normalized = []
        for tag in v:
            tag = tag.lower().strip()
            if not tag.replace("-", "").replace("_", "").isalnum():
                raise ValueError(f"Tag must be alphanumeric with hyphens/underscores: {tag}")
            normalized.append(tag)
        return sorted(set(normalized))

    @model_validator(mode="after")
    def validate_code_layer_prefix(self) -> "Fact":
        prefix = self.code.split("-")[0]
        allowed = LAYER_PREFIXES.get(self.layer.value, [])
        if prefix not in allowed:
            raise ValueError(
                f"Code prefix '{prefix}' not allowed for layer {self.layer.value}. "
                f"Allowed: {allowed}"
            )
        return self

    @model_validator(mode="after")
    def validate_superseded(self) -> "Fact":
        if self.status == FactStatus.SUPERSEDED and not self.superseded_by:
            raise ValueError("superseded_by is required when status is Superseded")
        return self
```

---

## 3. LatticeStore Protocol

```python
# src/lattice_lens/store/protocol.py
from __future__ import annotations
from typing import Protocol, runtime_checkable
from lattice_lens.models import Fact


@runtime_checkable
class LatticeStore(Protocol):
    """Storage abstraction. All CLI/MCP tools program against this."""

    def get(self, code: str) -> Fact | None: ...
    def list_facts(self, **filters) -> list[Fact]: ...
    def create(self, fact: Fact) -> Fact: ...
    def update(self, code: str, changes: dict, reason: str) -> Fact: ...
    def deprecate(self, code: str, reason: str) -> Fact: ...
    def exists(self, code: str) -> bool: ...
    def all_codes(self) -> list[str]: ...
    def stats(self) -> dict: ...
```

---

## 4. YamlFileStore Implementation

```python
# src/lattice_lens/store/yaml_store.py
"""
YamlFileStore — reads/writes facts as individual YAML files in .lattice/facts/.
Builds an in-memory index on first access for fast queries.
"""
from __future__ import annotations
from pathlib import Path
from datetime import datetime
from ruamel.yaml import YAML
from lattice_lens.models import Fact, FactStatus
from lattice_lens.store.index import FactIndex
from lattice_lens.config import FACTS_DIR, HISTORY_DIR

yaml = YAML()
yaml.default_flow_style = False


class YamlFileStore:
    def __init__(self, lattice_root: Path):
        self.root = lattice_root
        self.facts_dir = lattice_root / FACTS_DIR
        self.history_dir = lattice_root / HISTORY_DIR
        self._index: FactIndex | None = None

    @property
    def index(self) -> FactIndex:
        if self._index is None:
            self._index = FactIndex.build(self.facts_dir)
        return self._index

    def invalidate_index(self):
        self._index = None

    def get(self, code: str) -> Fact | None:
        path = self.facts_dir / f"{code}.yaml"
        if not path.exists():
            return None
        return self._read_fact(path)

    def list_facts(self, **filters) -> list[Fact]:
        """
        Supported filters:
          layer: str | list[str]
          status: str | list[str]  (default: ["Active"])
          tags_any: list[str]      (match ANY tag)
          tags_all: list[str]      (match ALL tags)
          type: str | list[str]
          text_search: str         (substring match on fact text)
        """
        facts = self.index.all_facts()

        # Apply filters
        layer = filters.get("layer")
        if layer:
            layers = [layer] if isinstance(layer, str) else layer
            facts = [f for f in facts if f.layer.value in layers]

        status = filters.get("status", ["Active"])
        if status:
            statuses = [status] if isinstance(status, str) else status
            facts = [f for f in facts if f.status.value in statuses]

        tags_any = filters.get("tags_any")
        if tags_any:
            facts = [f for f in facts if set(f.tags) & set(tags_any)]

        tags_all = filters.get("tags_all")
        if tags_all:
            tag_set = set(tags_all)
            facts = [f for f in facts if tag_set.issubset(set(f.tags))]

        type_filter = filters.get("type")
        if type_filter:
            types = [type_filter] if isinstance(type_filter, str) else type_filter
            facts = [f for f in facts if f.type in types]

        text_search = filters.get("text_search")
        if text_search:
            query = text_search.lower()
            facts = [f for f in facts if query in f.fact.lower()]

        return facts

    def create(self, fact: Fact) -> Fact:
        path = self.facts_dir / f"{fact.code}.yaml"
        if path.exists():
            raise FileExistsError(f"Fact {fact.code} already exists")
        self._write_fact(path, fact)
        self._append_changelog("create", fact.code, "Initial creation")
        self.invalidate_index()
        return fact

    def update(self, code: str, changes: dict, reason: str) -> Fact:
        current = self.get(code)
        if current is None:
            raise FileNotFoundError(f"Fact {code} not found")

        # Build updated fact
        data = current.model_dump()
        data.update(changes)
        data["version"] = current.version + 1
        data["updated_at"] = datetime.now()
        updated = Fact(**data)

        self._write_fact(self.facts_dir / f"{code}.yaml", updated)
        self._append_changelog("update", code, reason)
        self.invalidate_index()
        return updated

    def deprecate(self, code: str, reason: str) -> Fact:
        return self.update(code, {"status": "Deprecated"}, reason)

    def exists(self, code: str) -> bool:
        return (self.facts_dir / f"{code}.yaml").exists()

    def all_codes(self) -> list[str]:
        return [p.stem for p in self.facts_dir.glob("*.yaml")]

    def stats(self) -> dict:
        facts = self.index.all_facts()
        by_layer = {}
        by_status = {}
        stale = 0
        today = datetime.now().date()
        for f in facts:
            by_layer[f.layer.value] = by_layer.get(f.layer.value, 0) + 1
            by_status[f.status.value] = by_status.get(f.status.value, 0) + 1
            if f.review_by and f.review_by < today:
                stale += 1
        return {
            "total": len(facts),
            "by_layer": by_layer,
            "by_status": by_status,
            "stale": stale,
            "backend": "yaml",
        }

    # ── Private helpers ──

    def _read_fact(self, path: Path) -> Fact:
        with open(path) as f:
            data = yaml.load(f)
        return Fact(**data)

    def _write_fact(self, path: Path, fact: Fact):
        data = fact.model_dump(mode="json")
        with open(path, "w") as f:
            yaml.dump(data, f)

    def _append_changelog(self, action: str, code: str, reason: str):
        import json
        self.history_dir.mkdir(parents=True, exist_ok=True)
        entry = {
            "timestamp": datetime.now().isoformat(),
            "action": action,
            "code": code,
            "reason": reason,
        }
        changelog = self.history_dir / "changelog.jsonl"
        with open(changelog, "a") as f:
            f.write(json.dumps(entry) + "\n")
```

### 4.1 In-Memory Index

```python
# src/lattice_lens/store/index.py
from __future__ import annotations
from pathlib import Path
from lattice_lens.models import Fact
from ruamel.yaml import YAML

yaml = YAML()


class FactIndex:
    """In-memory index built by scanning .lattice/facts/."""

    def __init__(self):
        self._facts: dict[str, Fact] = {}       # code -> Fact
        self._by_tag: dict[str, set[str]] = {}  # tag -> {codes}
        self._by_layer: dict[str, set[str]] = {}  # layer -> {codes}
        self._refs_forward: dict[str, set[str]] = {}  # code -> {referenced codes}
        self._refs_reverse: dict[str, set[str]] = {}  # code -> {codes that reference this}

    @classmethod
    def build(cls, facts_dir: Path) -> "FactIndex":
        idx = cls()
        for path in sorted(facts_dir.glob("*.yaml")):
            try:
                with open(path) as f:
                    data = yaml.load(f)
                fact = Fact(**data)
                idx._add(fact)
            except Exception as e:
                # Log but don't crash — partial index is better than no index
                import sys
                print(f"Warning: skipping {path.name}: {e}", file=sys.stderr)
        return idx

    def _add(self, fact: Fact):
        self._facts[fact.code] = fact
        # Tag index
        for tag in fact.tags:
            self._by_tag.setdefault(tag, set()).add(fact.code)
        # Layer index
        self._by_layer.setdefault(fact.layer.value, set()).add(fact.code)
        # Ref graph
        self._refs_forward[fact.code] = set(fact.refs)
        for ref in fact.refs:
            self._refs_reverse.setdefault(ref, set()).add(fact.code)

    def all_facts(self) -> list[Fact]:
        return list(self._facts.values())

    def get(self, code: str) -> Fact | None:
        return self._facts.get(code)

    def codes_by_tag(self, tag: str) -> set[str]:
        return self._by_tag.get(tag, set())

    def codes_by_layer(self, layer: str) -> set[str]:
        return self._by_layer.get(layer, set())

    def refs_from(self, code: str) -> set[str]:
        return self._refs_forward.get(code, set())

    def refs_to(self, code: str) -> set[str]:
        return self._refs_reverse.get(code, set())
```

---

## 5. Business Rules (Fact Service)

These rules MUST be enforced on every write operation:

1. **Code immutability**: A fact's code never changes after creation.
2. **Version monotonicity**: Version increments by exactly 1 on each update.
3. **Ref integrity** (soft): Refs pointing to non-existent codes produce a warning, not an error. This allows creating facts in any order.
4. **Superseded requires target**: Status = `Superseded` requires `superseded_by` to be set to a valid code.
5. **No hard deletes**: Deprecate sets status to `Deprecated`, never removes the file.
6. **Stale detection**: On read, if `review_by < today`, flag as stale in display. Do NOT change the file.
7. **Tag normalization**: Tags are always lowercase, sorted, deduplicated.
8. **Auto-timestamping**: `updated_at` is set on every write. `created_at` is never modified after initial creation.
9. **Layer-code consistency**: Code prefix must match the allowed prefixes for its layer.
10. **Changelog append**: Every create, update, and deprecate appends to `history/changelog.jsonl`.

---

## 6. CLI Commands

### 6.1 lattice init

```
lattice init [--path DIR]
```

Creates `.lattice/` directory with:
- `config.yaml` (backend: auto, auto_promote thresholds)
- `facts/` (empty directory)
- `roles/` (with default role templates: planning.yaml, architecture.yaml, implementation.yaml, qa.yaml, deploy.yaml)
- `history/` (empty directory)
- `.gitignore` (index.yaml, *.bak/)

If `.lattice/` already exists, print error and exit.

### 6.2 lattice fact add

```
lattice fact add              # interactive mode
lattice fact add --from FILE  # from YAML file
```

**Interactive mode**: Prompt for each field using Rich prompts. Code, layer, type, fact text, tags (comma-separated), owner, status (default Draft), confidence (default Confirmed), refs (comma-separated, optional), review_by (optional).

**From file**: Read YAML, validate via Pydantic, write to `.lattice/facts/{code}.yaml`.

**Validation**: Run full Pydantic model validation. On failure, print error and do NOT write.

### 6.3 lattice fact get

```
lattice fact get CODE [--json]
```

Read `.lattice/facts/{CODE}.yaml`. Display as Rich-formatted panel (default) or raw JSON (`--json`). Print stale warning if `review_by < today`.

### 6.4 lattice fact ls

```
lattice fact ls [--layer LAYER] [--tag TAG] [--status STATUS] [--type TYPE] [--json]
```

List facts matching filters. Default status filter is `Active`. Rich table output with columns: Code, Layer, Type, Status, Tags (truncated), Version. JSON mode outputs array.

### 6.5 lattice fact edit

```
lattice fact edit CODE
```

Opens `.lattice/facts/{CODE}.yaml` in `$EDITOR` (fallback: `vi`). On save, re-validate via Pydantic. If validation fails, ask user to re-edit or abort. On success, increment version, update `updated_at`, append changelog.

### 6.6 lattice fact deprecate

```
lattice fact deprecate CODE --reason "REASON"
```

Sets status to `Deprecated`, increments version, appends changelog. Reason is required.

### 6.7 lattice validate

```
lattice validate [--fix]
```

Checks:
- All YAML files parse successfully
- All facts pass Pydantic validation
- No duplicate codes across files
- All ref targets exist (warn on missing, don't error)
- Code prefix matches layer
- Tags are lowercase and sorted
- No superseded facts missing `superseded_by`
- Stale facts (past `review_by`) listed

`--fix` auto-corrects: normalizes tags, sorts them, updates `updated_at` on fixed files.

### 6.8 lattice reindex

```
lattice reindex
```

Rebuilds `index.yaml` from scanning all fact files. Contains:
- Tag reverse index (tag -> [codes])
- Layer/type groups
- Ref graph (forward + reverse adjacency)
- Fact counts by layer, status

### 6.9 lattice seed

```
lattice seed [--force]
```

Writes the 12 example facts from `seed/example_facts.yaml` into `.lattice/facts/`. Creates placeholder Draft facts for any referenced codes not in the seed set (e.g., RISK-03, ETH-01, etc.). `--force` overwrites existing facts with same codes.

### 6.10 lattice status

```
lattice status
```

Displays: backend type, total facts, breakdown by layer, breakdown by status, stale count, last changelog entry timestamp.

---

## 7. Seed Data

The 12 example facts from the design document, stored in `seed/example_facts.yaml`. These are: ADR-01, ADR-03, PRD-01, DES-01, MC-01, AUP-05, RISK-07, DG-01, SP-01, API-01, MON-01, RUN-01.

Missing ref targets that should be created as Draft placeholders: RISK-03, RISK-05, RISK-02, ETH-01, ETH-02, AUP-01, AUP-02, SP-03, MON-04, DG-03, COMP-01, COMP-04, MON-03, ML-01, PRD-02.

---

## 8. Test Specifications

### 8.1 Fixtures (conftest.py)

- `tmp_lattice`: Creates a temporary directory with `.lattice/` structure, yields path, cleans up after.
- `yaml_store`: Returns a `YamlFileStore` pointed at `tmp_lattice`.
- `seeded_store`: Loads the 12 seed facts into `yaml_store`, returns the store.

### 8.2 Required Test Cases

#### test_models.py
| Test | Asserts |
|------|---------|
| `test_valid_fact_creation` | All fields populated, no error |
| `test_code_format_validation` | `"bad-code"` (lowercase) raises ValidationError |
| `test_layer_prefix_mismatch` | `ADR-01` with layer=GUARDRAILS raises ValidationError |
| `test_tag_normalization` | `["Security", "API"]` becomes `["api", "security"]` |
| `test_minimum_tags` | Single tag raises ValidationError |
| `test_superseded_requires_target` | Status=Superseded without superseded_by raises ValidationError |
| `test_fact_text_minimum_length` | 5-char fact text raises ValidationError |

#### test_yaml_store.py
| Test | Asserts |
|------|---------|
| `test_create_and_get` | Create fact, get by code, all fields match |
| `test_create_duplicate` | Second create with same code raises FileExistsError |
| `test_update_increments_version` | Version goes from 1 to 2, updated_at changes |
| `test_deprecate` | Status becomes Deprecated, version increments |
| `test_list_default_active` | Only Active facts returned by default |
| `test_list_filter_layer` | `layer="WHY"` returns only WHY facts |
| `test_list_filter_tags_any` | `tags_any=["security"]` returns RISK-07, DG-01 |
| `test_list_filter_tags_all` | `tags_all=["security", "privacy"]` returns only facts with both |
| `test_list_text_search` | `text_search="prompt injection"` returns RISK-07 |
| `test_exists` | Returns True for existing, False for missing |
| `test_stats` | Returns correct counts by layer and status |
| `test_changelog_appended` | Create + update produces 2 lines in changelog.jsonl |

#### test_validate.py
| Test | Asserts |
|------|---------|
| `test_valid_lattice_passes` | Seeded lattice has no errors |
| `test_broken_ref_detected` | Fact with ref to non-existent code produces warning |
| `test_duplicate_code_detected` | Two files with same code field produces error |
| `test_malformed_yaml_detected` | Invalid YAML file produces error |
| `test_stale_facts_listed` | Facts past review_by are listed |

#### test_cli.py
| Test | Asserts |
|------|---------|
| `test_init_creates_structure` | `.lattice/`, `facts/`, `roles/`, `config.yaml` exist |
| `test_init_already_exists` | Second `init` prints error |
| `test_seed_loads_facts` | After seed, 12+ YAML files in facts/ |
| `test_fact_get_json` | `--json` flag returns valid JSON |
| `test_fact_ls_filter` | `--layer WHY` returns only WHY codes |
| `test_status_output` | Shows backend, counts, staleness |

---

## 9. Acceptance Criteria — Phase 1 Done When

- [ ] `lattice init` creates `.lattice/` with config.yaml, facts/, roles/, history/
- [ ] `lattice fact add --from fact.yaml` writes a valid fact file
- [ ] `lattice fact get ADR-03` displays the fact with all fields
- [ ] `lattice fact get ADR-03 --json` outputs valid JSON
- [ ] `lattice fact ls` lists all Active facts in a Rich table
- [ ] `lattice fact ls --layer WHY` returns only WHY facts
- [ ] `lattice fact ls --tag security` returns RISK-07, DG-01
- [ ] `lattice fact edit ADR-03` opens in $EDITOR, validates on save, increments version
- [ ] `lattice fact deprecate ADR-03 --reason "test"` sets status to Deprecated
- [ ] `lattice validate` catches broken refs, bad schemas, stale facts
- [ ] `lattice reindex` rebuilds index.yaml
- [ ] `lattice seed` loads 12 example facts + placeholder drafts
- [ ] `lattice status` shows backend, counts by layer/status, stale count
- [ ] All tests in §8.2 pass
- [ ] `history/changelog.jsonl` records every create/update/deprecate
- [ ] Entire `.lattice/` directory works after `git clone` on another machine

---

## 10. What Phase 1 Does NOT Include

Explicitly out of scope — do not build yet:

- **Knowledge graph traversal** (Phase 2) — impact analysis, orphan detection
- **Context assembly** (Phase 3) — token budgeting, role-based context
- **LLM extraction** (Phase 4) — document-to-fact extraction
- **MCP server** (Phase 5) — network access to the lattice
- **SQLite backend** (Phase 6) — performance scaling
- **Enterprise features** (Phase 7) — multi-project, RBAC, remote DB
- **Full-text search** — substring match on `fact` field is sufficient for Phase 1
- **Pagination** — not needed at Tier 1 scale

---

*Phase 1 gives you the foundation. Every subsequent phase builds on it without changing these interfaces.*
