<p align="center">
  <img src="assets/logo.png" alt="LatticeLens" width="300">
</p>

<h1 align="center">LatticeLens</h1>
<p align="center"><strong>Knowledge Governance for AI</strong></p>

<p align="center">
  <img alt="Python 3.11+" src="https://img.shields.io/badge/python-3.11%2B-blue">
  <img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-green">
  <img alt="Tests: 324 passed" src="https://img.shields.io/badge/tests-324%20passed-brightgreen">
</p>

<p align="center">
  <a href="#quick-start">Quick Start</a> &middot;
  <a href="#commands">Commands</a> &middot;
  <a href="#claude-code-integration">Claude Code Integration</a> &middot;
  <a href="#roadmap">Roadmap</a>
</p>

---

A knowledge governance layer for AI agent systems. LatticeLens gives teams a structured, version-controlled way to capture the decisions, constraints, and procedures that AI agents must follow — and makes that knowledge queryable from the command line, CI pipelines, and directly from agent prompts via MCP.

## The Problem

AI agents are increasingly making consequential decisions — choosing architectures, enforcing policies, generating code — but the knowledge that should govern those decisions lives scattered across wikis, Slack threads, design docs, and people's heads. This creates real failure modes:

- **Drift**: An agent generates code that violates an architectural decision nobody told it about.
- **Inconsistency**: Two agents on the same team follow contradictory security policies.
- **Opacity**: When something goes wrong, there's no audit trail of which facts the agent was (or wasn't) working from.
- **Onboarding friction**: New team members and new agents have no single place to find "the rules."

LatticeLens solves this by providing a **single, git-native knowledge base** where teams record atomic facts organized into three layers:

| Layer | What it captures |
|-------|-----------------|
| **WHY** | Decisions, requirements, ethics, design rationale |
| **GUARDRAILS** | Constraints, policies, risks, compliance rules |
| **HOW** | Procedures, API specs, runbooks, monitoring rules |

Each fact is an individual YAML file with a code prefix that determines its type. The 14 canonical types are:

#### WHY — Why we build what we build

| Prefix | Type | Purpose |
|--------|------|---------|
| ADR | Architecture Decision Record | Captures architectural choices with context, alternatives considered, and rationale for the selected approach |
| PRD | Product Requirement | Defines what the system must do — functional requirements, acceptance criteria, and success metrics |
| ETH | Ethical Finding | Documents ethical considerations, bias assessments, and fairness evaluations for AI system behavior |
| DES | Design Proposal Decision | Records design-level decisions (API shape, data models, UX flows) that don't rise to full ADR scope |

#### GUARDRAILS — What the system must not violate

| Prefix | Type | Purpose |
|--------|------|---------|
| MC | Model Card Entry | Documents AI model characteristics — capabilities, limitations, intended use, and known failure modes |
| AUP | Acceptable Use Policy Rule | Defines hard constraints on system behavior — what the system must always or never do |
| RISK | Risk Register Entry | Tracks identified risks with severity, likelihood, mitigation strategies, and residual risk levels |
| DG | Data Governance Rule | Specifies data handling requirements — retention, access controls, PII treatment, and audit obligations |
| COMP | Compliance Rule | Captures regulatory and standards compliance requirements (SOC 2, GDPR, ISO, industry-specific) |

#### HOW — How the system operates

| Prefix | Type | Purpose |
|--------|------|---------|
| SP | System Prompt Rule | Defines rules and instructions that shape AI agent behavior at runtime via system prompts |
| API | API Specification | Documents API contracts — endpoints, schemas, authentication, rate limits, and versioning policies |
| RUN | Runbook Procedure | Step-by-step operational procedures for deployment, rollback, incident response, and maintenance |
| ML | MLOps Rule | Specifies ML pipeline requirements — training schedules, evaluation thresholds, model versioning, and drift detection |
| MON | Monitoring Rule | Defines what to monitor, alert thresholds, escalation paths, and observability requirements |

Each fact is validated by Pydantic, tracked by git, and queryable by tag, layer, status, and text search.

## Quick Start

### Prerequisites

- Python 3.11+

### Install

```bash
# From source
pip install -e .

# With MCP server support
pip install -e ".[mcp]"

# With LLM extraction support
pip install -e ".[extract]"
```

### Initialize a lattice

```bash
lattice init
```

This creates a `.lattice/` directory in your project with:

```
.lattice/
├── config.yaml     # Backend settings + schema version
├── facts/          # Individual fact YAML files
├── roles/          # Role query templates (planning, architecture, etc.)
├── history/        # Append-only changelog (JSONL)
├── tags.yaml       # Generated tag registry with usage counts
├── types.yaml      # Canonical type registry per code prefix
└── .gitignore      # Excludes generated index
```

### Load example facts

```bash
lattice seed
```

Loads 12 example facts covering all three layers plus placeholder drafts for referenced targets.

## Commands

LatticeLens provides 20 top-level commands organized into four categories: core operations, fact management, knowledge graph analysis, and backend management.

### Core Commands

| Command | Description |
|---------|-------------|
| `lattice init` | Create `.lattice/` directory with default structure |
| `lattice status` | Show backend type, fact counts by layer/status, and staleness |
| `lattice validate` | Check lattice integrity: YAML parsing, refs, tags, staleness |
| `lattice reindex` | Rebuild `index.yaml` from scanning all fact files |
| `lattice seed` | Load 12 example facts + placeholder drafts |
| `lattice upgrade` | Migrate lattice to the latest schema version (safe, idempotent) |
| `lattice evaluate` | Output governance briefing (used by Claude Code hook) |

```bash
lattice init                     # Initialize a new lattice
lattice status                   # Summary: backend, counts, staleness
lattice validate                 # Check integrity
lattice validate --fix           # Auto-fix tags (normalize, sort, deduplicate)
lattice reindex                  # Rebuild index from fact files
lattice seed                     # Load example facts
lattice upgrade                  # Upgrade schema version
lattice evaluate                 # Governance briefing (text)
lattice evaluate --json          # Governance briefing (JSON)
lattice evaluate --verbose       # Diagnostics on stderr
```

### Fact Management — `lattice fact`

| Subcommand | Description |
|------------|-------------|
| `lattice fact add` | Add a new fact (interactive or from file) |
| `lattice fact get CODE` | Display a single fact by code |
| `lattice fact ls` | List facts matching filters |
| `lattice fact edit CODE` | Open a fact in `$EDITOR`, validate on save |
| `lattice fact promote CODE` | Promote: Draft → Under Review → Active |
| `lattice fact deprecate CODE` | Soft-delete a fact (set status to Deprecated) |

```bash
# List and filter
lattice fact ls                           # All active facts
lattice fact ls --layer GUARDRAILS        # Filter by layer
lattice fact ls --tag security            # Filter by tag
lattice fact ls --status Draft            # Filter by status
lattice fact ls --type "Risk Register Entry"  # Filter by type

# View
lattice fact get RISK-07                  # Rich display
lattice fact get ADR-01 --json            # JSON output

# Create
lattice fact add                          # Interactive mode
lattice fact add --from my-fact.yaml      # From file

# Edit and lifecycle
lattice fact edit ADR-03                  # Open in $EDITOR, validates on save
lattice fact promote ADR-03 --reason "Reviewed and approved"
lattice fact deprecate ADR-03 --reason "Superseded by ADR-04"
```

New facts default to `Draft` status and must be promoted through the lifecycle before they appear in agent context.

### Knowledge Graph — `lattice graph`

| Subcommand | Description |
|------------|-------------|
| `lattice graph impact CODE` | Show facts and roles affected by changing a fact |
| `lattice graph orphans` | Find facts with no references in or out |
| `lattice graph contradictions` | Find active fact pairs that may contradict |

```bash
lattice graph impact ADR-03               # Direct, transitive, and role impacts
lattice graph impact ADR-03 --depth 1     # Limit traversal depth (default: 3)
lattice graph orphans                     # Disconnected facts
lattice graph contradictions              # Potential contradictions
```

All graph commands support `--json` for machine-readable output.

### Reconciliation — `lattice reconcile`

Verify governance facts against the codebase in both directions: facts-to-code and code-to-facts.

| Option | Description |
|--------|-------------|
| `--path PATH` | Directory to scan (default: project root) |
| `--include TEXT` | Glob patterns to include (default: `**/*.py`) |
| `--exclude TEXT` | Glob patterns to exclude |
| `--llm` | Enable LLM-assisted analysis via Anthropic API |
| `--json` | Output report as JSON |
| `--verbose` | Show per-fact matching details |

```bash
lattice reconcile                         # Scan project, Rich table output
lattice reconcile --json                  # Machine-readable JSON report
lattice reconcile --verbose               # Per-fact matching details
lattice reconcile --path src/ --include "**/*.py"  # Custom scan scope
```

Findings are categorized as **confirmed** (fact matches code), **stale** (fact outdated), **violated** (code contradicts fact), **untracked** (code pattern with no fact), or **orphaned** (fact with no code evidence).

### Context Assembly — `lattice context`

Assemble token-budgeted, role-scoped fact sets for agent prompts.

```bash
lattice context planning                  # Facts for the planning role
lattice context planning --budget 4000    # Token-limited
lattice context planning --json           # JSON output for agent injection
lattice context architecture --budget 8000 --json
```

Priority loading: Confirmed facts first, then Provisional if budget remains. Draft, Deprecated, and Superseded facts are never included. Excluded facts are listed as REFS pointers.

### LLM Extraction — `lattice extract`

Extract atomic facts from documents using an LLM (requires `anthropic` SDK).

```bash
lattice extract docs/architecture.md      # Extract and create Draft facts
lattice extract docs/prd.md --dry-run     # Preview without writing
lattice extract --prompt                 # Print extraction prompt for agent use
```

Extracted facts are always created as `Draft` status, requiring human review before promotion.

### Import / Export

```bash
# Export
lattice export --format json > backup.json
lattice export --format yaml > backup.yaml

# Import with merge strategies
lattice import backup.json                       # skip (default)
lattice import backup.json --strategy overwrite  # update existing
lattice import backup.json --strategy fail       # abort on collision
```

### Tag and Type Registries

```bash
lattice tags                    # View all tags with usage counts
lattice tags --rebuild          # Rebuild tag registry from current facts
lattice types                   # View canonical types per code prefix
lattice types --audit           # Audit facts for non-canonical type strings
```

### Backend Management — `lattice backend`

| Subcommand | Description |
|------------|-------------|
| `lattice backend status` | Show current backend type, fact count, advisory thresholds |
| `lattice backend switch TARGET` | Migrate between `yaml` and `sqlite` backends |

```bash
lattice backend status                    # Current backend info
lattice backend switch sqlite             # Migrate YAML → SQLite
lattice backend switch yaml               # Migrate SQLite → YAML
```

The system advises at 1,500+ facts and warns at 2,000+ facts to switch to SQLite, but never auto-migrates. Backend switching preserves all data.

### Git Integration

```bash
lattice diff                    # Fact-level diff summary
lattice diff --staged           # Show only staged changes
lattice log                     # Git history for all facts
lattice log ADR-03 --limit 10  # History for a specific fact
```

### MCP Server — `lattice serve`

Start a Model Context Protocol server for AI agent integration.

```bash
lattice serve                             # stdio transport (default)
lattice serve --writable                  # Enable write tools
lattice serve --host 0.0.0.0 --port 3100 # SSE transport for network access
```

The MCP server exposes 8 read-only tools (`fact_get`, `fact_query`, `fact_list`, `context_assemble`, `graph_impact`, `graph_orphans`, `lattice_status`, `reconcile`) and optionally 3 write tools (`fact_create`, `fact_update`, `fact_deprecate`) in writable mode.

#### MCP client configuration

```json
{
  "mcpServers": {
    "lattice": {
      "command": "lattice",
      "args": ["serve", "--stdio"],
      "cwd": "/path/to/your/project"
    }
  }
}
```

## Fact YAML Format

Each fact is stored as an individual file in `.lattice/facts/{CODE}.yaml`:

```yaml
code: RISK-07
layer: GUARDRAILS
type: Risk Register Entry
fact: >-
  Prompt injection via user-uploaded documents rated HIGH severity
  (likelihood: 4/5, impact: 5/5). Mitigation: input sanitization +
  document content sandboxing + output validation against original
  intent. Residual risk: MEDIUM after mitigation.
tags:
- high-severity
- mitigation
- prompt-injection
- security
- user-input
status: Active
confidence: Confirmed
version: 1
refs:
- ADR-03
- AUP-02
- SP-03
- MON-04
owner: security-team
review_by: 2026-06-01
```

### Business Rules

1. **Code immutability** — a fact's code never changes after creation
2. **Version monotonicity** — version increments by exactly 1 on each update
3. **Soft ref integrity** — refs to non-existent codes produce warnings, not errors
4. **Superseded requires target** — status `Superseded` requires `superseded_by`
5. **No hard deletes** — deprecation sets status, never removes the file
6. **Stale detection** — facts past `review_by` are flagged on read
7. **Tag normalization** — always lowercase, sorted, deduplicated
8. **Auto-timestamping** — `updated_at` set on every write, `created_at` never modified
9. **Layer-code consistency** — code prefix must match its layer's allowed prefixes
10. **Changelog append** — every mutation appends to `history/changelog.jsonl`

## Claude Code Integration

### Governance Hook (Recommended)

LatticeLens includes a `UserPromptSubmit` hook that automatically injects your project's governance rules into every Claude Code conversation. When active, the hook:

1. **Enforces governance** — All active GUARDRAILS-layer rules (AUP, DG, RISK, MC) are injected as mandatory context. The agent is instructed to follow these rules and **raise conflicts before proceeding** if a request would violate any rule, citing the specific rule code.
2. **Encourages knowledge discovery** — A summary of available WHY/HOW facts is included with instructions to run `lattice context <role> --json` before starting development work.
3. **Silent when absent** — If the project has no `.lattice/` directory, the hook produces no output and does not interfere.

#### Setup

**Step 1:** Install LatticeLens so the `lattice` command is on your PATH:

```bash
pip install -e .
```

**Step 2:** Add the hook configuration to your project's `.claude/settings.json`:

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "lattice evaluate",
            "timeout": 10
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Edit|Write",
        "hooks": [
          {
            "type": "command",
            "command": "bash \"$CLAUDE_PROJECT_DIR\"/.claude/hooks/audit-governance.sh",
            "timeout": 30
          }
        ]
      }
    ],
    "Stop": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "bash \"$CLAUDE_PROJECT_DIR\"/.claude/hooks/compliance-check.sh",
            "timeout": 30
          }
        ]
      }
    ]
  }
}
```

**Step 3:** Copy the hook scripts into your project:

```bash
mkdir -p .claude/hooks
cp .claude/hooks/audit-governance.sh .claude/hooks/
cp .claude/hooks/compliance-check.sh .claude/hooks/
```

The three hooks work together as a governance pipeline:

| Hook | Trigger | Purpose |
|------|---------|---------|
| `UserPromptSubmit` | Every prompt | Injects governance rules and knowledge context before Claude responds |
| `PostToolUse` | After `Edit` or `Write` | Runs `lattice validate` after file changes — blocks on validation failure |
| `Stop` | When Claude finishes responding | Audits modified source files against governance rules — blocks on new changes to force a compliance report |

The `PostToolUse` hook catches lattice integrity issues immediately after edits. The `Stop` hook performs a broader compliance audit once Claude is done, checking all modified `src/` files against governance rules. It uses a stamp file (`.claude/.audit-stamp`) to avoid infinite re-prompt loops — if the same changes have already been audited, it reports findings without blocking.

#### What the agent sees

When you submit a prompt, Claude sees something like:

```
# LatticeLens Governance Briefing

## Mandatory Rules
You MUST follow these governance rules for this project. If the user's
request would violate any of these rules, you MUST raise the conflict
before proceeding — cite the specific rule code (e.g. AUP-01)...

### [AUP-01] Acceptable Use Policy Rule (Confirmed)
Facts are never hard-deleted...

### [DG-06] Data Governance Rule (Confirmed)
Facts progress through a defined lifecycle...

## Project Knowledge Available
This project has a knowledge lattice you should consult before development:

**WHY layer** (architectural decisions & requirements):
- 13 Architecture Decision Records
- 3 Product Requirements
...

### Before starting work, load relevant context:
- For planning/scoping: `lattice context planning --json`
- For coding tasks: `lattice context implementation --json`
...
```

#### Manual testing

You can preview what the hook outputs at any time:

```bash
# Text briefing (what Claude sees)
lattice evaluate

# JSON format (for scripting or the agent hook variant)
lattice evaluate --json

# Test from a specific directory
lattice evaluate --path /path/to/project

# Diagnostics on stderr
lattice evaluate --verbose
```

#### Agent hook variant (optional)

For deeper AI-powered evaluation, you can use an agent-type hook instead of (or in addition to) the command hook. This spawns a Claude sub-agent that loads the lattice context and reasons about whether the prompt aligns with governance rules:

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "agent",
            "prompt": "You are a governance reviewer. Run `lattice evaluate --json` to load this project's governance rules and knowledge summary. Then evaluate whether the user's prompt might lead to actions that violate any governance rules, or whether there are relevant architectural decisions or design patterns the agent should review first. Output your assessment. $ARGUMENTS",
            "timeout": 30
          }
        ]
      }
    ]
  }
}
```

This is slower (~5-10s per prompt) but can catch subtler conflicts that simple context injection might miss.

### Skill

A `/lattice` skill is included for Claude Code users. Type `/lattice` in any Claude Code session to get usage guidance, or `/lattice how do I filter by tag` to ask a specific question.

To make it available globally (outside this repo), copy the skill to your personal skills directory:

```bash
cp -r .claude/skills/lattice ~/.claude/skills/lattice
```

## Development

```bash
# Install with all dev dependencies
pip install -e ".[dev]"

# Run tests (324 tests)
pytest

# Run tests with coverage
pytest --cov=lattice_lens

# Lint
ruff check src/ tests/
```

### Project Structure

```
src/lattice_lens/
├── cli/              # Typer CLI commands
├── mcp/              # MCP server (FastMCP)
├── services/         # Business logic (context, graph, tags, types, reconciliation)
├── store/            # Storage abstraction (protocol + YAML/SQLite backends)
├── models.py         # Pydantic Fact model
└── config.py         # Settings, lattice root discovery, backend config
```

## Roadmap

### Phase 1 — Core CLI + YAML Backend ✓

Git-native fact storage, full CRUD, filtering, validation, seed data. The foundation everything else builds on.

### Phase 2 — Knowledge Graph + Git Integration ✓

Impact analysis (`lattice graph impact`), orphan detection, contradiction candidates, git-aware diffs (`lattice diff`) and history (`lattice log`), versioned schema upgrades (`lattice upgrade`).

### Phase 3 — Context Assembly + Fact Lifecycle ✓

Lifecycle commands (`lattice fact promote`), role-scoped token-budgeted context assembly (`lattice context planning --budget 4000`), priority loading (Confirmed first, Provisional if budget remains), REFS pointers for excluded facts.

### Phase 4 — LLM Extraction + Import/Export ✓

Point `lattice extract` at a design doc or PRD and get atomic facts auto-generated. Export/import lattices for backup, sharing, or migration between projects. Post-task governance audit hook validates compliance after every implementation.

### Phase 5 — MCP Server + Tag/Type Registries ✓

Expose the lattice over Model Context Protocol (`lattice serve`) so Claude Desktop, Claude Code, Cursor, and custom agents can query governed facts natively. Centralized tag registry with vocabulary categories (`lattice tags`) and canonical type mapping with audit mode (`lattice types`).

### Phase 6 — Bidirectional Reconciliation + SQLite Backend ✓

**Reconciliation** (`lattice reconcile`): Verify knowledge against codebases in both directions. Facts-to-Code checks whether documented decisions match implementation. Code-to-Facts surfaces code behaviors with no corresponding fact. Produces a report categorizing each finding as confirmed, stale, violated, untracked, or orphaned.

**SQLite Backend** (`lattice backend switch sqlite`): Tier 2 of the progressive storage architecture for lattices with 500+ facts. Indexed queries, WAL-mode concurrent reads, zero CLI changes via the LatticeStore protocol abstraction. Backend switching is always explicit — the system advises but never auto-migrates.

## Complete CLI Reference

Every command, argument, and option. For examples and narrative documentation, see the [Commands](#commands) section above.

### Core Commands

#### `lattice init`

Create `.lattice/` directory with default structure.

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--path` | path | cwd | Directory to initialize in |

#### `lattice status`

Show backend type, fact counts by layer/status, and staleness. No options.

#### `lattice validate`

Check lattice integrity: YAML parsing, refs, tags, staleness.

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--fix` | flag | false | Auto-fix correctable issues |

#### `lattice reindex`

Rebuild `index.yaml` from scanning all fact files. No options.

#### `lattice seed`

Load 12 example facts + placeholder drafts into `.lattice/facts/`.

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--force` | flag | false | Overwrite existing facts |

#### `lattice upgrade`

Upgrade lattice to the latest schema version. Safe and idempotent. No options.

#### `lattice check`

CI gate: run all integrity checks and exit 0 (pass) or 1 (fail).

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--strict` | flag | false | Treat warnings as errors |
| `--stale-is-error` | flag | false | Treat stale facts as errors |
| `--reconcile` | path | — | Run reconciliation against codebase at PATH |
| `--include` | text (repeatable) | — | Glob patterns for reconciliation |
| `--exclude` | text (repeatable) | — | Glob exclusions for reconciliation |
| `--min-coverage` | int | 0 | Minimum coverage % (requires `--reconcile`) |
| `--format` | text | `text` | Output format: `text`, `json`, `github` |

#### `lattice evaluate`

Output governance briefing for Claude Code hook injection.

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--json` | flag | false | Output as JSON |
| `--path` | path | cwd | Directory to evaluate |
| `--verbose` | flag | false | Print diagnostics to stderr |

### Fact Management — `lattice fact`

#### `lattice fact add`

Add a new fact (interactive or from file).

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--from` | path | — | Create fact from YAML file |

#### `lattice fact get CODE`

Display a single fact by code.

| Argument | Description |
|----------|-------------|
| `CODE` | Fact code (e.g., `ADR-01`) |

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--json` | flag | false | Output as JSON |

#### `lattice fact ls`

List facts matching filters.

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--layer` | text | — | Filter by layer (`WHY`, `GUARDRAILS`, `HOW`) |
| `--tag` | text | — | Filter by tag |
| `--status` | text | — | Filter by status (`Active`, `Draft`, `Under Review`, etc.) |
| `--type` | text | — | Filter by type (e.g., `Architecture Decision Record`) |
| `--project` | text | — | Filter by project scope |
| `--json` | flag | false | Output as JSON |

#### `lattice fact edit CODE`

Open a fact in `$EDITOR`, validate on save. No options.

#### `lattice fact promote CODE`

Promote a fact: Draft → Under Review → Active.

| Argument | Description |
|----------|-------------|
| `CODE` | Fact code to promote |

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--reason` | text (required) | — | Reason for promotion |

#### `lattice fact deprecate CODE`

Deprecate a fact (soft delete).

| Argument | Description |
|----------|-------------|
| `CODE` | Fact code to deprecate |

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--reason` | text (required) | — | Reason for deprecation |

### Knowledge Graph — `lattice graph`

#### `lattice graph impact CODE`

Show facts and roles affected by changing a given fact.

| Argument | Description |
|----------|-------------|
| `CODE` | Fact code to analyze |

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--depth` | int | 3 | Max traversal depth |
| `--json` | flag | false | Output as JSON |

#### `lattice graph orphans`

Find facts with no references in or out.

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--json` | flag | false | Output as JSON |

#### `lattice graph contradictions`

Find pairs of active facts that may contradict each other.

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--min-tags` | int | 2 | Minimum shared tags to flag |
| `--json` | flag | false | Output as JSON |

### Context & Extraction

#### `lattice context ROLE`

Assemble token-budgeted, role-scoped facts for an agent role.

| Argument | Description |
|----------|-------------|
| `ROLE` | Role name (matches `.lattice/roles/{role}.yaml`) |

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--budget` | int | unlimited | Token budget |
| `--project` | text | — | Filter by project scope |
| `--json` | flag | false | Output as JSON |

#### `lattice extract [FILE]`

Extract atomic facts from a document using an LLM.

| Argument | Description |
|----------|-------------|
| `FILE` | Path to document (`.md`, `.txt`, `.docx`). Optional. |

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--prompt` | flag | false | Print extraction prompt to stdout and exit |
| `--dry-run` | flag | false | Preview extracted facts without writing |
| `--model` | text | `claude-sonnet-4-20250514` | Extraction model |
| `--api-key` | text | `$LATTICE_ANTHROPIC_API_KEY` | Anthropic API key |

### Import / Export

#### `lattice export`

Export all facts as JSON or YAML.

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--format` | text | `json` | Output format: `json` or `yaml` |
| `--output` / `-o` | path | stdout | Output file |

#### `lattice import FILE`

Import facts from a JSON or YAML file.

| Argument | Description |
|----------|-------------|
| `FILE` | File to import (`.json` or `.yaml`) |

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--format` | text | auto-detect | File format |
| `--strategy` | text | `skip` | Merge strategy: `skip`, `overwrite`, `fail` |

### Registries

#### `lattice tags`

Show tag registry: all tags with usage counts and vocabulary categories.

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--json` | flag | false | Output as JSON |
| `--rebuild` | flag | false | Regenerate `tags.yaml` from current facts |

#### `lattice types`

Show type registry: canonical type mapping per code prefix.

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--json` | flag | false | Output as JSON |
| `--audit` | flag | false | Show facts with non-canonical types |

### Reconciliation

#### `lattice reconcile`

Reconcile governance facts against the codebase.

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--path` | path | project root | Directory to scan |
| `--include` | text (repeatable) | `**/*.py` | Glob patterns to include |
| `--exclude` | text (repeatable) | — | Glob patterns to exclude |
| `--llm` | flag | false | Enable LLM-assisted analysis |
| `--llm-prompt` | flag | false | Print reconciliation prompt for agent integration |
| `--model` | text | `claude-sonnet-4-20250514` | Model for LLM analysis |
| `--api-key` | text | `$LATTICE_ANTHROPIC_API_KEY` | Anthropic API key |
| `--json` | flag | false | Output report as JSON |
| `--verbose` | flag | false | Show per-fact matching details |

### Backend Management — `lattice backend`

#### `lattice backend status`

Show current backend type, fact count, and advisory thresholds. No options.

#### `lattice backend switch TARGET`

Migrate between YAML and SQLite backends.

| Argument | Description |
|----------|-------------|
| `TARGET` | Target backend: `yaml` or `sqlite` |

### Git Integration

#### `lattice diff`

Show fact-level summary of git changes in `.lattice/facts/`.

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--staged` | flag | false | Show only staged changes |

#### `lattice log [CODE]`

Show git history for lattice facts.

| Argument | Description |
|----------|-------------|
| `CODE` | Fact code (optional — omit for all facts) |

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--limit` / `-n` | int | 20 | Max entries to show |

### MCP Server

#### `lattice serve`

Start the LatticeLens MCP server.

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--stdio` / `--no-stdio` | flag | true | Use stdio transport (for Claude Desktop/Code) |
| `--host` | text | `127.0.0.1` | HTTP host (disables stdio) |
| `--port` | int | 3100 | HTTP port |
| `--writable` | flag | false | Enable write operations |

## License

MIT
