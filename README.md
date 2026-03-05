# LatticeLens

A knowledge governance layer for AI agent systems. LatticeLens gives teams a structured, version-controlled way to capture the decisions, constraints, and procedures that AI agents must follow — and makes that knowledge queryable from the command line, CI pipelines, and (soon) directly from agent prompts via MCP.

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
pip install -e .
```

### Initialize a lattice

```bash
lattice init
```

This creates a `.lattice/` directory in your project with:

```
.lattice/
├── config.yaml     # Backend settings
├── facts/          # Individual fact YAML files
├── roles/          # Role query templates (planning, architecture, etc.)
├── history/        # Append-only changelog (JSONL)
└── .gitignore      # Excludes generated index
```

### Load example facts

```bash
lattice seed
```

Loads 12 example facts covering all three layers plus placeholder drafts for referenced targets.

### Explore

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

# Soft delete (no hard deletes — facts are Deprecated, never removed)
lattice fact deprecate ADR-03 --reason "Superseded by ADR-04"
```

### Validate integrity

```bash
# Check for broken refs, schema errors, stale facts
lattice validate

# Auto-fix tags (normalize, sort, deduplicate)
lattice validate --fix
```

### Other commands

```bash
# Rebuild the in-memory index file
lattice reindex

# Show backend, counts by layer/status, staleness
lattice status
```

## Fact YAML Format

Each fact is stored as an individual file in `.lattice/facts/{CODE}.yaml`:

```yaml
code: RISK-07
layer: GUARDRAILS
type: Risk Assessment Finding
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

A `/lattice` skill is included for Claude Code users. Type `/lattice` in any Claude Code session to get usage guidance, or `/lattice how do I filter by tag` to ask a specific question.

To make it available globally (outside this repo), copy the skill to your personal skills directory:

```bash
cp -r .claude/skills/lattice ~/.claude/skills/lattice
```

## Development

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Lint
ruff check src/ tests/
```

## Roadmap

### Phase 1 — Core CLI + YAML Backend (current)

Git-native fact storage, full CRUD, filtering, validation, seed data. The foundation everything else builds on.

### Phase 2 — Knowledge Graph + Git Integration

Impact analysis ("if I change ADR-03, what breaks?"), orphan detection, git-aware diffs and history scoped to `.lattice/facts/`.

### Phase 3 — Context Assembly Engine

Role-scoped, token-budgeted context assembly. Run `lattice context planning` and get exactly the facts the Planning Agent needs, fitted to a token budget.

### Phase 4 — LLM Extraction + Import/Export

Point `lattice extract` at a design doc or PRD and get atomic facts auto-generated. Export/import lattices for backup, sharing, or migration between projects.

### Phase 5 — MCP Server

Expose the lattice over Model Context Protocol so Claude Desktop, Claude Code, Cursor, and custom agents can query governed facts natively — the end-to-end value proposition.

## License

MIT
