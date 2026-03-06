<p align="center">
  <img src="assets/logo.png" alt="LatticeLens" width="300">
</p>

<h1 align="center">LatticeLens</h1>
<p align="center"><strong>Knowledge Governance for AI</strong></p>

<p align="center">
  <img alt="Python 3.11+" src="https://img.shields.io/badge/python-3.11%2B-blue">
  <img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-green">
  <img alt="Tests: 266 passed" src="https://img.shields.io/badge/tests-266%20passed-brightgreen">
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

| Layer | What it captures | Example prefixes |
|-------|-----------------|------------------|
| **WHY** | Decisions, requirements, ethics, design rationale | ADR, PRD, ETH, DES |
| **GUARDRAILS** | Constraints, policies, risks, compliance rules | MC, AUP, RISK, DG, COMP |
| **HOW** | Procedures, API specs, runbooks, monitoring rules | SP, API, RUN, ML, MON |

Each fact is an individual YAML file, validated by Pydantic, tracked by git, and queryable by tag, layer, status, and text search.

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

### Explore facts

```bash
# List all active facts
lattice fact ls

# Filter by layer
lattice fact ls --layer GUARDRAILS

# Filter by tag
lattice fact ls --tag security

# View a single fact
lattice fact get RISK-07

# JSON output (pipe to jq, feed to agents, etc.)
lattice fact get ADR-01 --json
```

### Create a fact

```bash
# Interactive mode — prompts for each field
lattice fact add

# From a YAML file
lattice fact add --from my-fact.yaml
```

### Edit and lifecycle

```bash
# Open in $EDITOR, validates on save, bumps version
lattice fact edit ADR-03

# Promote through lifecycle: Draft -> Under Review -> Active
lattice fact promote ADR-03 --reason "Reviewed and approved by team"

# Soft delete (no hard deletes — facts are Deprecated, never removed)
lattice fact deprecate ADR-03 --reason "Superseded by ADR-04"
```

New facts default to `Draft` status and must be promoted through the lifecycle before they appear in agent context.

### Validate integrity

```bash
# Check for broken refs, schema errors, stale facts, type mismatches
lattice validate

# Auto-fix tags (normalize, sort, deduplicate)
lattice validate --fix
```

### Knowledge graph

```bash
# What breaks if I change ADR-03? Shows direct, transitive, and affected roles
lattice graph impact ADR-03

# Limit traversal depth (default: 3)
lattice graph impact ADR-03 --depth 1

# Find facts with no references in or out
lattice graph orphans

# Find active fact pairs sharing tags across different layers/owners
lattice graph contradictions
```

All graph commands support `--json` for machine-readable output.

### Context assembly

```bash
# Assemble governed facts for the planning agent role
lattice context planning

# Respect a token budget — loads highest-priority facts first
lattice context planning --budget 4000

# JSON output — pipe directly into an agent prompt
lattice context planning --json

# Different roles get different facts
lattice context architecture --budget 8000 --json
```

Context assembly follows priority loading: Confirmed facts first, then Provisional if budget remains. Draft, Deprecated, and Superseded facts are never included. Facts that exist but weren't loaded are listed as REFS pointers so the agent knows what it's missing.

### LLM extraction

```bash
# Extract facts from a design document (requires anthropic SDK)
lattice extract docs/architecture.md

# Preview without writing
lattice extract docs/prd.md --dry-run

# Custom extraction prompt
lattice extract docs/notes.md --prompt "Focus on security decisions"
```

Extracted facts are always created as `Draft` status, requiring human review before promotion.

### Import / Export

```bash
# Export all facts to JSON
lattice export --format json > backup.json

# Export to YAML
lattice export --format yaml > backup.yaml

# Import with merge strategies
lattice import backup.json                     # skip (default) — ignore existing codes
lattice import backup.json --strategy overwrite  # update existing facts
lattice import backup.json --strategy fail       # abort on any collision
```

### Tag and type registries

```bash
# View all tags with usage counts and vocabulary categories
lattice tags

# Rebuild the tag registry from current facts
lattice tags --rebuild

# View canonical types per code prefix
lattice types

# Audit facts for non-canonical type strings
lattice types --audit
```

### MCP server

```bash
# Start MCP server over stdio (for Claude Desktop, Claude Code, Cursor)
lattice serve

# Start with write tools enabled
lattice serve --writable

# Start over SSE for team/network access
lattice serve --host 0.0.0.0 --port 3100
```

The MCP server exposes 7 read-only tools (fact_get, fact_query, fact_list, context_assemble, graph_impact, graph_orphans, lattice_status) and optionally 3 write tools (fact_create, fact_update, fact_deprecate) in writable mode.

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

### Git integration

```bash
# Fact-level diff summary (which codes changed, which fields)
lattice diff

# Show only staged changes
lattice diff --staged

# Git history for all facts
lattice log

# History for a specific fact
lattice log ADR-03 --limit 10
```

### Other commands

```bash
# Governance briefing (what the Claude Code hook outputs)
lattice evaluate

# Rebuild the in-memory index file
lattice reindex

# Show backend, counts by layer/status, staleness
lattice status

# Migrate lattice to latest schema version (safe, idempotent)
lattice upgrade
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
    ]
  }
}
```

That's it. Every prompt you submit in Claude Code will now be preceded by the project's governance briefing.

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

# Run tests (266 tests)
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
├── services/         # Business logic (context, graph, tags, types, etc.)
├── store/            # Storage abstraction (protocol + YAML backend)
├── models.py         # Pydantic Fact model
└── config.py         # Settings + lattice root discovery
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

### Phase 6 — Bidirectional Reconciliation + SQLite Backend

**Reconciliation**: Verify knowledge against codebases in both directions. Facts-to-Code checks whether documented decisions match implementation. Code-to-Facts surfaces code behaviors with no corresponding fact. Produces a report categorizing each finding as confirmed, stale, violated, untracked, or orphaned.

**SQLite Backend**: Tier 2 of the progressive storage architecture for lattices with 500+ facts. Indexed queries, WAL-mode concurrent reads, zero CLI changes via the LatticeStore protocol abstraction. Backend switching is always explicit — the system advises but never auto-migrates.

## License

MIT
